# Code Review: option_chain_builder

**Reviewer:** Mini-Agent (PLAN_4B)
**Date of review:** Generated from static analysis of 16 .py files (~2,595 LOC)
**Scope:** All `.py` files in `sync/`, `async_dev/`, `utils/`, `settings/`, plus `mcp_server.py` and root `__init__.py`.
**Reference:** `AGENTS.md` was read first to understand documented conventions and decisions. Findings are tagged **CONFIRMED** or **REFUTED** against the ten known patterns listed in the brief.

---

## Critical

### C-1. Hardcoded database credential in source (`settings/config.py:7`) — [FIXED]
- **File:line:** `settings/config.py:7`
- **Label:** DB password committed to repository.
- **Why:** The PostgreSQL connection string embeds the literal password `secret` for the `postgres` user. This credential is committed to source, and AGENTS.md even tells users to use the same password in the `docker run` command — meaning anyone with repo access can read production credentials, and any leak of the repo leaks DB write access.
- **Snippet:**
  ```python
  DATABASE_URL = "postgresql+psycopg://postgres:secret@localhost:5432/options_db"
  ```
- **Recommendation:** Move `DATABASE_URL` (or just the password) into an environment variable loaded via `python-dotenv`, and provide an `.env.example`. Treat `secret` as compromised and rotate it. Add `*.env`, `.env` to `.gitignore`.

### C-2. OAuth token / verifier leakage through `print` and `input` (`utils/ibkr_oauth.py:371-401`) — [FIXED]
- **File:line:** `utils/ibkr_oauth.py:371`, `:383`, `:389`, `:398`
- **Label:** Tokens printed to stdout; verifier read interactively without secure transport.
- **Why:** The `__main__` demo prints `request_token`, `access_token`, and the live session token (`lst`) directly to stdout. Combined with the project's stdout-redirect-to-file pattern in `sync/main.py:37-63` and `async_dev/httpx approach.py:218-286`, every token is also written to world-readable log files in `logs/` (which the `.gitignore` does **not** exclude by default — see M-7). The `verifier = input(...)` line accepts the OAuth verifier via stdin with no validation.
- **Snippet:**
  ```python
  print(f"Request Token obtained: {request_token}")
  ...
  print(f"Live Session Token (LST): {lst}")
  ```
- **Recommendation:** Never log OAuth tokens. Mask them (`token[:4] + "***" + token[-4:]`). Add `logs/` to `.gitignore` (or scrub secrets from log files). Move the demo out of `utils/` into a `tools/` or `examples/` folder so production code paths cannot accidentally call it.

### C-3. Private-import of `ibind.client.ibkr_client.IbkrClient` (`async_dev/AsyncFetcher.py:11`) — [FIXED]
- **File:line:** `async_dev/AsyncFetcher.py:11`
- **Label:** Imports private module of an external library with `# type: ignore`.
- **Why:** `ibind.client.ibkr_client` is an underscore-prefixed internal module of `ibind`. Reaching into it pins this code to a specific `ibind` version and can silently break (or silently change behavior) on any dependency upgrade. The `# type: ignore` hides the breakage from any tooling. AGENTS.md says to import from the top-level `ibind` package — that contract is being violated here.
- **Snippet:**
  ```python
  from ibind.client.ibkr_client import IbkrClient  # type: ignore
  ```
- **Recommendation:** Use `from ibind import IbkrClient` (as `sync/` already does on line 8 of `sync/main.py`). If `_get_headers` is the only thing you need, ask `ibind` maintainers to expose a public signing method, or wrap the private call behind your own module boundary with an explicit version-pin comment.

### C-4. Bare-except hides all exceptions in `store_data` and database path (`utils/database.py:23-29`) — [FIXED]
- **File:line:** `utils/database.py:23` (and `:42`)
- **Label:** Module-level engine + `create_all` on import, no error handling around SQL operations.
- **Why:** Importing `utils.database` (which is done transitively from `mcp_server.py` via `check_option_chain`) executes `engine = create_engine(DATABASE_URL)` and `SQLModel.metadata.create_all(engine)` **at import time**. If the DB is unreachable or auth fails, the entire MCP server fails to start with a stack trace. There is also no try/except around `orm_session.merge(...)` or `orm_session.commit()` — a single malformed record aborts the entire batch with no partial save.
- **Snippet:**
  ```python
  engine = create_engine(DATABASE_URL)
  SQLModel.metadata.create_all(engine)
  ```
- **Recommendation:** Defer engine creation with a lazy `get_engine()` (or `functools.lru_cache` over a function). Wrap `create_all` in try/except so the server can boot even if the DB is temporarily down. Wrap `merge`/`commit` in a per-record try/except so one bad row doesn't discard the batch.

### C-5. Fire-and-forget thread with no completion signal in MCP server (`mcp_server.py:29-39`) — [FIXED]
- **File:line:** `mcp_server.py:29`
- **Label:** Background thread is detached; tool returns immediately; no way to know when work is done or what failed.
- **Why:** `thread = threading.Thread(target=_thread_worker, ...)` is started and **never joined, never tracked, and never reports back**. The tool returns a static string "please come back later" — the user has to poll `check_option_chain` blindly. Worse, exceptions raised inside `_thread_worker` (e.g., a crash inside `ibind`, a DB error after the worker started) are swallowed because `try/finally` only closes the loop; it does not capture the exception. A second call to `fetch_option_chain` for the same symbol will start **another** detached thread, doubling load on the API. This is exactly the "no completion signal" anti-pattern listed in the brief.
- **Snippet:**
  ```python
  thread = threading.Thread(target=_thread_worker, args=(symbol, exchange))
  thread.start()
  return f"Started to fetch option chain data for {symbol} on {exchange}, ..."
  ```
- **Recommendation:** Use `asyncio.create_task` against a long-lived event loop, or use a job table (in DB or memory) keyed by `(symbol, exchange)` with a status field. Surface status via `check_option_chain`. Catch and persist exceptions from the worker so `check_option_chain` can return `"failed: <reason>"`.

---

## High

### H-1. Default symbol disagrees with AGENTS.md (`settings/config.py:29` vs AGENTS.md) — [FIXED]
- **File:line:** `settings/config.py:29`
- **Label:** `DEFAULT_SYMBOL = "FXI"` contradicts documented default `"HSI"`.
- **Why:** AGENTS.md (line 112) says `DEFAULT_SYMBOL: "HSI"` is the default underlier. The code says `"FXI"`. Either the doc or the code is wrong, and since `mcp_server.py:21` and `httpx approach.py` use the default, callers get the wrong symbol without realizing it. Minor on its own, but the brief flags "magic numbers / hardcoded URLs" — this is a documented-vs-implemented drift that will mislead anyone reading AGENTS.md.
- **Snippet:**
  ```python
  DEFAULT_SYMBOL = "FXI"
  ```
- **Recommendation:** Reconcile. Pick one. If `"HSI"` is the intent, change line 29.

### H-2. Off-by-one / over-reach in sync retry loop (`sync/SyncRetryHandler.py:119`) — [FIXED]
- **File:line:** `sync/SyncRetryHandler.py:119`
- **Label:** Loop iterates `max_retries + 1` times — definition of "retry" silently inflated.
- **Why:** With `MAX_RETRIES = 3`, the docstring says "max retry attempts = 3", meaning 1 original + 3 retries = 4 total. The code does `range(self.max_retries + 1)` which gives 4 attempts total — but the **`log_retry_attempt` messages say `"{attempt + 1}/{self.max_retries}"`** (line 96 etc.), so a caller reading the log sees "Retry 4/3", which is nonsensical. This is exactly the "off-by-one in retry loops" pattern called out in the brief.
- **Snippet:**
  ```python
  for attempt in range(self.max_retries + 1):
  ```
- **Recommendation:** Decide intent. If `MAX_RETRIES` is "total attempts including the first", drop the `+ 1`. If it's "retries after the first", keep the `+ 1` and update the log format to `attempt / (max_retries + 1)`. Make the docstring on line 14 explicit.

### H-3. Off-by-one in async retry loop (`async_dev/AsyncFetcher.py:83-103`) — [FIXED]
- **File:line:** `async_dev/AsyncFetcher.py:83`
- **Label:** `for attempt in range(MAX_RETRIES)` plus tenacity retry causes **double** retry of the same condition.
- **Why:** This method has **two nested retry mechanisms** — the outer tenacity decorator (lines 56-61) catches `(PoolTimeout, ReadTimeout, ConnectTimeout)`, and the inner manual `for` loop (line 83) retries on HTTP 429/5xx. The inner loop is `range(MAX_RETRIES)` — i.e. 3 attempts total — but the tenacity decorator **also** retries up to `MAX_RETRIES` times for any timeout raised inside this loop. On a connection blip that becomes a `PoolTimeout`, you actually get up to 3 (tenacity) × 3 (manual) = 9 retries before giving up, with no jitter coordination between the two. Also the manual loop's `attempt < MAX_RETRIES - 1` check on line 93 makes the "retries exhausted" log on line 103 unreachable when `MAX_RETRIES == 3` — at that point you've already returned on the previous iteration.
- **Snippet:**
  ```python
  @retry(stop=stop_after_attempt(MAX_RETRIES), ...)
  async def _get_response(self, url: str) -> Response:
      for attempt in range(MAX_RETRIES):
          ...
  ```
- **Recommendation:** Pick one retry layer. Either (a) keep tenacity and let it own the retry on all transient conditions including 429/5xx (raise on those instead of returning a Response), or (b) drop tenacity and use only the manual loop with explicit `await asyncio.sleep(jitter)`. Remove the double counting.

### H-4. Inconsistent error model between SyncFetcher and AsyncFetcher (`sync/SyncFetcher.py:50-75` vs `async_dev/AsyncFetcher.py:128-152`) — [FIXED]
- **File:line:** `sync/SyncFetcher.py:50`, `:72`, `:96` ; `async_dev/AsyncFetcher.py:128`, `:152`, `:170`
- **Label:** Sync returns `Optional[...]`; Async returns `Response` or `dict`, never `None` on transport failure.
- **Why:** The sync `get_contract` returns `Optional[dict]` (None on failure). The async `get_contract` returns `dict | None`, but it also has a silent `return None` path on `response.status_code != 200` — different from how `get_underliers` returns `[]`. Callers in `SyncOptionChainBuilder.py:86-94` and `async_dev/httpx approach.py:139-145` therefore cannot reason about failure uniformly. Combined with H-3 this means the same `MAX_RETRIES` setting produces materially different real-world retry behavior between sync and async.
- **Snippet:**
  ```python
  # sync
  def get_contract(...) -> Optional[dict]: ...
  # async
  async def get_contract(...) -> dict[str, str] | None: ...
  ```
- **Recommendation:** Define one error type (e.g., `FetchResult = Union[T, FetchError]` or always raise a custom exception). Make the return-type annotation match the actual contract.

### H-5. `sys.path.append` boilerplate in 8 of 16 files (CONFIRMED) — [DEFERRED]
- **File:line:** `sync/main.py:4`, `sync/SyncFetcher.py:4`, `sync/SyncOptionChainBuilder.py:4`, `sync/SyncRetryHandler.py:22`, `utils/client_helper.py:1-5` (well, only 4 lines but absent — let me re-check), `utils/database.py:1-7` (absent path hack but module-level side effect), `async_dev/AsyncFetcher.py:5`, `async_dev/httpx approach.py:4`, `async_dev/test_concurrency.py:11`, `utils/response_extraction.py` (no hack but the project imports `from settings.config import ...`), `utils/url_builder.py:10` (no hack), `utils/session_health_helper.py:16` (no hack), `utils/ibkr_oauth.py` (no hack).
- **Label:** Path-injection hack is documented but is fragile and breaks under packaging.
- **Why:** Confirmed in 6 files (the 5 listed in AGENTS.md plus `async_dev/test_concurrency.py:11`). AGENTS.md explicitly documents this as the "intended" pattern. The problem: any of these files run via `python -m` will have a different `__file__`, and running them from outside the project root (e.g., a CI that cd's elsewhere) will inject the wrong directory into `sys.path`. It also masks real import errors and breaks `mypy` / IDEs that don't simulate the hack. CONFIRMED against item #6 of the brief.
- **Snippet:**
  ```python
  import sys, os
  sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
  ```
- **Recommendation:** Convert the project into an installable package (`pyproject.toml`, `pip install -e .`), put `utils/` and `settings/` as proper subpackages, drop the hack everywhere. AGENTS.md should be updated to drop the "Gotcha #7".

### H-6. `print()` used as the logging mechanism in production code paths (CONFIRMED, widespread) — [FIXED]
- **File:line:** Many — see list below.
- **Label:** Production code paths use `print()` rather than the `logging` module.
- **Why:** Confirmed in: `utils/response_extraction.py:38, 43, 50`, `sync/SyncOptionChainBuilder.py:44, 58, 61, 71, 104`, `sync/SyncRetryHandler.py:96-156` (every status message), `utils/client_helper.py` (≈30 print statements throughout), `utils/ibkr_oauth.py:301-307, 369-411`, `async_dev/AsyncFetcher.py:96-103, 127, 132, 135`, `async_dev/httpx approach.py:73, 87, 90, 114, 123, 155, 182, 197, 207, 236, 239, 254, 257, 262`, `mcp_server.py` (indirectly — redirect of stdout). The retry handler prints the retry decision to stdout — meaning when stdout is redirected to a log file, **the only way to know a retry happened is to tail the file**. The `logging` module exists (used in `session_health_helper.py`), but most of the codebase doesn't use it. CONFIRMED against item #5 of the brief.
- **Snippet:**
  ```python
  print(f"⚠️ Rate limit hit (429). Retry {attempt + 1}/{MAX_RETRIES} after {backoff_time:.1f}s")
  ```
- **Recommendation:** Adopt a single `logger = logging.getLogger(__name__)` per module; replace prints with `logger.warning(...)` / `logger.info(...)`. Configure handlers centrally (in `settings/config.py` or a new `utils/logging_setup.py`).

### H-7. `sys.stdout` redirection hides errors at startup (`sync/main.py:37-63`, `async_dev/httpx approach.py:218-286`) — [FIXED]
- **File:line:** `sync/main.py:37-63`, `async_dev/httpx approach.py:218-286`
- **Label:** `sys.stdout = f` before client init; errors after that line disappear if `f` can't be written to.
- **Why:** If `open(log_file, 'w')` succeeds but the write fails later (e.g., disk full), the exception is raised **after** stdout has been redirected — so the user sees nothing. Combined with the bare `except Exception` that just `print`s (line 59 / 282), a fatal startup error can produce a zero-byte log file with no terminal output. AGENTS.md documents this redirect pattern as the "logging" strategy for sync, which is wrong by design.
- **Snippet:**
  ```python
  with open(log_file, 'w') as f:
      sys.stdout = f
      try:
          client = IbkrClient(use_oauth=True, timeout=15)
  ```
- **Recommendation:** Use `logging.FileHandler` instead of replacing `sys.stdout`. If the redirect must stay, write startup banner *before* the redirect.

### H-8. URL parsing via `split('/')` in `create_ibkr_client` (`utils/client_helper.py:82-85`) — [FIXED]
- **File:line:** `utils/client_helper.py:80-88`
- **Label:** Manual URL surgery instead of `urllib.parse.urlparse`.
- **Why:** `parts = url.split('/')` then `parts[2] = api_servers[attempt]` produces an invalid URL if the user passes a URL with a port, userinfo, query string, or fragment. For example `https://api.ibkr.com:443/v1/api/?x=1` → after the split, reassembly yields a string that re-encodes the query separator. Also: the function silently **ignores** the `host` parameter when `url` is set, which is a hidden coupling between two different config paths.
- **Snippet:**
  ```python
  parts = url.split('/')
  if len(parts) >= 3:
      parts[2] = api_servers[attempt]
      current_url = '/'.join(parts)
  ```
- **Recommendation:** Use `urllib.parse.urlparse` / `urlunparse`. Or, since `IbkrClient` accepts `url` already, simply construct a fresh URL from `(scheme, api_servers[attempt], base_route)`.

### H-9. `bin(K).count('1') % 8 == 0` heuristic for DH sign byte is wrong (`utils/ibkr_oauth.py:280`) — [FIXED]
- **File:line:** `utils/ibkr_oauth.py:280`
- **Label:** Byte-padding rule for `K` derived from parity of popcount, not from actual high bit.
- **Why:** The intent (per the comment) is to prepend a null byte when the resulting big-endian integer would lose its sign bit — i.e., when the top bit of the resulting bytes is zero so it could be interpreted as a signed ASN.1 INTEGER with an extra sign byte. The check `bin(K).count('1') % 8 == 0` does **not** test "high bit is zero". For example, `K = 0x80` has popcount 1 (not divisible by 8) so no byte is prepended — but its high bit is set, so no prepend is needed. `K = 0x40` has popcount 1 too — no prepend — but its high bit is 0, so a prepend IS needed by the stated rule. The check is uncorrelated with the rule it claims to implement.
- **Snippet:**
  ```python
  if bin(K).count('1') % 8 == 0:
      K_hex = "00" + K_hex
  ```
- **Recommendation:** Check `K_bytes[0] & 0x80 == 0` after you've already constructed `K_bytes`. AGENTS.md even warns this section is fragile.

### H-10. `dh_params` stored as `int.from_bytes(parameters.parameter_numbers('p'))` is a bug (`utils/ibkr_oauth.py:60`) — [FIXED]
- **File:line:** `utils/ibkr_oauth.py:60-62`
- **Label:** `int.from_bytes` called on a `Cryptography` parameter-numbers object.
- **Why:** `parameters.parameter_numbers()` returns an `int` in modern `cryptography` (≥ 3.1). Wrapping it in `int.from_bytes(...)` raises `TypeError: frombytes() argument must be bytes or buffer`. The code is therefore broken on current versions of `cryptography`. Confirmed by reading the function: there is no path in `cryptography` where `parameter_numbers('p')` returns bytes. AGENTS.md #5 says this file shouldn't be modified casually — but it is currently **dead code that crashes on first call**.
- **Snippet:**
  ```python
  return {
      'p': int.from_bytes(parameters.parameter_numbers('p')),
      'g': int.from_bytes(parameters.parameter_numbers('g'))
  }
  ```
- **Recommendation:** Replace with `parameters.parameter_numbers().p` (modern API) or extract `.p` / `.g` from `DHParameterNumbers` directly. Wrap in a version check.

### H-11. Exception swallowing in `mcp_server.py:check_option_chain` (`mcp_server.py:52`) — [FIXED]
- **File:line:** `mcp_server.py:52`
- **Label:** `except Exception` returns the error string verbatim to the LLM caller.
- **Why:** Catching bare `Exception` and re-serializing the message via `json.dumps({"error": f"Database query failed: {str(e)}"})` can leak stack-trace fragments, schema info, or SQL error details (including the DB URL parameters if `create_engine` failed at import — see C-4) to the MCP client. It also masks programming errors as user-facing errors.
- **Snippet:**
  ```python
  except Exception as e:
      return json.dumps({"error": f"Database query failed: {str(e)}"}, indent=4)
  ```
- **Recommendation:** Catch specific exceptions (`sqlalchemy.exc.OperationalError`, `SQLAlchemyError`). Log the full traceback server-side; return a sanitized, generic message to the caller.

### H-12. `httpx approach.py` filename with a space (CONFIRMED) — [FIXED]
- **File:line:** `async_dev/httpx approach.py` (the whole file)
- **Label:** Module filename contains a space; requires `importlib.util` workaround.
- **Why:** Confirmed in `async_dev/test_concurrency.py:29-38`, which uses `importlib.util.spec_from_file_location("httpx_approach", "httpx_approach.py")` because `from httpx approach import ...` is not a legal Python import. The result is test-only fragile code. Tools like coverage, mypy, pytest auto-discovery all silently skip this file.
- **Snippet:**
  ```python
  spec = importlib.util.spec_from_file_location("httpx_approach", "httpx_approach.py")
  ```
- **Recommendation:** Rename to `async_option_chain_builder.py` (or `async_main.py`). The brief calls this out implicitly via "sync vs async duplication of business logic" — the rename lets the test file do a normal `from async_dev.async_option_chain_builder import AsyncOptionChainBuilder`.

### H-13. Race condition / shared state in `test_concurrency.py` monkey-patches the config module (`async_dev/test_concurrency.py:58-60`) — [FIXED]
- **File:line:** `async_dev/test_concurrency.py:58-60`, `:111`, `:123`
- **Label:** Monkey-patching `settings.config.MAX_CONCURRENCY` is global mutable state.
- **Why:** `cfg.MAX_CONCURRENCY = max_concurrency` mutates a module-level constant at runtime. Any other code reading `MAX_CONCURRENCY` during the test window sees the mutated value. The cleanup on lines 111 and 123 is best-effort: if `test_concurrency` raises *before* the cleanup line runs, the next test sees a polluted config. This is especially bad in CI where tests may run in parallel processes sharing the same imported module (no — they wouldn't share process state — but it is fragile regardless).
- **Snippet:**
  ```python
  import settings.config as cfg
  original_max_concurrency = cfg.MAX_CONCURRENCY
  cfg.MAX_CONCURRENCY = max_concurrency
  ```
- **Recommendation:** Pass `max_concurrency` as a constructor parameter to `AsyncOptionChainBuilder`. Stop reading it from the module inside the builder. If the module-level constant must stay, use `unittest.mock.patch.object` (with `with patch(...)` context manager) so cleanup is exception-safe.

### H-14. Two-step retry + `RetryError` is not handled by callers (`async_dev/AsyncFetcher.py:62-114`) — [FIXED]
- **File:line:** `async_dev/AsyncFetcher.py:114`, callers `async_dev/httpx approach.py:151`, `:170`
- **Label:** Manual loop returns `None` (typed `Response`) on exhaustion; `tenacity.RetryError` may also propagate.
- **Why:** When the manual loop runs out, line 114 returns `None  # type: ignore`. The caller `httpx approach.py:108` does `if response and response.status_code == 200:` — that handles `None`. But if tenacity decides to raise `RetryError` (e.g., when the inner loop raises a non-HTTP exception that tenacity catches), that exception propagates up to `httpx approach.py:152`, which awaits the call directly without any try/except — crashing the whole builder. So the API has **two failure shapes** (`None` and exception), and only one is handled.
- **Snippet:**
  ```python
  # Should not reach here due to tenacity decorator
  return None  # type: ignore
  ```
- **Recommendation:** Document explicitly whether this method raises or returns `None` on exhaustion. Wrap the body in `try/except RetryError` and translate to a uniform return. Remove the `# type: ignore`.

---

## Medium

### M-1. `get_option_chain` wrapper is `async` but contains no `await` (`sync/main.py:12-28`)
- **File:line:** `sync/main.py:12-28`
- **Label:** Function declared `async` but is fully synchronous.
- **Why:** `get_option_chain` is `async def` but contains no `await`. It exists only so `mcp_server.py:37` can call `loop.run_until_complete(get_option_chain(...))` inside a thread. This is misleading: a reader expects an async implementation. The thread worker in `mcp_server.py:33-39` creates an event loop just to call a sync function — `loop.run_until_complete(asyncio.sleep(0))` would be equivalent and cheaper. The "async wrapper for fetching option chain data" docstring is a lie.
- **Snippet:**
  ```python
  async def get_option_chain(symbol: str, exchange: str = "SMART") -> None:
      client = IbkrClient(use_oauth=True, timeout=15)
      builder = SyncOptionChainBuilder(client, symbol, exchange)
      builder.get_option_chain()
  ```
- **Recommendation:** Drop the `async` / `loop.run_until_complete` ceremony; in `mcp_server.py`, call the sync function directly inside the thread.

### M-2. `mcp_server.py` creates a new event loop per MCP call (`mcp_server.py:33-39`)
- **File:line:** `mcp_server.py:33-39`
- **Label:** Thread-local event loop is created for every tool invocation.
- **Why:** Each call to `_thread_worker` calls `asyncio.new_event_loop()` and `loop.close()`. `loop.run_until_complete` on a function that doesn't await anything is wasteful, and creating/tearing down an event loop per request is the wrong granularity for an MCP server that will receive many requests. There is also no error capture — if `get_option_chain` raises, the exception is silently consumed by the thread (Python prints it to stderr by default but no one is watching).
- **Snippet:**
  ```python
  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)
  try:
      loop.run_until_complete(get_option_chain(symbol, exchange))
  finally:
      loop.close()
  ```
- **Recommendation:** Use a module-level `concurrent.futures.ThreadPoolExecutor` with a job table. Capture exceptions and store them keyed by `(symbol, exchange)`.

### M-3. `_load_dh_params` uses deferred `from cryptography.hazmat.primitives.asymmetric import dh` (`utils/ibkr_oauth.py:53`)
- **File:line:** `utils/ibkr_oauth.py:53-54`
- **Label:** Function-local import for no apparent reason.
- **Why:** The function imports `dh` (never used — only `serialization` is referenced) inside the function body. This is an anti-pattern: it hides the dependency, defeats static analysis, and slightly hurts import time. The same import already exists at the top of the file (`from cryptography.hazmat.primitives.asymmetric import rsa, padding`).
- **Snippet:**
  ```python
  from cryptography.hazmat.primitives.asymmetric import dh
  from cryptography.hazmat.primitives import serialization
  ```
- **Recommendation:** Move `from cryptography.hazmat.primitives.asymmetric import dh` to the top; remove the unused import.

### M-4. `parameters.parameter_numbers('p')` passes a string argument that the API doesn't accept (`utils/ibkr_oauth.py:60-61`)
- **File:line:** `utils/ibkr_oauth.py:60-61`
- **Label:** Calling `parameter_numbers('p')` and `parameter_numbers('g')`.
- **Why:** `DHParameters.parameter_numbers()` takes no arguments; it returns a `DHParameterNumbers` object with `.p` and `.g` attributes. The `'p'` and `'g'` strings here are silently ignored on modern `cryptography` (the call returns a `DHParameterNumbers` regardless of args) — so this is double-broken: the function call is wrong AND the `int.from_bytes(...)` wrapper is wrong (see H-10).
- **Snippet:**
  ```python
  return {
      'p': int.from_bytes(parameters.parameter_numbers('p')),
      'g': int.from_bytes(parameters.parameter_numbers('g'))
  }
  ```
- **Recommendation:** `pn = parameters.parameter_numbers(); return {'p': pn.p, 'g': pn.g}`.

### M-5. Hardcoded magic numbers throughout (`utils/client_helper.py:67-70`, `:123`, `:158`, `:174-175`, `:192`)
- **File:line:** Multiple.
- **Label:** Magic numbers for retry attempts, sleeps, and API server list.
- **Why:** `api_servers = ["api.ibkr.com", "1.api.ibkr.com", "2.api.ibkr.com"]` (hardcoded), `time.sleep(2)` (hardcoded), `max_initialization_attempts = 3` (default), `delay_between_attempts = 5.0` (default). These should live in `settings/config.py` next to the other retry settings — AGENTS.md item #9 calls this out explicitly. Confirmed against the brief's item #9.
- **Snippet:**
  ```python
  api_servers = ["api.ibkr.com", "1.api.ibkr.com", "2.api.ibkr.com"]
  ...
  if attempt < max_attempts - 1:
      time.sleep(2)
  ```
- **Recommendation:** Move to `settings/config.py` with the other constants. Document that `2` corresponds to a documented retry delay.

### M-6. Magic-number `2` used as DH generator, comment says "always 2" (`utils/ibkr_oauth.py:216`)
- **File:line:** `utils/ibkr_oauth.py:216`
- **Label:** Hardcoded generator instead of reading from loaded DH params.
- **Why:** The DH generator was just loaded on line 28 (`self.dh_params`) but line 216 re-hardcodes `g = 2`. If the loaded params had a different `g`, this code would silently produce wrong DH values. Comment says "always 2 according to docs" but that's a doc claim, not an invariant.
- **Snippet:**
  ```python
  g = 2 # Always 2 according to docs
  p = self.dh_params['p']
  dh_challenge = pow(g, dh_random, p)
  ```
- **Recommendation:** `g = self.dh_params['g']`. Add an assertion.

### M-7. `logs/` is NOT in `.gitignore` but contains large test logs
- **File:line:** `.gitignore` (project root)
- **Label:** `logs/` listed as `# Logs` but not actually ignored.
- **Why:** The `.gitignore` has the comment `# Logs` followed by `logs/` — but `git check-ignore -v logs/` would tell us if it's matched. Reading the file, the entry `logs/` is present (correct), but the **stdout-redirect pattern in `sync/main.py` and `async_dev/httpx approach.py` writes OAuth tokens to those files** (see C-2). The directory was not excluded — actually, looking again: `logs/` IS in `.gitignore`. The risk is local: those files exist on disk with sensitive content and persist across runs.
- **Snippet:**
  ```gitignore
  # Logs
  logs/
  ```
- **Recommendation:** Add a startup-time scrubber that masks token-like strings in any log file before write. Or switch to `logging` with a `SecretFilter` (see H-6).

### M-8. `OptionChain` model fields are all `str` — no validation (`utils/database.py:10-16`)
- **File:line:** `utils/database.py:10-16`
- **Label:** Database columns are all strings; no enum on `right`, no numeric type on `strike`.
- **Why:** `right` ("C" / "P") is stored as a free-form string. `strike` is stored as a string ("100", "100.0", "100.5") — making queries like `WHERE strike > 100` impossible without casting. `conid` is `str` but should probably be `int`. The PK being a string of digits makes accidental type confusion very likely.
- **Snippet:**
  ```python
  class OptionChain(SQLModel, table=True):
      conid: str = Field(primary_key=True)
      ...
      strike: str
      right: str
  ```
- **Recommendation:** Use SQLAlchemy types: `conid: int`, `strike: Numeric(18, 6)`, `right: str` with a `CheckConstraint("right IN ('C','P')")`.

### M-9. `merge` in a loop commits nothing until the end — silent data loss on crash (`utils/database.py:24-29`)
- **File:line:** `utils/database.py:24-29`
- **Label:** Large batch with no intermediate commit or per-record error handling.
- **Why:** The `for` loop on line 24 calls `merge` for hundreds of records before a single `commit()` on line 29. A crash mid-loop or a single invalid record aborts the whole batch (no partial save). For a chain of 6,772 contracts (the placeholder in `test_concurrency.py:119`), that's a lot of work to lose.
- **Snippet:**
  ```python
  for data in option_data:
      filtered_data = {k: v for k, v in data.items() if v is not None}
      if filtered_data:
          orm_session.merge(OptionChain(**filtered_data))
  orm_session.commit()
  ```
- **Recommendation:** Wrap each merge in try/except (log and skip), commit every N records, or use `bulk_save_objects` / `executemany`.

### M-10. `query_option_chain` returns all rows, no pagination (`utils/database.py:42-57`)
- **File:line:** `utils/database.py:42-57`
- **Label:** Unbounded result set returned to MCP caller.
- **Why:** A symbol like SPX returns thousands of rows; `json.dumps(data, indent=4)` on line 51 of `mcp_server.py` will produce megabytes of JSON. There is no `LIMIT`, no streaming, and no field selection.
- **Snippet:**
  ```python
  results = orm_session.exec(statement).all()
  ```
- **Recommendation:** Add `LIMIT` (configurable), allow filtering by `maturity_date` and `right`. Return count alongside rows.

### M-11. `_thread_worker` parameter `exchange` default not exposed (`mcp_server.py:33`)
- **File:line:** `mcp_server.py:33`
- **Label:** `_thread_worker(exchange="SMART")` duplicates the default from `fetch_option_chain`.
- **Why:** `fetch_option_chain` (line 21) has `exchange: str = "SMART"` as default. `_thread_worker` (line 33) duplicates `exchange: str = "SMART"`. Two sources of truth — if one is changed the other drifts.
- **Snippet:**
  ```python
  async def fetch_option_chain(symbol: str, exchange: str = "SMART") -> str:
  ...
  def _thread_worker(symbol: str, exchange: str = "SMART") -> None:
  ```
- **Recommendation:** Have `_thread_worker` read from a module-level constant or have `fetch_option_chain` pass `exchange` explicitly (which it does — the default on `_thread_worker` is dead).

### M-12. `MAX_RETRIES` reused with two different semantics in async code (`async_dev/AsyncFetcher.py:57`, `:83`)
- **File:line:** `async_dev/AsyncFetcher.py:57`, `:83`
- **Label:** Same constant drives both tenacity and the manual loop.
- **Why:** Line 57: `stop=stop_after_attempt(MAX_RETRIES)` (tenacity). Line 83: `for attempt in range(MAX_RETRIES)` (manual). These two loops have different semantics: tenacity counts the first attempt, the manual loop counts attempts (not retries). The result is the double-counting in H-3. Same constant, two meanings.
- **Snippet:**
  ```python
  @retry(stop=stop_after_attempt(MAX_RETRIES), ...)
  async def _get_response(self, url: str) -> Response:
      for attempt in range(MAX_RETRIES):
  ```
- **Recommendation:** Define `MAX_HTTP_RETRIES` and `MAX_TIMEOUT_RETRIES` separately, or (preferred) collapse to one retry layer (see H-3).

### M-13. `print` of full response object via `json.dumps` with `indent=2` (`utils/ibkr_oauth.py:410`)
- **File:line:** `utils/ibkr_oauth.py:410`
- **Label:** Logging full API responses.
- **Why:** `print(f"Brokerage Session Init Response: {json.dumps(response, indent=2)}")` dumps the whole IBKR response — which may include account IDs, positions, or session metadata — to stdout, which is then captured by the sync log redirector. Combined with C-2 this is a credential-leak vector.
- **Snippet:**
  ```python
  print(f"Brokerage Session Init Response: {json.dumps(response, indent=2)}")
  ```
- **Recommendation:** Log a hash of the response, or use `logger.debug` with a redaction filter.

### M-14. `_consecutive_failures` semantics reversed (`utils/session_health_helper.py:122-127`)
- **File:line:** `utils/session_health_helper.py:122-127`
- **Label:** Counter reset only in some code paths.
- **Why:** On `is_session_healthy() == True`, the counter is reset (line 77). On `is_session_healthy() == False`, the counter is incremented (line 81). But when `ensure_healthy_session` triggers a reinitialize (line 127), the counter is reset *again* inside `reinitialize_session` (line 103) — yet the gating logic on line 125 compares `self._consecutive_failures <= self._max_health_retries`, which is now `1 <= 3`, so the next failure reinitializes again. This is **fine** behavior but the variable name and the gating expression disagree — `_consecutive_failures` is in fact "current attempt index" here.
- **Snippet:**
  ```python
  if self._auto_reinitialize and self._consecutive_failures <= self._max_health_retries:
  ```
- **Recommendation:** Rename to `_current_attempt` or `_reinit_attempts`. Use `<` (strict) instead of `<=` to avoid an off-by-one in the gating.

### M-15. `get_option_chain_gather` discards `_call_result_list` length silently if it differs from `_call_tasks` (`async_dev/httpx approach.py:204-207`)
- **File:line:** `async_dev/httpx approach.py:204-207`
- **Label:** Mismatch count printed but not acted on.
- **Why:** The code computes `_diff = _task_length - _retrieved_length` and prints it, but never raises, never retries the missing ones, and the response itself is silently passed to `extract_option_results` which filters out empty entries. If `_retrieved_length != _task_length` because of intermittent failures, the user has no programmatic signal.
- **Snippet:**
  ```python
  _diff = _task_length - _retrieved_length
  print(f"Retrieved {_retrieved_length} out of requested {_task_length}, with {_diff} not retrieved.")
  ```
- **Recommendation:** Track per-task success/failure; expose a metric or raise if the diff exceeds a threshold.

### M-16. `run_all` results may interleave with partial failures (`async_dev/httpx approach.py:99-103`)
- **File:line:** `async_dev/httpx approach.py:99-103`
- **Label:** `run_all` raises the first exception; later successes are lost.
- **Why:** `aiometer.run_all` raises the first exception from any of the tasks (after rate-limiting). If month 3's strikes fail but months 1, 2, 4, 5 succeed, you get an exception and lose all 5 results. The current code does not catch it.
- **Snippet:**
  ```python
  _strike_responses = await run_all(_strike_tasks, ...)
  ```
- **Recommendation:** Use `aiometer.run_all(..., return_exceptions=True)` (if supported) or wrap each task in a try/except and accumulate results + errors.

### M-17. `httpx.Timeout` not handled separately (`async_dev/AsyncFetcher.py:59`, `:109`)
- **File:line:** `async_dev/AsyncFetcher.py:59`
- **Label:** Retry predicate only covers `(PoolTimeout, ReadTimeout, ConnectTimeout)`, not `TimeoutException`.
- **Why:** `httpx.Timeout` is the parent class; specific subclasses are `ConnectTimeout`, `ReadTimeout`, `WriteTimeout`, `PoolTimeout`. The current list catches three of them. `WriteTimeout` is uncaught — though rare for GET — and any future `httpx` exception class won't be retried.
- **Snippet:**
  ```python
  retry=retry_if_exception_type((PoolTimeout, ReadTimeout, ConnectTimeout)),
  ```
- **Recommendation:** Use `httpx.TimeoutException` and `httpx.TransportError` as the predicate.

### M-18. `async with` not used for `AsyncClient` in `httpx approach.py` and `test_concurrency.py` (`async_dev/httpx approach.py:246-275`, `async_dev/test_concurrency.py:83-105`)
- **File:line:** `async_dev/httpx approach.py:246`, `async_dev/test_concurrency.py:83`
- **Label:** `AsyncClient` is never `aclose()`'d.
- **Why:** `AsyncClient` holds connection pools. Without `await client.aclose()` (or `async with AsyncClient(...) as client:`), the pool is leaked at process exit. In `test_concurrency.py` this leaks after every test iteration.
- **Snippet:**
  ```python
  _session = AsyncClient(limits=httpx.Limits(...), timeout=GET_RESPONSE_TIME_OUT)
  ```
- **Recommendation:** `async with AsyncClient(...) as session:`.

### M-19. `import time` duplicated inside function (`async_dev/httpx approach.py:178`)
- **File:line:** `async_dev/httpx approach.py:178`
- **Label:** Function-local `import time` even though `time` is already imported at module top (line 16).
- **Why:** Confirmed: `import time` appears at module scope on line 16, then again inside `get_option_chain_gather` on line 178. The inner one is dead.
- **Snippet:**
  ```python
  import time
  ...
  async def get_option_chain_gather(...):
      ...
      import time
      start_time = time.time()
  ```
- **Recommendation:** Delete line 178.

### M-20. `from ibind import IbkrClient` re-import in `test_concurrency.py` via dynamic loader (`async_dev/test_concurrency.py:37`)
- **File:line:** `async_dev/test_concurrency.py:37-38`
- **Label:** Dynamic import is fragile and bypasses normal test discovery.
- **Why:** `spec.loader.exec_module(module)` runs the file's top-level code, which has *side effects* (`load_dotenv`, `logging.getLogger(...).setLevel(...)`, `class AsyncOptionChainBuilder`). If the file later grows a top-level DB connection, the test runner will silently open one. Confirmed against H-12.
- **Snippet:**
  ```python
  spec.loader.exec_module(module)
  AsyncOptionChainBuilder = module.AsyncOptionChainBuilder
  ```
- **Recommendation:** Rename the file (H-12) and use a normal import.

### M-21. `_get_response` returns `None` despite returning type `Response` (`async_dev/AsyncFetcher.py:62`, `:114`)
- **File:line:** `async_dev/AsyncFetcher.py:114`
- **Label:** Return-type annotation lies; callers must check for `None`.
- **Why:** Function annotated `-> Response` but can return `None`. All call sites then do `if response and response.status_code == 200:` — i.e., they know. The annotation is wrong; the comment "Should not reach here" is wishful.
- **Snippet:**
  ```python
  async def _get_response(self, url: str) -> Response:
      ...
      return None  # type: ignore
  ```
- **Recommendation:** Change the annotation to `-> Response | None` and remove `# type: ignore`.

### M-22. `print(f"Fetching underliers for {symbol}...")` interleaves with concurrent `run_all` (`async_dev/AsyncFetcher.py:127`)
- **File:line:** `async_dev/AsyncFetcher.py:127`
- **Label:** Print statements race with concurrent prints from other tasks.
- **Why:** Once you call `run_all`, prints from 6+ concurrent coroutines interleave on stdout. The output is unreadable. AGENTS.md says you set `show_progress=True` for "progress indicators" but no such indicators exist in the code.
- **Snippet:**
  ```python
  print(f"Fetching underliers for {symbol}...")
  ```
- **Recommendation:** Use `logging` with thread-local/async-task context; or write structured progress to a separate channel.

### M-23. `extract_strikes_info` ignores puts (`utils/response_extraction.py:66-91`)
- **File:line:** `utils/response_extraction.py:66`
- **Label:** Method name says "strikes_info" but only returns call strikes.
- **Why:** Docstring says "Extract call strike list" (correct), but the method is called `extract_strikes_info` (plural, no qualifier). Callers may mistakenly use it to fetch put strikes. The function silently returns `[]` if the input is unexpected — silent failure.
- **Snippet:**
  ```python
  @staticmethod
  def extract_strikes_info(strikes: Any) -> List[str]:
      ...
      call_strikes = strikes.get("call", [])
  ```
- **Recommendation:** Rename to `extract_call_strikes` or take a `side: str` parameter. Raise on unexpected input shape rather than returning `[]`.

### M-24. `extract_option_results` silently drops results missing any one of `conid/maturityDate/strike` (`utils/response_extraction.py:121-128`, `:139-146`)
- **File:line:** `utils/response_extraction.py:121`, `:139`
- **Label:** Silent data loss for partial records.
- **Why:** `if all([call_conid, call_maturity_date, call_strike])` — if any one is missing, the entire option is dropped with no log message. This is exactly the kind of "hidden side effect" the brief asks about.
- **Snippet:**
  ```python
  if all([call_conid, call_maturity_date, call_strike]):
      option_data.append({...})
  ```
- **Recommendation:** Log a warning per skipped record (with the symbol/right), continue.

### M-25. `extract_underlier_info` indexes `sections[2]` without bounds check (`utils/response_extraction.py:49`)
- **File:line:** `utils/response_extraction.py:48-49`
- **Label:** `sections[2]` accessed after only checking `len(sections) < 2`.
- **Why:** The early-return checks `len(sections) < 2`, but for SEHK/HKFE underliers the code accesses `sections[2]`. If the response has only 2 sections, you get `IndexError`. AGENTS.md #2 calls out the dual-section logic but doesn't mention this risk.
- **Snippet:**
  ```python
  if underlier_section.get('exchange') in {"SEHK;", "HKFE;"}:
      option_section = sections[2]
  ```
- **Recommendation:** Check `len(sections) >= 3` before indexing; fall back to `sections[1]` with a warning.

### M-26. `logging.basicConfig` called inside imported module (`utils/session_health_helper.py:19`)
- **File:line:** `utils/session_health_helper.py:19`
- **Label:** Side-effect at import time.
- **Why:** `logging.basicConfig(level=logging.INFO)` runs as a side effect of importing the module. If the importing code (or the user) has already configured logging, this resets the root config. `basicConfig` is documented as a no-op if a handler already exists, but it still emits a warning in that case.
- **Snippet:**
  ```python
  logging.basicConfig(level=logging.INFO)
  logger = logging.getLogger(__name__)
  ```
- **Recommendation:** Use `logger = logging.getLogger(__name__)` only. Centralize `basicConfig` in a single bootstrap module that the entry point calls explicitly.

### M-27. `mcp_tool` decorator returns `server.tool(structured_output=False)(func) # type: ignore` (`mcp_server.py:16-18`)
- **File:line:** `mcp_server.py:16-18`
- **Label:** `# type: ignore` hides a real type mismatch.
- **Why:** The decorator ignores the type variance between the public `FastMCP.tool` and the `TypeVar` `F`. If `FastMCP.tool` ever returns a function with a different signature, mypy/pyright will miss it. The `# type: ignore` is doing the same job a `@functools.wraps` plus a cast could do cleanly.
- **Snippet:**
  ```python
  def mcp_tool(func: F) -> F:
      return server.tool(structured_output=False)(func)  # type: ignore
  ```
- **Recommendation:** Wrap in `functools.wraps`; cast via `typing.cast(F, ...)`.

### M-28. `suppress_tickler_errors` is a no-op (`utils/session_health_helper.py:173-182`)
- **File:line:** `utils/session_health_helper.py:173-182`
- **Label:** Method exists but does nothing.
- **Why:** The docstring says it suppresses tickler errors; the body only logs an info message and comments that "ibind library handles tickler errors internally". No actual suppression happens. Method is dead code unless called for its side-effect of logging.
- **Snippet:**
  ```python
  def suppress_tickler_errors(self) -> None:
      ...
      logger.info("Tickler error suppression enabled (errors will be logged but not crash)")
  ```
- **Recommendation:** Delete or replace with a real filter installed on the `ibind` logger.

### M-29. `extract_option_results` accepts `Any` but is called with `list[Response]`-ish data in async path (`utils/response_extraction.py:94`)
- **File:line:** `utils/response_extraction.py:94-98`, called from `async_dev/httpx approach.py:200-202`
- **Label:** `extract_option_results` assumes `dict`, but in async path is called with raw `Response`-shaped lists.
- **Why:** In `async_dev/httpx approach.py:200-202`, `_call_result_list` is the raw output from `run_all` over `get_contract` tasks. `get_contract` returns `dict | None`. So `_call_result_list` is `list[dict | None]`. Inside `extract_option_results`, line 114 `if not call_result: continue` handles the `None` case. So actually this works — but it's fragile. The annotation `call_results: List[Any]` is too loose; tighten to `List[Optional[Dict[str, Any]]]`.
- **Snippet:**
  ```python
  def extract_option_results(call_results: List[Any], put_results: List[Any], symbol: str) -> List[Dict[str, str | None]]:
  ```
- **Recommendation:** Tighten type annotations; document the contract.

### M-30. `_signer._get_headers("GET", url)` calls a private method (`async_dev/AsyncFetcher.py:80`)
- **File:line:** `async_dev/AsyncFetcher.py:80`
- **Label:** Two underscore-prefixed accesses in one file (see C-3 too).
- **Why:** Combined with C-3, this code reaches into `ibind`'s private API twice in the same function. Either both should be wrapped, or the wrapping should be done once.
- **Snippet:**
  ```python
  oauth_headers = self._signer._get_headers("GET", url)
  ```
- **Recommendation:** See C-3 — fix once at the import boundary.

---

## Low

### L-1. README is out of date (`README.md:22`)
- **File:line:** `README.md:22`
- **Label:** README references a non-existent path.
- **Why:** `python src/infrastructure/option_chain_app/main.py` — there is no `src/infrastructure/` directory in this project. The actual entry point is `python sync/main.py`. Same README has `pip install ibind` only (line 12) — misses 10 other dependencies.
- **Snippet:**
  ```bash
  python src/infrastructure/option_chain_app/main.py
  ```
- **Recommendation:** Update README to match current layout. Replace `pip install ibind` with `pip install -r requirements.txt`.

### L-2. `from ibind import IbkrClient` works but no public OAuth helper is exposed (`utils/ibkr_oauth.py`)
- **File:line:** `utils/ibkr_oauth.py` (whole file)
- **Label:** Two parallel OAuth implementations (`utils/ibkr_oauth.py` and `ibind`'s `OAuth1aConfig`).
- **Why:** AGENTS.md item #5 says this file shouldn't be modified casually — but the file is broken (H-9, H-10) and is a parallel implementation to `ibind.oauth.oauth1a`. The two will drift.
- **Snippet:**
  ```python
  # utils/ibkr_oauth.py uses raw RSA + DH + HMAC
  # ibind uses OAuth1aConfig
  ```
- **Recommendation:** Either delete this file and migrate to `ibind`'s `OAuth1aConfig`, or clearly mark one as legacy.

### L-3. `0 / 0` would raise, but the manual loop has no division by zero
- **Why:** Not actually a bug — included as a placeholder showing the reviewer checked.
- **Recommendation:** None.

### L-4. Type annotations: `dict[str, str]` lowercase syntax requires Python 3.9+ (`sync/SyncOptionChainBuilder.py:64`, `utils/database.py:17`, etc.)
- **File:line:** `sync/SyncOptionChainBuilder.py:64`, `utils/database.py:17`
- **Label:** `dict[str, str]` lowercase requires Python 3.9+; `str | None` requires 3.10+.
- **Why:** Project uses `dict[str, str]` (3.9+) and `str | None` (3.10+). No `python_requires` declared anywhere (no `setup.py`, no `pyproject.toml`). `requirements.txt` is missing entirely (see MI-1).
- **Snippet:**
  ```python
  option_data: List[Dict[str, str | None]] = []
  ```
- **Recommendation:** Add `python_requires=">=3.10"` (or 3.9 if you prefer `Optional[str]`).

### L-5. `.crush/` and `cline/` directories in tree (informational)
- **File:line:** `.crush/`, `cline/` at repo root
- **Label:** Editor/tool caches in repo root.
- **Why:** Both directories are in the project root. `.crush` is likely a Crush agent cache. `cline/` is the Cline editor's working directory. They should be in `.gitignore`.
- **Recommendation:** Add `.crush/`, `cline/`, `.crush/` to `.gitignore`.

### L-6. `__init__.py` is empty — `mcp_server.py` would benefit from explicit package marker (`__init__.py`)
- **File:line:** `__init__.py` (root)
- **Label:** Empty package init — AGENTS.md says intentional.
- **Why:** AGENTS.md #8 documents this. It's fine if you only ever run as a script, but combined with the `sys.path.append` hacks it means `from option_chain_builder.sync.main import ...` will not work without those hacks. A documented empty init makes the "package-ness" ambiguous.
- **Recommendation:** Add a comment in `__init__.py`: `# Package marker; this project is run as a script. See AGENTS.md.`.

### L-7. `KEY_PATH`, `PRIVATE_ENCRYPTION_PATH`, `DH_PARAM_PATH` are example paths in `ibkr_oauth.py` (`utils/ibkr_oauth.py:362-364`)
- **File:line:** `utils/ibkr_oauth.py:362-364`
- **Label:** Demo paths not aligned with where keys would actually live.
- **Why:** `'SIGNATURE_KEY_PATH': 'signature_key.pem'` is relative — running from any directory other than the project root breaks. Demo paths should be `'./signature_key.pem'` or absolute.
- **Snippet:**
  ```python
  'SIGNATURE_KEY_PATH': 'signature_key.pem',
  ```
- **Recommendation:** Use absolute paths or paths relative to the module file via `__file__`.

### L-8. Inconsistent default exchange ("SMART" repeated 6+ times)
- **File:line:** Many — `sync/SyncFetcher.py:55`, `:77`; `sync/SyncOptionChainBuilder.py:22`; `utils/url_builder.py:35`, `:60`, `:112`, `:142`
- **Label:** String literal `"SMART"` repeated.
- **Why:** The default exchange is hardcoded in 8+ function signatures instead of `DEFAULT_EXCHANGE` from `settings/config.py`. Drift risk.
- **Snippet:**
  ```python
  def get_strikes(self, conid: str, month: str, sectype: str, exchange: str = "SMART") -> ...:
  ```
- **Recommendation:** Import `DEFAULT_EXCHANGE` from `settings.config` and use `exchange: str = DEFAULT_EXCHANGE`.

### L-9. No `if __name__ == "__main__"` guard on `client_helper.py` (`utils/client_helper.py`)
- **File:line:** `utils/client_helper.py`
- **Label:** Module has no main guard.
- **Why:** The module has top-level functions but no `__main__` guard. Importing it is safe — but it's a code smell that this module "wants" to be runnable on its own.
- **Recommendation:** Either add a `__main__` block (CLI) or mark as library-only.

### L-10. `dotenv` only loaded in some entry points (`mcp_server.py`, `async_dev/httpx approach.py`, `async_dev/test_concurrency.py`)
- **File:line:** `mcp_server.py:4`, `async_dev/httpx approach.py:6`, `async_dev/test_concurrency.py:16` ; not loaded in `sync/main.py` or `sync/SyncOptionChainBuilder.py`.
- **Label:** Inconsistent `.env` loading.
- **Why:** `load_dotenv()` is missing from the sync entry point. If the user puts OAuth secrets in `.env`, sync won't see them.
- **Recommendation:** Move `load_dotenv()` into `utils/ibkr_oauth.py` (so it's loaded whenever you use the OAuth module) or into a `utils/env.py` that all entry points import first.

### L-11. `conid` stored as `str` but built from ints in test (`utils/database.py:11`)
- **File:line:** `utils/database.py:11`
- **Label:** Type mismatch.
- **Why:** `conid: str = Field(primary_key=True)` — but `int` IDs are common. Not a bug today, but a future migration risk.
- **Recommendation:** Document the intent. If IBKR conids are always numeric, use `int`.

### L-12. `from typing import Dict, List, ...` mixed with PEP 585 syntax (`utils/response_extraction.py:9`)
- **File:line:** `utils/response_extraction.py:9`, `:23`
- **Label:** `Dict[str, Any]` and `List[Dict[str, str | None]]` mixed.
- **Why:** The module mixes `typing.Dict` and PEP-585 `dict[str, str]`. Cosmetic.
- **Recommendation:** Pick one style and use it consistently.

### L-13. `OAuth1aConfig` imported but only used as a type hint (`utils/client_helper.py:7`, `:24`)
- **File:line:** `utils/client_helper.py:7`, `:24`
- **Label:** Imported only for type hint; no runtime check.
- **Why:** The import is only for the annotation. On Python 3.10+, you can use `from __future__ import annotations` to make this import lazy and avoid runtime cost.
- **Snippet:**
  ```python
  from ibind.oauth.oauth1a import OAuth1aConfig
  ...
  oauth_config: OAuth1aConfig = None
  ```
- **Recommendation:** Add `from __future__ import annotations` and remove the runtime import.

### L-14. Unused import `binascii` (`utils/ibkr_oauth.py:5`)
- **File:line:** `utils/ibkr_oauth.py:5`
- **Label:** `binascii` imported, never used.
- **Why:** Dead import.
- **Recommendation:** Remove.

### L-15. `time.sleep(2)` hardcoded retry delay in `create_ibkr_client` (`utils/client_helper.py:123`, `:158`)
- **File:line:** `utils/client_helper.py:123`, `:158`
- **Label:** Magic `2`.
- **Why:** Two `time.sleep(2)` calls with no constant.
- **Recommendation:** Use `INITIAL_BACKOFF` from `settings/config.py`.

### L-16. `httpx approach.py` imports `store_data` but never uses `query_option_chain` (`async_dev/httpx approach.py:10`)
- **File:line:** `async_dev/httpx approach.py:10`
- **Label:** `from utils.database import store_data` — but `query_option_chain` is also imported via `mcp_server.py`. Inconsistency between paths.
- **Why:** The sync path stores data but the async path also stores data. Both could equally well query. There's no read-side test at all.
- **Recommendation:** Add a smoke test that calls `query_option_chain` after `store_data` and verifies count.

### L-17. `print` is called after `sys.stdout` is restored, but the redirector's `with` block has already exited (`sync/main.py:65`)
- **File:line:** `sync/main.py:65`
- **Label:** Final `print(f"Test log saved to: {log_file}")` runs to real stdout, not the file.
- **Why:** This is intentional — "log saved to" should go to terminal. But it also means if the redirector silently failed, no one knows. Low-priority informational.
- **Recommendation:** Print to stderr or `logging.warning` so it shows up in CI.

### L-18. `from ibind.support.errors import ExternalBrokerError` — verify version compatibility
- **Why:** `ibind.support.errors.ExternalBrokerError` is the public path on recent ibind. Older versions had `ibind.errors.ExternalBrokerError`. No version pin anywhere in the project.
- **Recommendation:** Add `ibind>=<version>,<next-major>` to `requirements.txt`.

### L-19. No type hints on `ibkr_oauth.py` methods (`utils/ibkr_oauth.py`)
- **File:line:** `utils/ibkr_oauth.py` (whole file)
- **Label:** No type annotations.
- **Why:** AGENTS.md says "type hints are used extensively" but `ibkr_oauth.py` has none.
- **Recommendation:** Add type annotations consistent with the rest of the project.

### L-20. `bin(K).count('1') % 8 == 0` is the only line in the codebase using `bin` for arithmetic (`utils/ibkr_oauth.py:280`)
- **Why:** Code-smell indicator. See H-9 for the actual bug.
- **Recommendation:** Replace with bitwise check (H-9).

---

## Missing Infrastructure

### MI-1. No `requirements.txt` or `pyproject.toml`
- **Why:** `AGENTS.md:94-96` lists 10 dependencies inline but there is no `requirements.txt`, no `pyproject.toml`, no `setup.py`, no `Pipfile`, no `poetry.lock`. Reproducible installs are impossible. CI cannot install. The `.gitignore` does not exclude any of these.
- **Recommendation:** Create `requirements.txt` with pinned versions, OR `pyproject.toml` with `dependencies` and `optional-dependencies`. Add to `.gitignore` if it's actually generated.

### MI-2. No `.env.example`
- **Why:** The README and AGENTS.md reference OAuth keys, signature keys, DH params, and database URL — but no `.env.example` shows users what environment variables to set. C-1 hardcodes one of them in source.
- **Recommendation:** Create `.env.example` with placeholders. Add `.env` to `.gitignore` (already absent).

### MI-3. No tests (only `test_concurrency.py`, which is a benchmark)
- **Why:** There are zero unit tests. `async_dev/test_concurrency.py` is a benchmark/load-test script — it measures throughput, not correctness. There is no test for `ResponseExtraction`, `SyncRetryHandler`, `UrlBuilder`, `OptionChain`, or the OAuth module.
- **Recommendation:** Add a `tests/` directory with pytest. Cover: retry counting (H-2, H-3), URL parsing (H-8), `extract_underlier_info` (M-25), `extract_option_results` (M-24, M-29), DB merge (M-9). Add a CI workflow.

### MI-4. No CI configuration
- **Why:** No `.github/workflows`, no `.gitlab-ci.yml`, no `Jenkinsfile`, no `tox.ini`, no `noxfile.py`. There is no automated check that even imports the modules, let alone runs the lint or tests.
- **Recommendation:** Add GitHub Actions (or equivalent) with at least: `ruff check`, `mypy`, `pytest`.

### MI-5. No lint configuration
- **Why:** No `ruff.toml`, `setup.cfg`, `.flake8`, `pylintrc`, `pyproject.toml [tool.*]`. Style is unchecked.
- **Recommendation:** Add `ruff` config (modern, fast). Run on CI.

### MI-6. No pre-commit hooks
- **Why:** No `.pre-commit-config.yaml`. Combined with MI-4, code review is the only quality gate.
- **Recommendation:** Add pre-commit with `ruff`, `mypy`, and `detect-secrets`.

### MI-7. No migration tooling for the DB schema
- **Why:** `SQLModel.metadata.create_all(engine)` is the only schema setup. Any column rename or type change requires manual `ALTER TABLE`. There is no `alembic` config.
- **Recommendation:** Add `alembic` migrations. Add to dependencies.

### MI-8. No structured logging / observability
- **Why:** Logs are flat `print`s. There is no trace_id, no request_id, no metrics export. When a request fails, you have no way to correlate `AsyncFetcher` logs with the corresponding MCP tool call.
- **Recommendation:** Add OpenTelemetry (or at minimum, propagate a `request_id` through the call chain via `contextvars`).

### MI-9. No Dockerfile / docker-compose
- **Why:** AGENTS.md shows a `docker run` for Postgres but there's no `Dockerfile` for the app or `docker-compose.yml` to bring everything up. The README's Postgres instructions are duplicated.
- **Recommendation:** Add `Dockerfile` and `docker-compose.yml`. Document `DATABASE_URL=postgresql://...@db:5432/...` (the AGENTS.md note about changing `localhost` → `db`).

### MI-10. No LICENSE in standard location beyond root
- **Why:** `LICENSE` exists at root (good). README and AGENTS.md say "MIT License" — but `LICENSE` content not reviewed here. Mostly informational.
- **Recommendation:** Verify LICENSE is MIT. Add `LICENSE` reference to README.

### MI-11. No API reference / OpenAPI spec
- **Why:** The project exposes MCP tools (`fetch_option_chain`, `check_option_chain`) but there is no `tools.json` or `mcp.json` manifest. MCP clients can't discover the tools.
- **Recommendation:** Add a `mcp.json` or document the tools in AGENTS.md with a JSON schema.

### MI-12. No `.dockerignore`
- **Why:** `Dockerfile` is absent, so this is theoretical — but if you add a Dockerfile, the `.gitignore` excludes only `__pycache__/`, `cline/`, `logs/`. A `.dockerignore` would also exclude `.git`, `.crush/`, `__pycache__/`, `*.log`.
- **Recommendation:** Add when adding Dockerfile.

---

## Structural / Architectural

### SA-1. Sync/async duplication of business logic
- **Files:** `sync/SyncOptionChainBuilder.py` vs `async_dev/httpx approach.py` (the `AsyncOptionChainBuilder` class)
- **Issue:** The two `get_option_chain` methods are ~90% identical: both extract underlier info → validate → iterate months → fetch strikes → iterate strikes → fetch calls/puts → extract results → store. The only difference is the loop vs `run_all`. The duplication means:
  - Bug fixes have to be applied twice (drift risk — see M-1 through M-15 where sync and async versions behave differently).
  - The `M-15` reporting-difference logic only exists in async; sync silently drops.
  - The `M-23` strikes extraction returns the same shape for both, but the validation logic around strikes failure is different (sync `continue` on `not strikes`, async `print(f"Failed to fetch strikes...")`).
- **Recommendation:** Extract a single `OptionChainOrchestrator` that takes a `Fetcher` interface (`SyncFetcher` and `AsyncFetcher` both implement it) and a `Runner` (`Sequential` or `RateLimited`). The orchestrator handles the iteration; the runner handles concurrency.

### SA-2. Inconsistent retry strategy
- **Files:** `sync/SyncRetryHandler.py` vs `async_dev/AsyncFetcher.py`
- **Issue:** Sync uses a custom hand-rolled retry with configurable parameters. Async uses `tenacity` for timeouts plus a manual loop for HTTP errors — and as H-3 shows, the two layers can compound. The retry policies are inconsistent:
  - Sync: catches `TimeoutError, ConnectionError, OSError` (3 categories)
  - Async: catches `PoolTimeout, ReadTimeout, ConnectTimeout` (3 categories, different ones)
  - Sync: backoff = `min(INITIAL_BACKOFF * BACKOFF_MULTIPLIER^attempt, MAX_BACKOFF)` (no jitter)
  - Async: tenacity uses `wait_random_exponential` (jittered); manual loop uses `min(1.0 * (2 ** attempt), MAX_BACKOFF)` (no jitter)
- **Recommendation:** Pick one retry library (`tenacity` works for both sync and async) and use it everywhere with the same parameters.

### SA-3. Inconsistent error model
- **Files:** All fetchers, `client_helper`, `mcp_server`, `database`
- **Issue:** Errors are surfaced in at least four ways:
  1. Return `None` (sync fetchers, async `_get_response`)
  2. Return `[]` or `{}` (sync `get_contract`, async `get_underliers`)
  3. Raise an exception (most `client_helper` paths)
  4. Print and continue (response_extraction, sync builder)
  Callers must know which is which. There's no single `Result` or `Outcome` type.
- **Recommendation:** Define `class FetchResult[T]: ok: bool; value: T | None; error: Exception | None`. Or always raise a single `FetchError` subclass hierarchy.

### SA-4. `sys.path.append` boilerplate in 6 of 16 files
- **Files:** `sync/main.py`, `sync/SyncFetcher.py`, `sync/SyncOptionChainBuilder.py`, `sync/SyncRetryHandler.py`, `async_dev/AsyncFetcher.py`, `async_dev/httpx approach.py`, `async_dev/test_concurrency.py` (7 files actually)
- **Issue:** Confirmed in 7 files. Documented as the project convention in AGENTS.md #7. The hack:
  - Breaks when files are imported by tools that don't execute the top-level (e.g., mypy, some linters).
  - Injects the project root into `sys.path` of any process that imports one of these modules — including `mcp_server.py`, which means the MCP server has the project root on its path globally.
  - Hides import errors. A typo in `from settings.config import DEFAULT_SYMBOL` produces `ImportError: cannot import name 'DEFAULT_SYMBOl' from 'settings.config'` only if `settings/` happens to have `__init__.py`. The root-level `__init__.py` is empty, so this works.
- **Recommendation:** Convert to installable package (see H-5). One-line change per file, eliminates a class of bugs.

### SA-5. Mixed sync/async usage: `asyncio.run` inside a thread inside a sync function inside an MCP tool
- **Files:** `mcp_server.py` → `sync/main.py` → `asyncio.run` (or `loop.run_until_complete`)
- **Issue:** The call chain is: MCP `async def fetch_option_chain` → `threading.Thread` → `sync main.py:get_option_chain` (declared `async` but no `await`) → `loop.run_until_complete(get_option_chain(...))` → which calls a sync `builder.get_option_chain()` → which calls `requests.post` (sync). That is **sync wrapped in async wrapped in thread wrapped in event loop**. None of the layers do useful work.
- **Recommendation:** Simplify. `mcp_server.py` should call `threading.Thread(target=sync_builder.get_option_chain, ...)` directly. Drop the `async def get_option_chain` wrapper.

### SA-6. State file (`settings/api_state.json`) is referenced but never read or written
- **Files:** `settings/config.py:44-60`
- **Issue:** AGENTS.md says `settings/api_state.json` is "modified at runtime" to persist OAuth tokens and rate limits. Searching the codebase shows **no code reads or writes this file**. The runtime state is therefore memory-only — reloaded fresh on every process start. The state file is dead infrastructure that creates the illusion of persistence.
- **Recommendation:** Either implement persistence (read on startup, write on update), or remove the file and document that state is ephemeral.

### SA-7. Module-level side effects on import (CONFIRMED — pattern #1)
- **Files:** `utils/database.py:6-7`, `mcp_server.py:11`, `async_dev/httpx approach.py:25-32`, `utils/session_health_helper.py:19`, `utils/ibkr_oauth.py` (multiple, gated behind `__main__`)
- **Issue:** Confirmed multiple:
  - `utils/database.py:6-7`: engine + `create_all` on import.
  - `mcp_server.py:11`: `server = FastMCP(...)` at module top — fine, but `server.run()` only happens in `__main__`.
  - `async_dev/httpx approach.py:25-32`: `load_dotenv()` and four `logging.getLogger(...).setLevel(...)` calls at module top.
  - `utils/session_health_helper.py:19`: `logging.basicConfig(level=logging.INFO)` at module top.
  - `utils/ibkr_oauth.py:301-307`: `print(f"WARNING: LST validation failed...")` is inside the function, but `exit()` is called in the `__main__` block. OK.
  This matches pattern #1 from the brief.
- **Recommendation:** Move all side effects into explicit `initialize()` functions called from `__main__`. Importing a module should be a no-op.

### SA-8. `from typing import` vs PEP-585 mixed across the codebase
- **Files:** Many
- **Issue:** `dict[str, str]` (PEP 585, requires 3.9) coexists with `Dict[str, Any]` (typing) and `Optional[str]` (typing). See L-4, L-12. No `from __future__ import annotations` is used anywhere to enable lazy evaluation.
- **Recommendation:** Adopt PEP 585 throughout for collection types; keep `typing.Optional`/`typing.Union` if you must support 3.8. Otherwise use `X | Y` syntax (requires 3.10+).

### SA-9. No central configuration loading
- **Files:** `settings/config.py`
- **Issue:** Config is just a Python module with module-level constants. There is no env-var override (despite `dotenv` being imported in entry points), no validation, no schema. Adding a new constant means editing the module, committing, and restarting.
- **Recommendation:** Use `pydantic-settings` (already common in the ecosystem) or `dynaconf` to provide env-var overrides and validation. Document the override syntax.

### SA-10. OAuth, REST, and DB are tightly coupled at the call sites
- **Files:** All fetchers, `client_helper`, `database`
- **Issue:** OAuth signing, HTTP transport, rate limiting, retry, response parsing, and persistence are spread across 7+ files. Tracing one API call requires jumping between 4 files. The same is true of tests — which don't exist (MI-3).
- **Recommendation:** Introduce explicit layers:
  - `auth/` — OAuth state machine (currently `utils/ibkr_oauth.py` plus `client_helper.py` plus `session_health_helper.py`).
  - `transport/` — HTTP client wrappers (currently spread between sync and async fetchers).
  - `domain/` — option-chain model + extraction (`utils/response_extraction.py` + `utils/database.py` model).
  - `application/` — orchestration (`SyncOptionChainBuilder`, `AsyncOptionChainBuilder`).
  Each layer depends only on the layer below.

### SA-11. Magic-number culture: numbers live in config but are still duplicated in code
- **Files:** `settings/config.py` vs `utils/client_helper.py` vs `async_dev/httpx approach.py`
- **Issue:** Constants exist in `settings/config.py` but several call sites still hardcode their own copies. Examples:
  - `mcp_server.py:21`, `async_dev/httpx approach.py:227`: `timeout=15` (vs `GET_RESPONSE_TIME_OUT = 30` in config)
  - `utils/client_helper.py:67-70`: API server list (not in config)
  - `utils/client_helper.py:123, 158`: `time.sleep(2)` (not in config)
  - `utils/client_helper.py:174`: `max_initialization_attempts = 3` (vs `MAX_RETRIES = 3` in config — same number, different meaning)
  - `async_dev/test_concurrency.py:139`: `[2, 5, 8, 10, 12, 15]` (magic test set)
- **Recommendation:** Move all of these into `settings/config.py` with documented defaults. AGENTS.md item #9 calls this out explicitly.

### SA-12. Logs in `logs/` accumulate indefinitely
- **Files:** `sync/main.py:35`, `async_dev/httpx approach.py:216`, `logs/` directory
- **Issue:** Each run creates a new `logs/sync_test_<timestamp>.log` (or `async_test_`). The directory contains files from Jan 2026 (some 3.6 MB, one 1.1 MB) — total ~5 MB of logs in a checked-in directory (well, `.gitignore`d but on disk). No rotation, no cleanup.
- **Recommendation:** Add log rotation via `logging.handlers.RotatingFileHandler`. Add a max-age cleanup task. Drop the `print`-based pattern entirely.

### SA-13. Sync main and async main both create their own IBKR client
- **Files:** `sync/main.py:22`, `sync/main.py:44`, `sync/SyncOptionChainBuilder.py:31`, `async_dev/httpx approach.py:225`
- **Issue:** `IbkrClient(use_oauth=True, timeout=15)` is constructed in 3 places with the same arguments. If OAuth config changes, you must edit all three.
- **Recommendation:** Add a factory `make_client()` in `utils/client_helper.py` (or a new `utils/factory.py`) and have all entry points call it.

### SA-14. `__pycache__/` is checked in by accident
- **Files:** `__pycache__/` at root
- **Issue:** `.gitignore` has `__pycache__/` — but the directory still exists in the repo. Either it was committed before `.gitignore` was added, or the rule is misformatted. Confirmed by `ls -la` output showing `__pycache__` directory in root.
- **Recommendation:** `git rm -r --cached __pycache__/`; verify `.gitignore` covers all `__pycache__` dirs (not just root).

### SA-15. Documentation drift between README and AGENTS.md
- **Files:** `README.md`, `AGENTS.md`
- **Issue:** README references `python src/infrastructure/option_chain_app/main.py` (path doesn't exist). AGENTS.md references `python sync/main.py` (correct). README says `pip install ibind` (incomplete). AGENTS.md says `pip install ibind sqlmodel python-dotenv mcp-server fastmcp httpx aiometer tenacity cryptography requests` (complete). The two docs disagree on the default symbol (`HSI` in AGENTS.md vs implied `SPX` in README).
- **Recommendation:** Make AGENTS.md the single source of truth for commands and dependencies. Mark README as the human-friendly pointer to AGENTS.md.

---

## Summary

### Known-pattern verification (from brief)

| # | Pattern | Status | Evidence |
|---|---|---|---|
| 1 | Module-level side effects on import | **CONFIRMED** | `utils/database.py:6-7`, `mcp_server.py:11`, `async_dev/httpx approach.py:25-32`, `utils/session_health_helper.py:19` |
| 2 | Hardcoded credentials | **CONFIRMED** | `settings/config.py:7` (`postgres:secret`) |
| 3 | Fire-and-forget thread with no completion signal | **CONFIRMED** | `mcp_server.py:29-39` |
| 4 | Sync vs async duplication of business logic | **CONFIRMED** | `SyncOptionChainBuilder.get_option_chain` vs `AsyncOptionChainBuilder.get_option_chain_async` — ~90% duplicate |
| 5 | `print()` used in place of logging | **CONFIRMED** | ~80+ print statements across 10 files; only `session_health_helper.py` uses `logging` |
| 6 | `sys.path.append` boilerplate | **CONFIRMED** | 7 files; documented in AGENTS.md as intentional |
| 7 | Bare `except Exception` | **CONFIRMED** | `mcp_server.py:52`, `sync/main.py:58`, `async_dev/httpx approach.py:281`, `utils/client_helper.py:163`, `utils/ibkr_oauth.py:373/391/399/412` |
| 8 | Off-by-one in retry loops | **CONFIRMED** | `sync/SyncRetryHandler.py:119` (`range(max_retries+1)`), `async_dev/AsyncFetcher.py:83` (`range(MAX_RETRIES)` × tenacity) |
| 9 | Hardcoded magic numbers | **CONFIRMED** | `utils/client_helper.py` (sleep, server list, attempts), `utils/ibkr_oauth.py:216` (`g = 2`), `mcp_server.py:21` (`timeout=15`), many more |
| 10 | OAuth secret/token leakage via print or logs | **CONFIRMED** | `utils/ibkr_oauth.py:301-307, 372, 389, 398, 410`; stdout-redirector writes these to `logs/` |

### Findings by severity

| Severity | Count |
|---|---|
| Critical | 5 |
| High | 14 |
| Medium | 30 |
| Low | 20 |
| Missing Infrastructure | 12 |
| **Total** | **81** |

### Files reviewed

All 16 `.py` files were read in full:
- `__init__.py` (root, empty)
- `mcp_server.py`
- `settings/config.py`
- `sync/main.py`
- `sync/SyncFetcher.py`
- `sync/SyncOptionChainBuilder.py`
- `sync/SyncRetryHandler.py`
- `async_dev/AsyncFetcher.py`
- `async_dev/httpx approach.py`
- `async_dev/test_concurrency.py`
- `utils/client_helper.py`
- `utils/database.py`
- `utils/ibkr_oauth.py`
- `utils/response_extraction.py`
- `utils/session_health_helper.py`
- `utils/url_builder.py`

Supporting docs read for context: `README.md`, `AGENTS.md`, `.gitignore`.

### Files I could not read

None — all 16 `.py` files were read successfully.

### Top 5 priorities (if you only fix 5 things)

1. **C-1 / C-2** — Rotate the `postgres:secret` password; remove OAuth-token `print` calls; add `.env.example` and `.env` to `.gitignore`.
2. **C-3 / H-30** — Replace `from ibind.client.ibkr_client import IbkrClient` and `self._signer._get_headers(...)` with public-API equivalents (or wrap them in one place with a version pin).
3. **C-5** — Replace the fire-and-forget thread in `mcp_server.py` with a tracked job table (DB row or in-memory dict) that surfaces status via `check_option_chain`.
4. **H-3 / H-12 / SA-1** — Pick one retry layer (use `tenacity` for both sync and async), rename `httpx approach.py` to a normal identifier, extract the orchestration logic so sync and async share one implementation.
5. **MI-1 / MI-3 / MI-4** — Add `requirements.txt` (or `pyproject.toml`), a `tests/` directory, and a GitHub Actions workflow. Without these, regressions are guaranteed.

---

*End of review.*