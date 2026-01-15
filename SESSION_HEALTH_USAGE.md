# Session Health Helper Usage Guide

## Overview

The `session_health_helper.py` module provides automatic session health management for IBKR API connections, handling common issues like:
- **410 Gone errors** (OAuth session expired)
- **503 Service Unavailable** (temporary service issues)
- **500 Internal Server Error** (service health issues)
- **Tickler failures** (session keep-alive failures)

## Where to Call the Helper

### 1. **Initial Client Creation** (Recommended)

Replace your existing `create_ibkr_client()` call with `create_session_aware_client()`:

```python
from session_health_helper import create_session_aware_client

# OLD WAY
_signer = create_ibkr_client(use_oauth=True, timeout=15, retry_on_410=True)

# NEW WAY - with automatic session health management
_session_manager = create_session_aware_client(
    use_oauth=True,
    timeout=15,
    retry_on_410=True,
    max_health_retries=3,          # Max attempts to reinitialize
    health_check_interval=60.0,    # Check health every 60 seconds
    tickler_retry_delay=5.0,        # Wait 5s before retry
    auto_reinitialize=True         # Auto-reinitialize on failure
)

# Get the client from the manager
_signer = _session_manager.client
```

### 2. **Before Critical Operations**

Ensure session is healthy before important operations:

```python
# Before starting your main workflow
_healthy_client = _session_manager.ensure_healthy_session()
if _healthy_client is None:
    print("❌ Failed to establish healthy session")
    sys.exit(1)
```

### 3. **Long-Running Applications**

For long-running processes, periodically check session health:

```python
async def long_running_task():
    while True:
        # Ensure session is healthy
        client = _session_manager.ensure_healthy_session()
        if client is None:
            print("Session lost, attempting recovery...")
            continue
        
        # Perform your operations
        await do_some_work(client)
        
        # Wait before next iteration
        await asyncio.sleep(30)
```

### 4. **Wrapping Operations**

Wrap individual operations with automatic recovery:

```python
# Define a function that uses the client
def fetch_market_data(symbol):
    return client.get_market_data(symbol)

# Wrap it with automatic session health checks
safe_fetch = _session_manager.wrap_operation(fetch_market_data)

# Now safe_fetch will ensure session health before calling
result = safe_fetch("SPY")
```

## Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_health_retries` | 3 | Maximum attempts to reinitialize session |
| `health_check_interval` | 30.0 | Seconds between health checks |
| `tickler_retry_delay` | 5.0 | Delay before retrying tickler failures |
| `auto_reinitialize` | True | Automatically reinitialize on failure |
| `use_oauth` | True | Use OAuth authentication |
| `timeout` | 15 | Request timeout in seconds |
| `retry_on_410` | True | Retry with different servers on 410 errors |

## How It Works

1. **Session Health Monitoring**: The `SessionHealthManager` periodically checks if the session is healthy by calling `tickle()`

2. **Automatic Recovery**: When a session becomes unhealthy (410, 503, 500 errors), it automatically attempts to reinitialize

3. **Tickler Error Handling**: Tickler errors are logged but don't crash the application

4. **Configurable Retries**: You can control how many times to retry reinitialization

## Example: Full Integration

```python
from session_health_helper import create_session_aware_client
from httpx import AsyncClient
import asyncio

async def main():
    # Create client with session health management
    session_manager = create_session_aware_client(
        use_oauth=True,
        timeout=15,
        retry_on_410=True,
        max_health_retries=3,
        health_check_interval=60.0,
        tickler_retry_delay=5.0,
        auto_reinitialize=True
    )
    
    if session_manager is None:
        print("Failed to create client")
        return
    
    # Get the client
    client = session_manager.client
    
    # Create httpx session
    http_session = AsyncClient(
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0
        )
    )
    
    # Ensure session is healthy before starting
    healthy_client = session_manager.ensure_healthy_session()
    if healthy_client is None:
        print("Failed to establish healthy session")
        return
    
    # Do your work here
    await do_option_chain_fetch(http_session, client)

asyncio.run(main())
```

## Handling Tickler Errors Manually

If you need to analyze tickler errors:

```python
from session_health_helper import handle_tickler_error

try:
    # Your IBKR operations
    client.tickle()
except Exception as e:
    message = handle_tickler_error(e)
    print(message)
    # Output example:
    # ⚠️ IBKR Service Unavailable (503).
    #    The tickler failed due to temporary service issues.
    #    Action: Will retry automatically. This is usually transient.
```

## Benefits

✅ **Automatic Recovery**: No need to manually handle session expirations  
✅ **Graceful Degradation**: Tickler errors don't crash your app  
✅ **Configurable**: Adjust retry logic to your needs  
✅ **Minimal Code Changes**: Drop-in replacement for existing client creation  
✅ **Better Logging**: Clear messages about session health issues  

## Troubleshooting

### "Max reinitialization attempts exceeded"

- Check your OAuth credentials
- Verify IBKR API service status
- Increase `max_health_retries` if needed
- Check network connectivity

### Frequent 410 Gone errors

- Your OAuth session may be expiring too quickly
- Ensure `maintain_oauth` is enabled in OAuth config
- Check if you're hitting rate limits

### Tickler errors in logs

- These are normal and handled automatically
- Use `suppress_tickler_errors()` to reduce log noise
- Errors are informational only, won't crash the app

### Timeout errors when fetching data

- Ensure `GET_RESPONSE_TIME_OUT` in `config.py` is set to at least 30 seconds
- The IBKR API can be slow, especially during market hours
- Check your internet connection speed
- Try reducing the rate of requests if hitting rate limits

### Session expires during long operations

- Increase `health_check_interval` to check less frequently
- Ensure `auto_reinitialize` is enabled
- Consider breaking up long operations into smaller chunks
