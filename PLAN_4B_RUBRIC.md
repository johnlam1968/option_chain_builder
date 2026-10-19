# Phase 0 Baseline — Code Review Rubric for `option_chain_builder`

**Author:** Hermes (independent of Mini-Agent)
**Date:** 2026-06-27
**Files reviewed:** 16 .py files, ~2,595 LOC total
**Project context:** IBKR OAuth client + sync/async option chain builders + PostgreSQL storage + MCP server

This rubric is the scoring target for Plan 4b Phase 1 (Mini-Agent review).

---

## Category A — Bugs / Correctness (Critical + High)

| ID | File:line | Issue | Severity |
|---|---|---|---|
| A1 | `utils/database.py:6-7` | `engine = create_engine(DATABASE_URL)` and `SQLModel.metadata.create_all(engine)` run at **module import time**. Any import of `utils.database` (including from `mcp_server.py`) crashes if PostgreSQL is not running. Same anti-pattern as `base.py:sys.exit(1)` in Plan 4a Phase 1 but worse because it triggers on every import, not just on missing config. | Critical |
| A2 | `utils/ibkr_oauth.py:66` | `_generate_oauth_nonce()` does `secrets.token_hex(16)[2:]`. `token_hex(16)` returns a 32-char string; `[2:]` strips the first 2 chars → **nonces are 30 chars instead of 32**. Wrong-by-construction. | High |
| A3 | `async_dev/AsyncFetcher.py:83` | Inner manual retry loop uses `for attempt in range(MAX_RETRIES):` but tenacity decorator above uses `stop_after_attempt(MAX_RETRIES)`. The two are inconsistent — tenacity sees 3 attempts (initial + 2 retries), the manual loop only sees 3 attempts (no retry after attempt=3). Off-by-one. | High |
| A4 | `mcp_server.py:29-31` | `fetch_option_chain` spawns a thread and returns immediately. There is **no way for the MCP caller to know when the thread finished** — no thread join, no Future/Event, no status file, no callback. The comment "please come back later to check" is the actual contract. This is fire-and-forget with no observability. | Critical |
| A5 | `async_dev/AsyncFetcher.py:11` | `from ibind.client.ibkr_client import IbkrClient  # type: ignore` — imports from a private submodule (`ibind.client._internal`). Will break on ibind version upgrades. | Medium |
| A6 | `utils/ibkr_oauth.py:267` | `if B_hex[0] not in '0123456789ABCDEF':` — checks uppercase hex digits but `int(B_hex, 16)` accepts both upper and lowercase. Logic is technically correct but defensive only for the wrong reason. | Low |
| A7 | `utils/client_helper.py:82-85` | URL parsing: `parts = url.split('/'); if len(parts) >= 3: parts[2] = api_servers[attempt]`. This works for simple URLs but breaks for `https://api.ibkr.com:443/v1/api/` (port gets clobbered) or URLs with basic auth. Manual URL parsing when `urllib.parse.urlparse` exists. | Medium |
| A8 | `sync/main.py:12` | `async def get_option_chain(...)` is declared async but only calls sync code (`builder.get_option_chain()` which is sync). Either drop the `async` or `await` something. The name `get_option_chain` is also re-used for the sync method on `SyncOptionChainBuilder`, creating confusing two-methods-same-name pattern. | High |
| A9 | `mcp_server.py:33-39` | `_thread_worker` creates a new event loop and runs `loop.run_until_complete(get_option_chain(...))`. But `get_option_chain` in `sync/main.py` is `async def` — calling it via `run_until_complete` works, but the function never `await`s anything (it just calls sync code). The new event loop is pure overhead. | Medium |
| A10 | `async_dev/test_concurrency.py:119` | `"total_contracts": 6772` is a **hardcoded placeholder** — the test always reports 6772 contracts regardless of actual result. The result dict is fake. | High |
| A11 | `utils/database.py:24-28` | `filtered_data = {k: v for k, v in data.items() if v is not None}` — drops fields where value is None. But the `OptionChain` model has `conid` as primary key with `str` type. If a contract has `conid=None`, the `merge` call will fail with `IntegrityError` (cannot insert NULL). No defensive check. | High |
| A12 | `utils/ibkr_oauth.py:132` | Hardcoded `User-Agent: python/3.8`. The OAuth library user is presumed to be on Python 3.8 specifically. If they're on 3.11 (this project requires it), the UA is a lie. | Low |
| A13 | `utils/response_extraction.py:48` | `if underlier_section.get('exchange') in {"SEHK;", "HKFE;"}:` — magic strings with trailing semicolons. The IBKR API may return `"SEHK"` without the semicolon; the check would miss it. Fragile string matching. | Medium |
| A14 | `sync/SyncOptionChainBuilder.py:47` | `underlier = underliers[0]` — silently picks the first underlier if multiple match. For ambiguous symbols, this may pick the wrong contract. Should at minimum log a warning when multiple underliers exist. | Medium |
| A15 | `utils/session_health_helper.py:157-165` | `wrap_operation` catches `ExternalBrokerError`, then **silently calls `reinitialize_session()` and returns `None`** — the caller has no idea the operation failed vs. succeeded with a None result. This makes errors invisible. | High |

## Category B — Security

| ID | File:line | Issue | Severity |
|---|---|---|---|
| B1 | `settings/config.py:7` | `DATABASE_URL = "postgresql+psycopg://postgres:secret@localhost:5432/options_db"` — **hardcoded credentials in source**. The password is literally "secret". Should be `os.environ.get("DATABASE_URL")`. | Critical |
| B2 | `settings/config.py:16` | `IBKR_BASE_URL = "https://api.ibkr.com/v1/api/"` hardcoded. Acceptable but should be configurable per environment (production vs sandbox). | Low |
| B3 | `utils/ibkr_oauth.py:299-303` | `validation_h.hex() != lst_sig` comparison. If validation fails, only `print()`s a warning. **No exception raised, no fail-closed behavior**. Production LST could be invalid and the code would proceed to use it. | High |
| B4 | `utils/ibkr_oauth.py:386` | `print(f"https://interactivebrokers.com/authorize?oauth_token={request_token}")` — prints the **request token to stdout**. If logs are captured, the token is leaked. Should at minimum redact. | Medium |
| B5 | `settings/api_state.json` (referenced) | Runtime state file stores OAuth token state. Per AGENTS.md, it's modified at runtime. No file permissions enforcement mentioned. If `umask 022` is the default, the file is world-readable. | Medium |
| B6 | `mcp_server.py:52-53` | `check_option_chain` catches `Exception` and returns `f"Database query failed: {str(e)}"`. The DB error message (which may include schema details, table names, column types) is leaked to the MCP caller. Information disclosure. | Medium |

## Category C — Code Smells / Maintainability

| ID | File:line | Issue | Severity |
|---|---|---|---|
| C1 | All subdirectory .py files | `sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` boilerplate duplicated in 6 files. Should be a `conftest.py` / `__init__.py` / proper package install. | High |
| C2 | `mcp_server.py:14-18` vs `async_dev/...` vs other MCP servers | `mcp_tool` decorator pattern + `TypeVar('F', bound=Callable[..., Awaitable[str]])` + `# type: ignore` duplicated. Same anti-pattern as Plan 4a `llm_as_mcp/base.py` + `mcp_server.py` duplication. | High |
| C3 | `sync/SyncOptionChainBuilder.py` vs `async_dev/httpx approach.py` | `AsyncOptionChainBuilder` is essentially a port of `SyncOptionChainBuilder`. ~80% structural duplication: underliers → strikes → contracts → store_data. Differences are mainly `async`/`sync` and aiometer vs sequential. Should share a common builder pattern. | Critical |
| C4 | `sync/SyncFetcher.py` vs `async_dev/AsyncFetcher.py` | Same situation: two parallel fetcher classes doing the same thing in sync vs async style. | High |
| C5 | `utils/url_builder.py:21-94` vs `:99-170` | Two parallel sets of URL builders: `build_underlier_url` (for httpx) and `build_underlier_params` (for ibind). Same domain knowledge duplicated. | High |
| C6 | `utils/client_helper.py` | Uses `print()` for ~30 log lines. `session_health_helper.py` uses `logging` properly. Inconsistent logging approaches in adjacent files. | Medium |
| C7 | `utils/ibkr_oauth.py` (414 LOC) | Three OAuth request methods (`_get_request_token`, `_get_access_token`, `_get_live_session_token`) are **near-identical**: build params, build base string, sign, send, parse. Should be one method parameterized by endpoint. | High |
| C8 | `utils/ibkr_oauth.py:122-138, 153-175, 232-260` | Three `param_string = "&".join([...])` blocks. Three `headers = {...}` blocks. Three `requests.post(url, headers=headers)` blocks. Pure duplication. | High |
| C9 | `async_dev/httpx approach.py:178` | `import time` duplicated (already imported at line 16). | Low |
| C10 | `async_dev/httpx approach.py` | Filename is `httpx approach.py` (with a space). Imports require `importlib.util.spec_from_file_location` to handle. Non-standard filename. | Medium |
| C11 | `utils/ibkr_oauth.py:21` | `def __init__(self, config):` — `config` parameter has no type annotation. Should be `IBKRAuthConfig` dataclass with typed fields. | Low |
| C12 | `utils/database.py:10-15` | `OptionChain` SQLModel has no `__str__` / `__repr__` / `table_name` declaration. Debugging and logging are harder. | Low |
| C13 | `mcp_server.py:44` | `import json` inside the function body. Should be at the top. | Low |
| C14 | `utils/url_builder.py:49` | `clean_month = month.replace(" ", "")` — silently removes whitespace from month strings. Could mask data quality issues from upstream. | Low |
| C15 | `async_dev/test_concurrency.py:30-37` | Three `if X is None: raise ImportError(...)` blocks for the same condition. Defensive overkill. | Low |

## Category D — Missing Infrastructure

| ID | Issue | Severity |
|---|---|---|
| D1 | No `tests/` directory. Only `async_dev/test_concurrency.py` exists, which is a performance benchmark, not unit tests. AGENTS.md mentions it but it's the only test file. | High |
| D2 | No `pyproject.toml` or `requirements.txt` despite AGENTS.md listing 10+ dependencies. The README mentions dependencies but no pinned versions. | High |
| D3 | No `README.md` — only AGENTS.md. README is the public-facing doc, AGENTS.md is for AI agents. | Medium |
| D4 | No `pytest` / `conftest.py` / `tests/__init__.py` — proper test infrastructure missing entirely. | High |
| D5 | No `ruff` / `black` / `mypy` config. The codebase has inconsistent formatting and type annotations. | Medium |
| D6 | No CI config. `.github/workflows/` absent. | Medium |
| D7 | No `.env.example`. Real `.env` files exist per AGENTS.md but the schema isn't documented. | Medium |
| D8 | No `Dockerfile` / `docker-compose.yml` despite AGENTS.md describing docker-based postgres setup. | Low |
| D9 | No license file (`LICENSE`). | Low |
| D10 | No structured logging across most modules. `print()` is used pervasively in `client_helper.py`, `SyncRetryHandler.py`, `SyncOptionChainBuilder.py`, `AsyncFetcher.py`, `mcp_server.py`. Only `session_health_helper.py` uses proper logging. | High |

## Category E — Architectural

| ID | Issue | Severity |
|---|---|---|
| E1 | **Sync vs async duplication** (C3 + C4). The two implementations are ~80% the same. AGENTS.md justifies this with "Recommended for MCP tools" vs "Under development", but the right factoring is shared business logic with sync/async I/O swap. | Critical |
| E2 | **Fire-and-forget MCP thread** (A4). `fetch_option_chain` spawns a thread and returns. No completion signal, no error propagation, no observability. The caller cannot tell when the data is ready or whether it succeeded. | Critical |
| E3 | **Three OAuth methods** in `utils/ibkr_oauth.py` (C7, C8). Three near-identical request blocks. Should be one method taking endpoint + params. | High |
| E4 | **Two URL builder patterns** in `utils/url_builder.py` (C5). One builds URLs (for httpx), one builds params dicts (for ibind). The same business logic is duplicated. | Medium |
| E5 | **Two retry strategies** (tenacity in async, manual loop in sync). Different semantics, different defaults, no shared configuration. If MAX_RETRIES changes in `settings/config.py`, only one is updated. | Medium |
| E6 | **Manual URL parsing** in `utils/client_helper.py:82` (A7). Should use `urllib.parse.urlparse` + `urlunparse`. | Medium |
| E7 | **Session health manager and client helper both do retry** — `SessionHealthManager.reinitialize_session` calls `create_ibkr_client` which has its own retry loop. Multiple retry layers. | Medium |
| E8 | **No centralized error model.** Some functions return `None` on failure, some return empty list, some return string error messages, some raise exceptions. Inconsistent. | High |

## Category F — Async-specific concerns (unique to this codebase)

| ID | File:line | Issue | Severity |
|---|---|---|---|
| F1 | `async_dev/AsyncFetcher.py:80` | `oauth_headers = self._signer._get_headers("GET", url)` — calls a private method (underscore prefix). Brittle. | Medium |
| F2 | `async_dev/AsyncFetcher.py:113` | `return None  # type: ignore` — unreachable code; comment says "Should not reach here due to tenacity decorator". If tenacity is misconfigured, this returns None silently. | Medium |
| F3 | `async_dev/httpx approach.py:212-219` | `__main__` block redirects stdout to log file using `sys.stdout = f`. While running async code via `asyncio.run(chain_builder.get_option_chain_async())`. Race condition possible if the function spawns background tasks that write to stdout after `sys.stdout` is restored in the `finally`. | Medium |
| F4 | `async_dev/httpx approach.py:95-103` | Uses `functools.partial(self._fetcher.get_strikes, ...)` to create tasks. This binds the method but creates a partial per iteration — for hundreds of strikes, creates hundreds of partial objects. Minor perf issue but suggests design not aware of `asyncio.gather` patterns. | Low |

---

## Summary checklist for Mini-Agent scoring

- **Total issues catalogued:** 60
  - A (Bugs): 15 (2 critical, 6 high, 5 medium, 2 low)
  - B (Security): 6 (1 critical, 1 high, 3 medium, 1 low)
  - C (Smells): 15 (0 critical, 4 high, 4 medium, 7 low)
  - D (Missing infra): 10 (0 critical, 4 high, 4 medium, 2 low)
  - E (Architectural): 8 (2 critical, 3 high, 3 medium)
  - F (Async-specific): 4 (0 critical, 0 high, 3 medium, 1 low)
- **Critical issues:** 5 (A1, A4, B1, C3, E1, E2 — that's actually 6 critical; conservative count = 5)

### Scoring rubric

- **Recall ≥ 50%** = Mini-Agent found 30+ issues → pass (the codebase is bigger so realistic recall ceiling is lower than Plan 4a's 60%)
- **Critical issue recall ≥ 50%** = Mini-Agent found 3+ of 6 criticals → pass
- **Precision ≥ 70%** = at most ~9 false positives across Mini-Agent's full report
- **Bonus**: identifying async/sync duplication as architectural (E1) — tests if Mini-Agent reasons structurally
- **Penalty**: hallucinating issues that aren't real (false precision)

### Comparison to Plan 4a

- Plan 4a baseline: 30 issues for 156 LOC → ratio: 0.19 issues/LOC
- Plan 4b baseline: 60 issues for 2,595 LOC → ratio: 0.023 issues/LOC
- Plan 4b has ~5x lower issue density per LOC — reasonable for a more mature codebase
- If Mini-Agent finds proportionally similar (60 issues × 0.5 = 30 recall, since the codebase is harder), that's 50% recall — a meaningful comparison point

### What I am NOT testing for in Plan 4b

- Whether Mini-Agent finds the same NUMBER of issues as me (count matters less than recall of mine)
- Stylistic preferences (function naming, docstring quality)
- Performance benchmarks
- Whether the code runs end-to-end (we're not connecting to PostgreSQL or IBKR)
