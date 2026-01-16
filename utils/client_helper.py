"""
Helper functions for IBKR client initialization with exception handling.
"""
import time
from ibind import IbkrClient
from ibind.support.errors import ExternalBrokerError
from ibind.oauth.oauth1a import OAuth1aConfig


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
            # Extract the base URL and replace the host
            if url:
                # Parse the URL and replace the host
                parts = url.split('/')
                if len(parts) >= 3:
                    parts[2] = api_servers[attempt]  # Replace host
                    current_url = '/'.join(parts)
            else:
                # Build URL from components
                current_url = f'https://{api_servers[attempt]}:{port}{base_route}'
            
            print(f"Attempt {attempt + 1}/{max_attempts}: Trying API server: {current_url}")
        
        try:
            print(f"Initializing IbkrClient (attempt {attempt + 1}/{max_attempts})...")
            
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
            
            print("✅ IbkrClient initialized successfully!")
            return client
            
        except ExternalBrokerError as e:
            error_msg = str(e)
            print(f"❌ ExternalBrokerError: {error_msg}")
            
            # Check for specific error types
            if e.status_code == 410 and 'gone' in error_msg.lower():
                if attempt < max_attempts - 1:
                    print(f"⚠️ OAuth session expired (410 Gone). Will retry with different server...")
                    time.sleep(2)  # Wait before retry
                    continue
                else:
                    print("❌ All API servers exhausted. Please check your OAuth credentials and try again later.")
                    print("   Possible solutions:")
                    print("   - Re-authenticate with IBKR")
                    print("   - Check if OAuth credentials are still valid")
                    print("   - Try again later (session may be temporarily unavailable)")
            
            elif 'no bridge' in error_msg:
                print("❌ No bridge error. Try calling `initialize_brokerage_session()` first.")
            
            else:
                print(f"❌ IBKR API error: {e}")
                
            return None
            
        except ImportError as e:
            print(f"❌ ImportError: {e}")
            print("   OAuth support missing. Install with: pip install ibind[oauth]")
            return None
            
        except RuntimeError as e:
            print(f"❌ RuntimeError: {e}")
            print("   Live session token validation failed.")
            print("   Check your OAuth credentials and try again.")
            return None
            
        except ConnectionError as e:
            print(f"❌ ConnectionError: {e}")
            print("   Failed to connect to IBKR API.")
            print("   Check your internet connection and IBKR service status.")
            
            if attempt < max_attempts - 1:
                print("   Retrying...")
                time.sleep(2)
                continue
            
            return None
            
        except Exception as e:
            print(f"❌ Unexpected error creating IbkrClient: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    print("❌ Failed to create IbkrClient after all attempts.")
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
        print(f"\nInitialization attempt {attempt + 1}/{max_initialization_attempts}")
        
        client = create_ibkr_client(**kwargs)
        
        if client is not None:
            return client
        
        if attempt < max_initialization_attempts - 1:
            print(f"\n⏳ Waiting {delay_between_attempts} seconds before retry...")
            time.sleep(delay_between_attempts)
    
    print(f"\n❌ Failed to create IbkrClient after {max_initialization_attempts} attempts.")
    return None
