# Configuration file for option chain application

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

DATABASE_URL = "postgresql+psycopg://postgres:secret@localhost:5432/options_db"
# PostgreSQL connection string
# Note: Replace 'localhost' with 'db' if Python is inside Docker network


# ============================================================================
# IBKR API CONFIGURATION
# ============================================================================

IBKR_BASE_URL = "https://api.ibkr.com/v1/api/"
# Base URL for all IBKR API endpoints

# API Endpoint Paths
SEARCH_PATH = "iserver/secdef/search"   # Search for underliers by symbol
STRIKE_PATH = "iserver/secdef/strikes"  # Get available strike prices
INFO_PATH = "iserver/secdef/info"       # Get contract details


# ============================================================================
# DEFAULT VALUES
# ============================================================================

DEFAULT_SYMBOL = "FXI"
# Default symbol/underlier for option chain queries

DEFAULT_EXCHANGE = "SMART"
# Default exchange identifier (e.g., "SMART", "FEHK", "NYMEX")

DEFAULT_USE_LOOP = False
# Default to use batch processing (aiometer) instead of sequential loop
# Set True for debugging or to disable concurrent processing


# ============================================================================
# STATE MANAGEMENT
# ============================================================================

STATE_FILE = "settings/api_state.json"
# File path for storing dynamic runtime state
# 
# This file is modified during runtime to persist:
# - OAuth token state for authentication
# - Throttling parameters that may be adjusted dynamically (e.g., rate limits)
# - Performance metrics and adaptive settings
#
# Example state:
# {
#   "initial_rate": 10.0,
#   "marginal_rate": 19
# }
#
# The actual content depends on the throttling/adaptive algorithms used
# Note: This is a placeholder that will be modified at runtime


# ============================================================================
# TIMEOUT CONFIGURATION
# ============================================================================

GET_RESPONSE_TIME_OUT = 30
# HTTP request timeout in seconds
# Increased from 5 to 30 for better reliability with slow IBKR API responses


# ============================================================================
# RETRY CONFIGURATION
# ============================================================================

MAX_RETRIES = 3
# Maximum number of retry attempts for failed requests (timeouts, rate limits, etc.)

INITIAL_BACKOFF = 1.0
# Initial backoff delay in seconds before first retry

BACKOFF_MULTIPLIER = 2.0
# Multiplier for exponential backoff (delay = INITIAL_BACKOFF * MULTIPLIER^attempt)

MAX_BACKOFF = 10.0
# Maximum backoff cap in seconds
# Actual backoff = min(INITIAL_BACKOFF * BACKOFF_MULTIPLIER^attempt, MAX_BACKOFF)


# ============================================================================
# CONCURRENCY AND RATE LIMITING (ASYNC ONLY)
# ============================================================================

# IMPORTANT NOTES:
# 1. IBKR uses HTTP/1.1 (no multiplexing), so each request requires a connection from pool
# 2. MAX_CONCURRENCY must be < MAX_CONNECTIONS to avoid PoolTimeout errors
# 3. IBKR has a concurrent request limit that triggers HTTP 503 errors when exceeded
#    (Tested: 20 concurrent requests causes 503 errors)
# 4. These settings are only used by async implementation (async_dev/)
# 5. Sync implementation (sync/) uses sequential processing with retry logic

MAX_CONCURRENCY = 8
# Maximum number of concurrent HTTP requests
# Matches natural concurrency: MAX_RATE (10 req/s) × avg_response_time (0.80s) ≈ 8
# Tested values:
#   - 2: Bottlenecked (50% capacity) - slow but safe
#   - 5: Bottlenecked (62.5% capacity) - used in early testing
#   - 8: Matches natural capacity (100%) - theoretically optimal
#   - 10+: May exceed capacity, risk 503 errors
#   - 20+: Definitely exceeds capacity, high 503 risk

MAX_RATE = 10
# Rate limit: maximum requests per second
# Based on IBKR API documentation limits
# Do not increase without verifying IBKR's updated rate limits


# ============================================================================
# HTTP CONNECTION POOL CONFIGURATION (ASYNC ONLY)
# ============================================================================

MAX_CONNECTIONS = 16
# Hard limit on concurrent HTTP connections in the pool
# Should be at least 2× MAX_CONCURRENCY for safety buffer
# This allows for: active concurrent requests + overhead + new connection setup

MAX_KEEPALIVE_CONNECTIONS = 8
# Number of connections to keep alive for reuse
# Should be equal to MAX_CONCURRENCY for efficiency
# Reusing connections is critical for HTTP/1.1 performance

KEEPALIVE_EXPIRY = 30.0
# Time in seconds to keep idle connections alive before closing
# Allows connection reuse across multiple requests
# Should be longer than typical request processing time


# ============================================================================
# CONFIGURATION NOTES AND GUIDELINES
# ============================================================================

# Relationship Between Settings:
# - MAX_CONCURRENCY < MAX_CONNECTIONS (avoid PoolTimeout)
# - MAX_KEEPALIVE_CONNECTIONS ≈ MAX_CONCURRENCY (efficiency)
# - MAX_CONNECTIONS ≥ 2× MAX_CONCURRENCY (safety buffer)

# How to Adjust:
# - For slower API: Increase GET_RESPONSE_TIME_OUT
# - For more aggressive fetching: Increase MAX_CONCURRENCY (watch for 503 errors)
# - For rate limit issues: Decrease MAX_RATE
# - For connection errors: Increase MAX_CONNECTIONS or MAX_KEEPALIVE_CONNECTIONS

# Testing Changes:
# See async_dev/test_concurrency.py for systematic testing
# Run with different MAX_CONCURRENCY values to find optimal setting
