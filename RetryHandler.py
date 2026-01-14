from config import BACKOFF_MULTIPLIER, INITIAL_BACKOFF, MAX_BACKOFF, MAX_RETRIES


from httpx import ConnectTimeout, PoolTimeout, ReadTimeout


import asyncio
from typing import Any, Callable


class RetryHandler:
    """
    Encapsulates retry logic with exponential backoff for transient failures.

    Handles:
    - Timeouts (PoolTimeout, ReadTimeout, ConnectTimeout)
    - HTTP 429 Rate Limit errors
    - HTTP 5xx Server errors (500-599)

    Configuration:
        - max_retries: Maximum retry attempts
        - initial_backoff: Initial backoff in seconds
        - backoff_multiplier: Exponential backoff multiplier
        - max_backoff: Maximum backoff cap in seconds
    """

    def __init__(
        self,
        max_retries: Optional[int] = None,
        initial_backoff: Optional[float] = None,
        backoff_multiplier: Optional[float] = None,
        max_backoff: Optional[float] = None
    ):
        self.max_retries = max_retries if max_retries is not None else MAX_RETRIES
        self.initial_backoff = initial_backoff if initial_backoff is not None else INITIAL_BACKOFF
        self.backoff_multiplier = backoff_multiplier if backoff_multiplier is not None else BACKOFF_MULTIPLIER
        self.max_backoff = max_backoff if max_backoff is not None else MAX_BACKOFF

    def calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff time for a given attempt."""
        return min(
            self.initial_backoff * (self.backoff_multiplier ** attempt),
            self.max_backoff
        )

    def is_retryable_response(self, result: Any) -> bool:
        """Check if an HTTP response indicates a retryable error (429 or 5xx)."""
        if not hasattr(result, 'status_code'):
            return False
        return result.status_code == 429 or (500 <= result.status_code < 600)

    def log_retry_attempt(self, error_type: str, attempt: int, wait_time: float, error_code: Optional[int] = None) -> None:
        """Log retry attempt with appropriate message based on error type."""
        if error_type == "Timeout":
            if attempt < self.max_retries:
                print(f"⏱️ {error_type} on attempt {attempt + 1}/{self.max_retries}. Retry after {wait_time:.1f}s")
            else:
                print(f"❌ {error_type} after {self.max_retries} retries. Giving up.")
        elif error_type == "RateLimit":
            print(f"⚠️ Rate limit hit (429). Retry {attempt + 1}/{self.max_retries} after {wait_time:.1f}s")
        elif error_type == "ServerError":
            print(f"⚠️ Server error {error_code}. Retry {attempt + 1}/{self.max_retries} after {wait_time:.1f}s")

    async def retry_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute async function with retry logic and exponential backoff.

        Args:
            func: Async function to execute
            *args, **kwargs: Arguments to pass to function

        Returns:
            Function result if successful, None after max retries
        """
        # Retry loop: attempt 0 = first try, attempt 1 = first retry, etc.
        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)

                # Check if result indicates a retryable HTTP error
                if self.is_retryable_response(result):
                    if attempt < self.max_retries:
                        wait_time = self.calculate_backoff(attempt)

                        # Determine error type for logging
                        if result.status_code == 429:
                            error_type = "RateLimit"
                        else:
                            error_type = "ServerError"

                        self.log_retry_attempt(error_type, attempt + 1, wait_time, result.status_code)
                        await asyncio.sleep(wait_time)
                        continue

                    return result

            except (PoolTimeout, ReadTimeout, ConnectTimeout) as e:
                if attempt < self.max_retries:
                    wait_time = self.calculate_backoff(attempt)
                    self.log_retry_attempt("Timeout", attempt + 1, wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ Timeout after {self.max_retries} retries. Giving up.")
                    return None

            except Exception as e:
                # Don't retry on unexpected exceptions
                print(f"❌ Unexpected error: {type(e).__name__}: {e}")
                return None

        # All retries exhausted
        return None