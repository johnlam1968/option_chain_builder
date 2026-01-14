# Configuration file for the option chain app
DATABASE_URL = "postgresql+psycopg://postgres:secret@localhost:5432/options_db"
IBKR_BASE_URL = "https://api.ibkr.com/v1/api/"
SEARCH_PATH = "iserver/secdef/search"
STRIKE_PATH = "iserver/secdef/strikes"
INFO_PATH = "iserver/secdef/info"
STATE_FILE = "api_state.json"
MAX_RATE = 10
GET_RESPONSE_TIME_OUT = 5
DEFAULT_SYMBOL = "SPY"
DEFAULT_EXCHANGE = "SMART"

# Retry configuration
MAX_RETRIES = 3              # Maximum retry attempts for failed requests
INITIAL_BACKOFF = 1.0        # Initial backoff in seconds
BACKOFF_MULTIPLIER = 2.0     # Exponential multiplier for backoff
MAX_BACKOFF = 10.0           # Maximum backoff cap in seconds
