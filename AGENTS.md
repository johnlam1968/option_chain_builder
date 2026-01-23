# AGENTS.md - Agent Guide for Option Chain Builder

This document helps AI agents work effectively in this option chain builder repository.

## Project Overview

This application builds option chains by fetching options data from the Interactive Brokers (IBKR) Web API. It uses OAuth 1.0a authentication (with pre-stored secrets) and stores results in PostgreSQL. The project has both synchronous and asynchronous implementations to accommodate different performance requirements and testing scenarios.

## Directory Structure

```
option_chain_builder/
├── sync/                     # Synchronous implementation using ibind
│   ├── main.py              # Entry point for sync option chain building
│   ├── SyncOptionChainBuilder.py  # Main sync builder class
│   ├── SyncFetcher.py       # IBKR API calls using ibind client
│   └── SyncRetryHandler.py  # Retry logic with exponential backoff
│
├── async_dev/               # Asynchronous implementation using httpx
│   ├── httpx approach.py    # Main async builder with aiometer rate limiting
│   ├── AsyncFetcher.py     # Async HTTP requests with tenacity retry logic
│   └── test_concurrency.py  # Performance testing for different concurrency settings
│
├── utils/                   # Shared utilities
│   ├── database.py          # SQLModel database operations (store/query)
│   ├── url_builder.py       # IBKR API URL construction
│   ├── response_extraction.py  # Parse API responses
│   ├── ibkr_oauth.py        # OAuth 1.0a authentication
│   ├── client_helper.py     # Client initialization helpers
│   └── session_health_helper.py  # Session health management
│
├── settings/                # Configuration
│   ├── config.py            # Main configuration (API URLs, timeouts, retry settings)
│   ├── api_state.json       # Runtime state (rate limits, OAuth tokens)
│   └── underlier_mapping.md # Symbol to exchange mappings
│
├── mcp_server.py            # MCP server providing option chain tools
├── __init__.py              # Package initialization (empty)
└── README.md                # Project documentation
```

## Essential Commands

### Running the Application

**Synchronous Implementation (Recommended for MCP tools):**
```bash
python sync/main.py
```
- Uses ibind client for OAuth signing
- Sequential processing with retry logic
- More reliable for production use

**Asynchronous Implementation (Development/Performance Testing):**
```bash
python async_dev/httpx approach.py
```
- Uses httpx with aiometer for rate limiting
- Concurrent processing for faster retrieval
- Still under development

**MCP Server (for LLM tool integration):**
```bash
python mcp_server.py
```
- Provides `fetch_option_chain` and `check_option_chain` tools
- Uses sync implementation in background threads

**Concurrency Testing:**
```bash
python async_dev/test_concurrency.py
```
- Tests different `MAX_CONCURRENCY` values
- Measures total time, throughput, and HTTP 503 errors
- Helps find optimal concurrency settings

### Database Setup

Start PostgreSQL container:
```bash
docker run -d \
  --name options-db-container \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_DB=options_db \
  -p 5432:5432 \
  postgres
```

If Python is running inside Docker network, change `localhost` to `db` in `DATABASE_URL`.

### Installing Dependencies

```bash
pip install ibind sqlmodel python-dotenv mcp-server fastmcp httpx aiometer tenacity cryptography requests
```

## Key Configuration

### Main Configuration File: `settings/config.py`

**Database Configuration:**
- `DATABASE_URL`: PostgreSQL connection string
- Modify `localhost` to `db` if Python runs in Docker network

**IBKR API Configuration:**
- `IBKR_BASE_URL`: Base URL for IBKR API endpoints
- `SEARCH_PATH`, `STRIKE_PATH`, `INFO_PATH`: API endpoint paths
- `GET_RESPONSE_TIME_OUT`: HTTP request timeout (default: 30s)

**Default Values:**
- `DEFAULT_SYMBOL`: "HSI" (default underlier symbol)
- `DEFAULT_EXCHANGE`: "FEHK" (default exchange)
- `DEFAULT_USE_LOOP`: False (use batch processing by default)

**Retry Configuration:**
- `MAX_RETRIES`: 3 (max retry attempts for failed requests)
- `INITIAL_BACKOFF`: 1.0s (initial delay before first retry)
- `BACKOFF_MULTIPLIER`: 2.0 (exponential backoff multiplier)
- `MAX_BACKOFF`: 10.0s (maximum backoff cap)

**Concurrency and Rate Limiting (Async Only):**
- `MAX_CONCURRENCY`: 8 (max concurrent HTTP requests)
- `MAX_RATE`: 10 req/s (rate limit)
- `MAX_CONNECTIONS`: 16 (HTTP connection pool size)
- `MAX_KEEPALIVE_CONNECTIONS`: 8 (connections to keep alive)
- `KEEPALIVE_EXPIRY`: 30.0s (idle connection keep-alive time)

**Important Notes:**
- IBKR uses HTTP/1.1 (no multiplexing), so each request uses a connection from pool
- `MAX_CONCURRENCY` must be < `MAX_CONNECTIONS` to avoid PoolTimeout errors
- IBKR has a concurrent request limit that triggers HTTP 503 errors when exceeded
- Tested: 20 concurrent requests cause 503 errors, 8 is optimal

### Underlier Mapping: `settings/underlier_mapping.md`

This file maps symbols to their correct exchanges. Some underliers need specific exchanges:

```
Underlier: SPX, Exchange: SMART  # Even though SPX is on CBOE
Underlier: SPY, Exchange: SMART  # Even though SPY is on ARCA
Underlier: HSI, Exchange: HKFE   # Index options, use HKFE
Underlier: VIX, Exchange: CBOE   # Future options, use CBOE
Underlier: 2828, Exchange: SEHK
Underlier: CL, Exchange: NYMEX    # Future options, use NYMEX
```

### Runtime State: `settings/api_state.json`

This file is modified at runtime to persist:
- OAuth token state for authentication
- Throttling parameters that may be adjusted dynamically
- Performance metrics and adaptive settings

Example:
```json
{"initial_rate": 10.0, "marginal_rate": 19}
```

## Code Conventions and Patterns

### Utility Classes Use Static Methods

Shared utility classes in `utils/` use static methods to avoid instantiation:

```python
# UrlBuilder
from utils.url_builder import UrlBuilder
url = UrlBuilder.build_underlier_url("SPX")

# ResponseExtraction
from utils.response_extraction import ResponseExtraction
info = ResponseExtraction.extract_underlier_info(underlier, symbol)
```

### Path Handling in Subdirectories

All files in `sync/`, `async_dev/`, and `utils/` add parent directory to `sys.path`:

```python
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

This allows imports like `from settings.config import ...` to work from subdirectories.

### Retry Logic Patterns

**Sync Implementation (SyncRetryHandler):**
- Custom retry handler with exponential backoff
- Handles HTTP 429 (rate limit), HTTP 5xx (server errors), timeouts, connection errors
- Used by `SyncFetcher` for all API calls

**Async Implementation (tenacity):**
- Uses tenacity decorator for retry logic
- Handles `PoolTimeout`, `ReadTimeout`, `ConnectTimeout` exceptions
- Additional manual retry loop for HTTP 429 and 5xx errors

### Database Operations

Use SQLModel for database operations. All operations use context managers:

```python
from utils.database import store_data, query_option_chain

# Store option data (uses merge to handle duplicates)
store_data(option_data)

# Query option data by symbol
data = query_option_chain("SPX")
```

The `OptionChain` model has fields: `conid`, `symbol`, `maturity_date`, `strike`, `right`.

### Type Hints

The codebase uses type hints extensively, especially in newer files:

```python
from typing import List, Dict, Optional, Any

def extract_underlier_info(
    underlier: Dict[str, Any],
    symbol: str
) -> Optional[Tuple[str, Optional[str], Optiona[str], List[str]]]:
    ...
```

### Logging

- Sync implementation redirects stdout to log files with timestamps
- Async implementation uses Python's `logging` module
- INFO logs are suppressed to reduce noise (only WARNING and above shown)

### Async Implementation Details

The async implementation (`httpx approach.py`) uses:
- **httpx.AsyncClient**: For HTTP requests
- **aiometer.run_all**: For rate-limited concurrent execution
- **Batch processing**: Fetches all strikes for a month, then processes in parallel
- **Sequential mode**: Can use `use_loop=True` for debugging (no concurrency)

## API Workflow

### Option Chain Building Process

1. **Search for underlier** → Get contract ID (conid) and option details
2. **Get strikes** → List of available strike prices for each expiration month
3. **Fetch contract details** → Get call and put contracts for each strike
4. **Store in database** → Save option data to PostgreSQL

### IBKR API Endpoints

All endpoints use OAuth 1.0a signing via ibind or manual implementation:

- `/iserver/secdef/search?symbol={symbol}` - Search for underlier
- `/iserver/secdef/strikes?conid={conid}&sectype={sectype}&month={month}` - Get strikes
- `/iserver/secdef/info?conid={conid}&secType={sectype}&month={month}&strike={strike}&right={right}&exchange={exchange}` - Get contract details

### Exchange Handling

The API response contains multiple sections (equity, option, futures, etc.). The correct section must be selected:

- Most underliers: Option section is `sections[1]`
- Special exchanges (SEHK, HKFE): Option section is `sections[2]`

Multiple exchanges may be returned (e.g., "SMART;AMEX;"). Use only the first:
```python
if option_exchange and ';' in option_exchange:
    option_exchange = option_exchange.split(';')[0]
```

## Testing

### Test File: `async_dev/test_concurrency.py`

This script systematically tests different `MAX_CONCURRENCY` values to find the optimal setting.

It measures:
- Total time to complete
- Number of contracts fetched
- HTTP 503 errors (indicates concurrent limit exceeded)
- Throughput (contracts/second)

Usage:
```bash
python async_dev/test_concurrency.py
```

Tests values: `[2, 5, 8, 10, 12, 15]` and provides a recommendation based on:
- Highest throughput
- No 503 errors
- Shortest total time

## Important Gotchas

### 1. HTTP/1.1 No Multiplexing

IBKR uses HTTP/1.1, which doesn't support multiplexing. Each request requires a connection from the pool. This is why:
- `MAX_CONCURRENCY` must be < `MAX_CONNECTIONS`
- Keep-alive connections are critical for performance
- Connection pool configuration is sensitive

### 2. Exchange Mapping is Critical

Many underliers require specific exchanges that aren't obvious:
- SPX and SPY use "SMART" even though they're listed on CBOE and ARCA
- Index options (HSI) use "HKFE"
- Future options (CL, VIX) use "NYMEX" or "CBOE"

**Always check `underlier_mapping.md`** before adding new underliers.

### 3. API Rate Limits and 503 Errors

IBKR enforces strict concurrent request limits:
- Exceeding the limit returns HTTP 503 errors
- Tested: 20 concurrent requests cause 503 errors
- Current optimal: 8 concurrent requests (MAX_CONCURRENCY=8)

If you see 503 errors, reduce `MAX_CONCURRENCY` or increase delays.

### 4. Month Formatting

The API expects months in format "JAN 26" (with space), but some responses return "JAN26" (no space). The code normalizes this:

```python
# Format month: "JAN26" -> "JAN 26" if not already formatted
if " " not in month:
    formatted_month = f"{month[:3]} {month[3:]}"
else:
    formatted_month = month
```

### 5. OAuth 1.0a Complexity

The OAuth implementation in `utils/ibkr_oauth.py` handles:
- Request Token generation
- Access Token generation (requires manual user authorization)
- Live Session Token (LST) generation using Diffie-Hellman
- HMAC-SHA256 signing for authenticated requests

This is complex and should generally not be modified unless you understand the full OAuth 1.0a flow with RSA signatures and DH key exchange.

### 6. State File Persistence

`settings/api_state.json` is modified at runtime. Be aware:
- It contains dynamic state (OAuth tokens, rate limits)
- It may change while the application is running
- Don't rely on it being stable across restarts
- OAuth tokens expire and need regeneration

### 7. Path Imports

All subdirectory files add parent directory to `sys.path`. This is unusual but necessary for the current structure. When adding new files in subdirectories, ensure this pattern is followed:

```python
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

### 8. Empty __init__.py

The root `__init__.py` is empty. This is intentional - the package is used primarily as a script, not as an importable library.

### 9. Database Merge vs Insert

The `store_data` function uses `session.merge()` instead of `session.add()`. This means:
- Duplicate records (same conid) are updated, not duplicated
- The database acts as an upsert (update or insert) operation
- Conid is the primary key

### 10. MCP Server Threading

The MCP server runs sync option chain building in background threads. This is because:
- The sync implementation is blocking
- MCP tools should be async
- A thread is spawned to avoid blocking the event loop

The tool returns immediately with a message, and the actual work happens in the background.

## Dependencies

### Core Dependencies

- **ibind**: IBKR API client for OAuth and API calls
- **sqlmodel**: Database ORM (built on SQLAlchemy)
- **python-dotenv**: Environment variable loading
- **mcp-server**: MCP server framework
- **fastmcp**: Fast MCP server implementation

### Async Dependencies

- **httpx**: Async HTTP client
- **aiometer**: Async rate limiting (for concurrent API calls)
- **tenacity**: Retry logic with exponential backoff

### Additional Dependencies

- **cryptography**: For OAuth cryptographic operations (RSA, HMAC)
- **requests**: For HTTP requests (in sync implementation)

## Performance Considerations

### Sync vs Async

**Sync (ibind):**
- Sequential processing
- Easier to debug
- More reliable for production
- ~X × 10 seconds for X contracts

**Async (httpx + aiometer):**
- Concurrent processing
- Faster for large option chains
- More complex to debug
- Sensitive to rate limits (503 errors)

### Optimal Concurrency

Through testing (see `test_concurrency.py`):
- MAX_CONCURRENCY = 2: Bottlenecked (50% capacity) - slow but safe
- MAX_CONCURRENCY = 5: Bottlenecked (62.5% capacity)
- MAX_CONCURRENCY = 8: Matches natural capacity (100%) - optimal
- MAX_CONCURRENCY = 10+: May exceed capacity, risk 503 errors
- MAX_CONCURRENCY = 20+: Definitely exceeds capacity, high 503 risk

The theoretical optimal is: `MAX_RATE (10 req/s) × avg_response_time (0.80s) ≈ 8`

## Debugging Tips

### Enable Detailed Logging

For async implementation, comment out these lines to show INFO logs:

```python
# logging.getLogger('httpx').setLevel(logging.WARNING)
# logging.getLogger('ibind').setLevel(logging.WARNING)
# logging.getLogger('ibind_fh').setLevel(logging.WARNING)
# logging.getLogger('ibind_ibkr_client').setLevel(logging.WARNING)
```

### Check Database

Query the database to verify data:

```python
from utils.database import query_option_chain
data = query_option_chain("SPX")
print(data)
```

### Use Sequential Mode for Debugging

Set `use_loop=True` in `AsyncOptionChainBuilder` to disable concurrency:

```python
builder = AsyncOptionChainBuilder(
    session,
    signer,
    symbol,
    exchange,
    use_loop=True,  # Sequential processing for debugging
    show_progress=True
)
```

### Monitor for 503 Errors

Look for these messages in logs:
- `⚠️ Rate limit hit (429). Retry X/Y after Zs`
- `⚠️ Server error 503. Retry X/Y after Zs`

These indicate you're exceeding IBKR's concurrent request limits.

## When to Modify What

### Need to add a new underlier?
1. Check `settings/underlier_mapping.md` for the correct exchange
2. Add the mapping if it doesn't exist
3. Test with sync implementation first: `python sync/main.py`
4. Verify data appears in database

### Need to improve performance?
1. Run `python async_dev/test_concurrency.py` to find optimal settings
2. Adjust `MAX_CONCURRENCY` in `settings/config.py`
3. Monitor for HTTP 503 errors
4. Consider adjusting `MAX_RATE` if rate limits change

### Need to add a new API endpoint?
1. Add endpoint path to `settings/config.py`
2. Add URL builder method to `utils/url_builder.py`
3. Add fetcher method to `AsyncFetcher.py` or `SyncFetcher.py`
4. Add response extraction method to `utils/response_extraction.py` if needed

### Need to add new fields to database?
1. Update the `OptionChain` model in `utils/database.py`
2. Update `extract_option_results` in `utils/response_extraction.py` to extract new fields
3. Run: `python -c "from utils.database import engine; from sqlmodel import SQLModel; SQLModel.metadata.create_all(engine)"`

### Need to modify retry logic?
- Sync: Edit `SyncRetryHandler.py` for retry configuration
- Async: Edit `tenacity` decorator in `AsyncFetcher.py` for timeout retry, or manual retry loop for HTTP errors

## License

This project is licensed under the MIT License. See LICENSE for details.
