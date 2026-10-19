"""MCP server for option chain tools.

Two tools are exposed:

* ``fetch_option_chain(symbol, exchange)`` — kicks off a background job that
  builds the option chain. The job runs on a tracked thread; its status
  (``pending``/``running``/``ok``/``failed``) is stored in an in-memory job
  table keyed by ``(symbol, exchange)`` so the caller can poll for results.

* ``check_option_chain(symbol, exchange)`` — returns the current status of the
  job, including a sanitized error message if the build failed.

This module is intentionally thin: the heavy lifting is done by
``sync.main.get_option_chain`` running inside a daemon thread. The previous
implementation (a bare ``Thread.start()`` with no completion signal) has been
replaced with a per-job ``concurrent.futures.Future`` so callers no longer
have to poll blindly.
"""

import json
import logging
import threading
from concurrent.futures import Future
from typing import Callable, TypeVar, Awaitable, Dict, Tuple

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

from sync.main import get_option_chain_sync


logger = logging.getLogger(__name__)

load_dotenv()

server = FastMCP("option_chain_server")

# Type variables for the decorator
F = TypeVar('F', bound=Callable[..., Awaitable[str]])


def mcp_tool(func: F) -> F:
    """Custom decorator for MCP tools that automatically sets structured_output=False"""
    return server.tool(structured_output=False)(func)  # type: ignore


# ----------------------------------------------------------------------------
# Job tracking
# ----------------------------------------------------------------------------
#
# A simple in-memory job table. Keys are (symbol, exchange). Each value is a
# Future plus an optional status string ("running", "ok", "failed: <reason>").
#
# This is intentionally not persisted: a process restart discards job state,
# which is the same behaviour the old fire-and-forget version had. Persistence
# is a separate concern (see SA-6 in MINI_AGENT_PLAN4B_REVIEW.md).

_JOBS: Dict[Tuple[str, str], Dict[str, object]] = {}
_JOBS_LOCK = threading.Lock()


def _job_key(symbol: str, exchange: str) -> Tuple[str, str]:
    return (symbol, exchange)


def _submit_job(symbol: str, exchange: str) -> Future:
    """Submit the option-chain build as a tracked, daemon-thread job.

    Returns the underlying ``Future``. The future completes with ``None`` on
    success or re-raises whatever the worker thread raised. Errors are also
    captured into the job-status dict so ``check_option_chain`` can return a
    sanitized message without re-raising to the LLM caller.
    """
    future: Future = Future()

    with _JOBS_LOCK:
        existing = _JOBS.get(_job_key(symbol, exchange))
        if existing is not None and not existing.get("future").done():  # type: ignore[union-attr]
            # A previous job for the same key is still running — return its future
            # so callers don't pile up duplicate work.
            return existing["future"]  # type: ignore[return-value]
        _JOBS[_job_key(symbol, exchange)] = {
            "future": future,
            "status": "running",
            "error": None,
        }

    def _runner() -> None:
        # NOTE (M-1): ``get_option_chain_sync`` is the regular sync entry
        # point in sync/main.py. The previous version was an ``async def``
        # wrapper with no ``await`` inside, executed via a fresh event loop
        # inside the worker thread; that wasted an event-loop create/destroy
        # per job for no benefit.
        try:
            get_option_chain_sync(symbol, exchange)
        except BaseException as exc:  # noqa: BLE001 - we re-raise through the future below
            with _JOBS_LOCK:
                job = _JOBS.get(_job_key(symbol, exchange))
                if job is not None:
                    # Store a sanitized, single-line summary; the full traceback
                    # is logged server-side and never sent to the LLM caller.
                    reason = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else exc!r}"
                    job["status"] = f"failed: {reason}"
                    job["error"] = reason
            logger.exception("fetch_option_chain job failed for %s/%s", symbol, exchange)
            future.set_exception(exc)
        else:
            with _JOBS_LOCK:
                job = _JOBS.get(_job_key(symbol, exchange))
                if job is not None:
                    job["status"] = "ok"
                    job["error"] = None
            future.set_result(None)

    thread = threading.Thread(
        target=_runner,
        name=f"option-chain-{symbol}-{exchange}",
        daemon=True,
    )
    thread.start()
    return future


def _job_status(symbol: str, exchange: str) -> str:
    with _JOBS_LOCK:
        job = _JOBS.get(_job_key(symbol, exchange))
        if job is None:
            return "not_started"
        return str(job.get("status") or "unknown")  # type: ignore[arg-type]


@server.tool(structured_output=False)
async def fetch_option_chain(symbol: str, exchange: str = "SMART") -> str:
    """Retrieve option chain data for a given symbol and exchange.

    Args:
        symbol: Underlier symbol (for example ``"HSI"`` or ``"SPY"``).
        exchange: Exchange identifier. Defaults to ``"SMART"``. See
            ``settings/underlier_mapping.md`` for the right value per symbol.

    The build runs in a tracked background thread. Poll
    ``check_option_chain(symbol, exchange)`` for status; the returned string
    transitions from ``"running"`` to ``"ok"`` (data ready) or ``"failed: ..."``.
    """
    future = _submit_job(symbol, exchange)
    if future.done():
        # The job completed (or failed) before this coroutine returned. Reuse
        # the cached status string so the caller gets a coherent reply.
        status = _job_status(symbol, exchange)
        return json.dumps({
            "symbol": symbol,
            "exchange": exchange,
            "status": status,
            "note": "Job finished before fetch_option_chain returned.",
        }, indent=4)
    return json.dumps({
        "symbol": symbol,
        "exchange": exchange,
        "status": "running",
        "note": (
            f"Started to fetch option chain data for {symbol} on {exchange}; "
            "call check_option_chain to poll status."
        ),
    }, indent=4)


@server.tool(structured_output=False)
async def check_option_chain(symbol: str, exchange: str = "SMART") -> str:
    """Check the status of an option-chain build, or read the persisted data.

    Args:
        symbol: Underlier symbol previously passed to ``fetch_option_chain``.
        exchange: Exchange identifier used in the original call (default SMART).

    Returns a JSON document describing the current job state. When the build
    has finished successfully, this also returns the persisted option-chain
    rows from the database.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from utils.database import query_option_chain

    status = _job_status(symbol, exchange)
    payload: Dict[str, object] = {
        "symbol": symbol,
        "exchange": exchange,
        "status": status,
    }

    if status.startswith("failed"):
        # Surface only the redacted reason that _submit_job stored. The full
        # traceback is already in the server log — we deliberately don't echo
        # SQL fragments, connection strings, or stack frames to the LLM.
        with _JOBS_LOCK:
            job = _JOBS.get(_job_key(symbol, exchange))
            reason = job.get("error") if job else None  # type: ignore[union-attr]
        payload["error"] = reason or status
        return json.dumps(payload, indent=4)

    if status == "not_started":
        payload["note"] = (
            f"No fetch_option_chain call has been recorded for {symbol} on {exchange}."
        )
        return json.dumps(payload, indent=4)

    if status == "running":
        payload["note"] = "Job is still running; check again shortly."
        return json.dumps(payload, indent=4)

    # status == "ok" — fetch the persisted rows.
    try:
        data = query_option_chain(symbol)
    except SQLAlchemyError as exc:
        logger.exception("check_option_chain: DB read failed for %s", symbol)
        payload["error"] = (
            "Database read failed; the server log has the full traceback. "
            f"({type(exc).__name__})"
        )
        return json.dumps(payload, indent=4)

    if not data:
        payload["note"] = (
            f"No option chain data found for symbol '{symbol}' (job reported ok)."
        )
        return json.dumps(payload, indent=4)

    payload["count"] = len(data)
    payload["data"] = data
    return json.dumps(payload, indent=4)


if __name__ == "__main__":
    server.run()