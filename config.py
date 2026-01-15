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
MAX_CONCURRENCY = 5          # Max concurrent requests (conservative start for IBKR gateway)
MAX_RATE = 10                # Rate limit: requests per second (IBKR API limit)

# Connection pool configuration (important for HTTP/1.1)
# Adjust these based on your concurrency needs
MAX_CONNECTIONS = 100               # Hard limit on concurrent connections
MAX_KEEPALIVE_CONNECTIONS = 20     # Reuse connections (important for HTTP/1.1 performance)
KEEPALIVE_EXPIRY = 30.0             # Keep connections alive for 30 seconds

#TODO: organize above parameter defaults, review duplicate/conflicts of using these defaults in code base.
