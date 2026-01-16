# Configuration file for the option chain app
DATABASE_URL = "postgresql+psycopg://postgres:secret@localhost:5432/options_db"
IBKR_BASE_URL = "https://api.ibkr.com/v1/api/"
SEARCH_PATH = "iserver/secdef/search"
STRIKE_PATH = "iserver/secdef/strikes"
INFO_PATH = "iserver/secdef/info"

DEFAULT_SYMBOL = "SPY"
DEFAULT_EXCHANGE = "SMART"

STATE_FILE = "api_state.json"

DEFAULT_USE_LOOP = False


GET_RESPONSE_TIME_OUT = 30  # Increased from 5 to 30 seconds for better reliability

# Retry configuration
MAX_RETRIES = 3              # Maximum retry attempts for failed requests
INITIAL_BACKOFF = 1.0        # Initial backoff in seconds
BACKOFF_MULTIPLIER = 2.0     # Exponential multiplier for backoff
MAX_BACKOFF = 10.0           # Maximum backoff cap in seconds

# Concurrency and rate limiting configuration
# Note: IBKR uses HTTP/1.1 (no multiplexing), so each request requires a connection from the pool
# MAX_CONCURRENCY must be < MAX_CONNECTIONS to avoid PoolTimeout
# IMPORTANT: IBKR has a concurrent request limit that triggers 503 errors when exceeded (tested: 20 causes 503s)
MAX_CONCURRENCY = 8          # Test value 2/6: Matches natural concurrency (10 req/s * 0.80s)
MAX_RATE = 10                # Rate limit: requests per second (IBKR API limit)

# Connection pool configuration (important for HTTP/1.1)
# These should be consistent with MAX_CONCURRENCY since aiometer controls actual concurrency
MAX_CONNECTIONS = 16               # Hard limit on concurrent connections (2x MAX_CONCURRENCY for safety buffer)
MAX_KEEPALIVE_CONNECTIONS = 8      # Reuse connections (equal to MAX_CONCURRENCY for efficiency)
KEEPALIVE_EXPIRY = 30.0             # Keep connections alive for 30 seconds

#TODO: organize above parameter defaults, review duplicate/conflicts of using these defaults in code base.
