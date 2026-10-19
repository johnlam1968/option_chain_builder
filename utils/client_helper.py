"""
Helper functions for IBKR client initialization with exception handling.
"""
import logging
import time
from urllib.parse import urlparse, urlunparse
from ibind import IbkrClient
from ibind.support.errors import ExternalBrokerError
from ibind.oauth.oauth1a import OAuth1aConfig


# Module-level logger. The previous version of this file used bare ``print()``
# for every status message, which raced with the project's stdout-redirect
# pattern (see H-6 / H-7 in MINI_AGENT_PLAN4B_REVIEW.md). Records now flow
# through the logging system; callers can attach a StreamHandler or
# FileHandler if they want them on the terminal.
logger = logging.getLogger(__name__)


def create_ibkr_client(
    account_id: str = None,
    url: str = None,
    host: str = '127.0.0.1',
    port: str = '5000',
    base_route: str = '/v1/api/',
    cacert = None,
    timeout: float = 15,
    max_retries: int = 3,
    use_session: bool = True,
    auto_recreate_session: bool = True,
    auto_register_shutdown: bool = True,
    log_responses: bool = False,
    use_oauth: bool = True,
    oauth_config: OAuth1aConfig = None,
    retry_on_410: bool = True,
    api_servers: list = None
):
    """
    Create an IbkrClient with comprehensive exception handling and retry logic.
    
    Handles common initialization errors including:
    - 410 Gone errors (OAuth session expired)
    - Connection errors
    - Authentication failures
    - Missing dependencies
    
    Args:
        account_id: IBKR account ID
        url: IBKR API base URL
        host: IBKR API host
        port: IBKR API port
        base_route: IBKR API base route
        cacert: Path to CA certificate or False to disable
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        use_session: Whether to use persistent session
        auto_recreate_session: Whether to auto-recreate session on errors
        auto_register_shutdown: Whether to register shutdown handler
        log_responses: Whether to log API responses
        use_oauth: Whether to use OAuth authentication
        oauth_config: OAuth configuration
        retry_on_410: Whether to retry on 410 Gone errors with different servers
        api_servers: List of API servers to try on 410 errors
        
    Returns:
        IbkrClient instance if successful, None otherwise
        
    Example:
        >>> client = create_ibkr_client(use_oauth=True, timeout=15)
        >>> if client:
        ...     print("Client created successfully")
        ... else:
        ...     print("Failed to create client")
    """
    if api_servers is None:
        api_servers = [
            "api.ibkr.com",
            "1.api.ibkr.com",
            "2.api.ibkr.com"
        ]
    
    max_attempts = len(api_servers) if retry_on_410 else 1
    
    for attempt in range(max_attempts):
        current_url = url
        
        # If retrying on 410, try different API servers
        if retry_on_410 and attempt > 0 and attempt < len(api_servers):
            # Replace the URL host with the next API server. The previous
            # implementation split the URL on '/' and rewrote parts[2], which
            # silently produced broken URLs for inputs containing ports,
            # userinfo, query strings, or fragments. Use urlparse instead.
            if url:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    # netloc may carry userinfo + port — preserve everything
                    # except the host (first component of netloc).
                    userinfo_port = parsed.netloc.split('@')[-1]
                    if ':' in userinfo_port:
                        _host, _port = userinfo_port.rsplit(':', 1)
                        new_netloc = f"{api_servers[attempt]}:{_port}"
                    else:
                        new_netloc = api_servers[attempt]
                    # Carry any userinfo forward.
                    if '@' in parsed.netloc:
                        new_netloc = parsed.netloc.split('@', 1)[0] + '@' + new_netloc
                    current_url = urlunparse((
                        parsed.scheme,
                        new_netloc,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    ))
                # If parsing failed, leave current_url alone and let IbkrClient
                # surface the error.
            else:
                # Build URL from components
                current_url = f'https://{api_servers[attempt]}:{port}{base_route}'

            logger.info("Attempt %d/%d: Trying API server: %s", attempt + 1, max_attempts, current_url)

        try:
            logger.info("Initializing IbkrClient (attempt %d/%d)...", attempt + 1, max_attempts)

            client = IbkrClient(
                account_id=account_id,
                url=current_url,
                host=host,
                port=port,
                base_route=base_route,
                cacert=cacert,
                timeout=timeout,
                max_retries=max_retries,
                use_session=use_session,
                auto_recreate_session=auto_recreate_session,
                auto_register_shutdown=auto_register_shutdown,
                log_responses=log_responses,
                use_oauth=use_oauth,
                oauth_config=oauth_config,
            )

            logger.info("✅ IbkrClient initialized successfully!")
            return client

        except ExternalBrokerError as e:
            error_msg = str(e)
            logger.error("❌ ExternalBrokerError: %s", error_msg)

            # Check for specific error types
            if e.status_code == 410 and 'gone' in error_msg.lower():
                if attempt < max_attempts - 1:
                    logger.warning("⚠️ OAuth session expired (410 Gone). Will retry with different server...")
                    time.sleep(2)  # Wait before retry
                    continue
                else:
                    logger.error("❌ All API servers exhausted. Please check your OAuth credentials and try again later.")
                    logger.error("   Possible solutions:")
                    logger.error("   - Re-authenticate with IBKR")
                    logger.error("   - Check if OAuth credentials are still valid")
                    logger.error("   - Try again later (session may be temporarily unavailable)")

            elif 'no bridge' in error_msg:
                logger.error("❌ No bridge error. Try calling `initialize_brokerage_session()` first.")

            else:
                logger.error("❌ IBKR API error: %s", e)

            return None

        except ImportError as e:
            logger.error("❌ ImportError: %s", e)
            logger.error("   OAuth support missing. Install with: pip install ibind[oauth]")
            return None

        except RuntimeError as e:
            logger.error("❌ RuntimeError: %s", e)
            logger.error("   Live session token validation failed.")
            logger.error("   Check your OAuth credentials and try again.")
            return None

        except ConnectionError as e:
            logger.error("❌ ConnectionError: %s", e)
            logger.error("   Failed to connect to IBKR API.")
            logger.error("   Check your internet connection and IBKR service status.")

            if attempt < max_attempts - 1:
                logger.error("   Retrying...")
                time.sleep(2)
                continue

            return None

        except Exception as e:
            logger.exception("❌ Unexpected error creating IbkrClient: %s: %s", type(e).__name__, e)
            return None

    logger.error("❌ Failed to create IbkrClient after all attempts.")
    return None


def create_ibkr_client_with_retry(
    max_initialization_attempts: int = 3,
    delay_between_attempts: float = 5.0,
    **kwargs
):
    """
    Create an IbkrClient with multiple initialization attempts and delays.
    
    Useful for handling transient network issues or temporary service disruptions.
    
    Args:
        max_initialization_attempts: Maximum number of initialization attempts
        delay_between_attempts: Delay between attempts in seconds
        **kwargs: Arguments passed to create_ibkr_client()
        
    Returns:
        IbkrClient instance if successful, None otherwise
    """
    for attempt in range(max_initialization_attempts):
        logger.info("\nInitialization attempt %d/%d", attempt + 1, max_initialization_attempts)

        client = create_ibkr_client(**kwargs)

        if client is not None:
            return client

        if attempt < max_initialization_attempts - 1:
            logger.info("\n⏳ Waiting %.1f seconds before retry...", delay_between_attempts)
            time.sleep(delay_between_attempts)

    logger.error("\n❌ Failed to create IbkrClient after %d attempts.", max_initialization_attempts)
    return None
