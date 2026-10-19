"""Public alias for the async option-chain builder.

The original implementation lives in ``async_dev/httpx approach.py`` (a file
whose name contains a space). That name forces callers to use
``importlib.util.spec_from_file_location`` rather than a normal ``import``,
which breaks coverage tools, type checkers, and test discovery (see H-12 in
``MINI_AGENT_PLAN4B_REVIEW.md``).

This module re-exports ``AsyncOptionChainBuilder`` from that file so callers
can write::

    from async_dev.async_option_chain_builder import AsyncOptionChainBuilder

without needing the dynamic-loader workaround. The underlying file is left in
place so existing scripts that reference it directly continue to work.

Note: importing this module also runs ``importlib.util`` to load the spaced
file. The side effects of that load (``load_dotenv``, log-level configuration)
are documented in the spaced file itself.
"""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPACED_FILE = os.path.join(_HERE, "httpx approach.py")

_spec = importlib.util.spec_from_file_location(
    "async_dev._httpx_approach_legacy", _SPACED_FILE
)
if _spec is None or _spec.loader is None:
    raise ImportError(
        f"Could not locate async implementation at {_SPACED_FILE!r}. "
        "The file may have been moved; see async_dev/."
    )
_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("async_dev._httpx_approach_legacy", _module)
_spec.loader.exec_module(_module)

AsyncOptionChainBuilder = _module.AsyncOptionChainBuilder

__all__ = ["AsyncOptionChainBuilder"]