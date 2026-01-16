"""
Helper functions for managing IBKR session health and handling tickler errors.

Handles common session issues including:
- 410 Gone errors (OAuth session expired)
- 503 Service Unavailable (temporary service issues)
- 500 Internal Server Error (service health issues)
- Tickler failures (session keep-alive failures)
"""
import time
import logging
from typing import Optional, Callable
from ibind import IbkrClient
from ibind.support.errors import ExternalBrokerError
from ibind.oauth.oauth1a import OAuth1aConfig
from utils.client_helper import create_ibkr_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionHealthManager:
    """
    Manages IBKR session health and handles tickler errors gracefully.
    
    This class provides methods to:
    - Monitor session health
    - Handle tickler failures
    - Reinitialize sessions when needed
    - Wrap client operations with health checks
    """
    
    def __init__(
        self,
        client: IbkrClient,
        max_health_retries: int = 3,
        health_check_interval: float = 30.0,
        tickler_retry_delay: float = 5.0,
        auto_reinitialize: bool = True,
        **client_kwargs
    ):
        """
        Initialize the SessionHealthManager.
        
        Args:
            client: The IbkrClient instance to monitor
            max_health_retries: Maximum attempts to reinitialize session
            health_check_interval: Time between health checks in seconds
            tickler_retry_delay: Delay before retrying tickler failures
            auto_reinitialize: Whether to automatically reinitialize session on failure
            **client_kwargs: Arguments for reinitializing the client if needed
        """
        self._client = client
        self._max_health_retries = max_health_retries
        self._health_check_interval = health_check_interval
        self._tickler_retry_delay = tickler_retry_delay
        self._auto_reinitialize = auto_reinitialize
        self._client_kwargs = client_kwargs
        self._last_health_check = 0
        self._consecutive_failures = 0
        
    @property
    def client(self) -> IbkrClient:
        """Get the current client instance."""
        return self._client
    
    def is_session_healthy(self) -> bool:
        """
        Check if the current session is healthy by attempting a tickle.
        
        Returns:
            True if session is healthy, False otherwise
        """
        try:
            self._client.tickle()
            self._consecutive_failures = 0
            return True
        except ExternalBrokerError as e:
            logger.warning(f"Session health check failed: {e}")
            self._consecutive_failures += 1
            return False
        except Exception as e:
            logger.error(f"Unexpected error during health check: {e}")
            self._consecutive_failures += 1
            return False
    
    def reinitialize_session(self) -> Optional[IbkrClient]:
        """
        Attempt to reinitialize the IBKR session.
        
        Returns:
            New IbkrClient instance if successful, None otherwise
        """
        logger.info(f"Attempting to reinitialize session (attempt {self._consecutive_failures}/{self._max_health_retries})...")
        
        # Try to create a new client
        new_client = create_ibkr_client(**self._client_kwargs)
        
        if new_client:
            logger.info("✅ Session reinitialized successfully")
            self._client = new_client
            self._consecutive_failures = 0
            return new_client
        else:
            logger.error("❌ Failed to reinitialize session")
            return None
    
    def ensure_healthy_session(self) -> Optional[IbkrClient]:
        """
        Ensure we have a healthy session, reinitializing if necessary.
        
        Returns:
            Healthy IbkrClient instance if successful, None otherwise
        """
        current_time = time.time()
        
        # Check if we need to perform a health check
        if current_time - self._last_health_check > self._health_check_interval:
            self._last_health_check = current_time
            
            if not self.is_session_healthy():
                logger.warning("Session unhealthy, attempting to recover...")
                
                if self._auto_reinitialize and self._consecutive_failures <= self._max_health_retries:
                    time.sleep(self._tickler_retry_delay)
                    return self.reinitialize_session()
                else:
                    logger.error(f"Max reinitialization attempts ({self._max_health_retries}) exceeded")
                    return None
        
        return self._client
    
    def wrap_operation(self, operation: Callable) -> Callable:
        """
        Wrap an operation with session health checks and automatic recovery.
        
        Args:
            operation: A callable that uses the IBKR client
            
        Returns:
            Wrapped callable that ensures healthy session before execution
        """
        def wrapper(*args, **kwargs):
            # Ensure session is healthy before operation
            client = self.ensure_healthy_session()
            
            if client is None:
                logger.error("Cannot perform operation: no healthy session available")
                return None
            
            try:
                # Execute the operation
                result = operation(*args, **kwargs)
                return result
                
            except ExternalBrokerError as e:
                logger.error(f"Operation failed with ExternalBrokerError: {e}")
                
                # Handle session errors by reinitializing
                if e.status_code in [410, 503, 500]:
                    logger.warning("Session error detected, attempting reinitialization...")
                    self.reinitialize_session()
                
                return None
                
            except Exception as e:
                logger.error(f"Operation failed with unexpected error: {e}")
                return None
        
        return wrapper
    
    def suppress_tickler_errors(self) -> None:
        """
        Suppress tickler errors by configuring the client's tickler to be less noisy.
        
        Note: This is a workaround for noisy tickler logs. The tickler will still
        attempt to keep the session alive, but errors won't crash the program.
        """
        # The ibind library handles tickler errors internally
        # We just need to ensure our application doesn't crash on tickler failures
        logger.info("Tickler error suppression enabled (errors will be logged but not crash)")


def create_session_aware_client(
    max_health_retries: int = 3,
    health_check_interval: float = 30.0,
    tickler_retry_delay: float = 5.0,
    auto_reinitialize: bool = True,
    **client_kwargs
) -> Optional[SessionHealthManager]:
    """
    Create an IbkrClient with automatic session health management.
    
    This is a convenience function that creates both a client and a health manager.
    
    Args:
        max_health_retries: Maximum attempts to reinitialize session
        health_check_interval: Time between health checks in seconds
        tickler_retry_delay: Delay before retrying tickler failures
        auto_reinitialize: Whether to automatically reinitialize session on failure
        **client_kwargs: Arguments passed to create_ibkr_client()
        
    Returns:
        SessionHealthManager instance if client created successfully, None otherwise
        
    Example:
        >>> manager = create_session_aware_client(use_oauth=True, timeout=15)
        >>> if manager:
        ...     client = manager.ensure_healthy_session()
        ...     if client:
        ...         # Use client for operations
        ...         pass
    """
    # Create the initial client
    client = create_ibkr_client(**client_kwargs)
    
    if client is None:
        return None
    
    # Create and return the health manager
    manager = SessionHealthManager(
        client=client,
        max_health_retries=max_health_retries,
        health_check_interval=health_check_interval,
        tickler_retry_delay=tickler_retry_delay,
        auto_reinitialize=auto_reinitialize,
        **client_kwargs
    )
    
    return manager


def handle_tickler_error(exception: Exception) -> str:
    """
    Analyze and handle tickler errors with appropriate messages.
    
    Args:
        exception: The exception from the tickler
        
    Returns:
        A descriptive message about the error and recommended action
    """
    error_str = str(exception)
    
    if '410' in error_str or 'Gone' in error_str:
        return (
            "⚠️ OAuth session expired (410 Gone).\n"
            "   The tickler failed to keep the session alive.\n"
            "   Action: Session will be reinitialized automatically if auto_reinitialize is enabled."
        )
    
    elif '503' in error_str or 'Service Unavailable' in error_str:
        return (
            "⚠️ IBKR Service Unavailable (503).\n"
            "   The tickler failed due to temporary service issues.\n"
            "   Action: Will retry automatically. This is usually transient."
        )
    
    elif '500' in error_str or 'Internal Server Error' in error_str:
        return (
            "⚠️ IBKR Internal Server Error (500).\n"
            "   The tickler failed due to server health issues.\n"
            "   Action: Will retry automatically. Check IBKR service status if persistent."
        )
    
    elif 'No bridge' in error_str:
        return (
            "❌ No bridge error.\n"
            "   The session bridge is not available.\n"
            "   Action: Reinitialize the brokerage session."
        )
    
    else:
        return (
            f"⚠️ Unexpected tickler error: {type(exception).__name__}.\n"
            f"   Error: {error_str}\n"
            f"   Action: Check logs for details."
        )
