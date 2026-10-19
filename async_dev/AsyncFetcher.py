# Direct calls to IBKR API using httpx with tenacity retry logic
# ibind client for OAuth signing
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from httpx import AsyncClient, Response, PoolTimeout, ReadTimeout, ConnectTimeout, TimeoutException

# ibind ships `IbkrClient` at the top-level package (`ibind.IbkrClient`); the
# `ibind.client.ibkr_client` submodule is an internal/private path. We use
# the public re-export here to keep imports stable across ibind versions.
from ibind import IbkrClient
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError
)
from settings.config import GET_RESPONSE_TIME_OUT, MAX_RETRIES, MAX_BACKOFF
from utils.url_builder import UrlBuilder

# Configure logger for tenacity
logger = logging.getLogger(__name__)


class _HTTPErrorForRetry(Exception):
    """Internal sentinel raised by ``_get_response`` to feed tenacity.

    Tenacity's retry predicates are exception-based, so when the underlying
    HTTP call succeeded (status code came back) but the status itself is
    retryable (429 / 5xx), we have to raise something to trigger a retry.
    Carrying the ``status_code`` lets the log message stay informative.
    """

    def __init__(self, status_code: int) -> None:
        super().__init__(f"retryable HTTP status {status_code}")
        self.status_code = status_code


class AsyncFetcher:
    """
    Encapsulates all IBKR API fetching operations with tenacity retry logic.

    Handles:
    - Fetching underliers (search)
    - Fetching option strikes
    - Fetching contract details
    - Retry logic via tenacity (exponential backoff with jitter)
    - HTTP error retrying (429, 5xx)

    Note: Rate limiting is handled externally by aiometer in the calling code.
    """

    def _should_retry_response(self, response: Response) -> bool:
        """Check if HTTP response indicates a retryable error (429 or 5xx)."""
        return response.status_code == 429 or (500 <= response.status_code < 600)

    def __init__(self, session: AsyncClient, signer: IbkrClient):
        """
        Initialize Fetcher with httpx session and IBKR signer.

        Args:
            session: httpx AsyncClient for HTTP requests
            signer: IbkrClient for OAuth authentication
        """
        self._session = session
        self._signer = signer

    # NOTE on retry policy: We use a single retry layer (tenacity) instead of
    # nesting tenacity with a manual for-loop. The previous manual loop counted
    # HTTP-error retries independently from tenacity's timeout retries, which
    # meant a timeout inside the inner loop could compound up to
    # MAX_RETRIES * MAX_RETRIES attempts. With one layer we cap cleanly at
    # MAX_RETRIES attempts and gain proper jittered backoff for free.
    #
    # `TimeoutException` is the parent of `PoolTimeout`, `ReadTimeout`,
    # `ConnectTimeout`, and `WriteTimeout` — catching the parent covers every
    # current and future httpx timeout subclass without further changes.
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_random_exponential(multiplier=1, max=MAX_BACKOFF),
        # Retry on transient transport / timeout errors. HTTP 429 and 5xx are
        # *also* transient, but they don't raise — they come back as a normal
        # `Response`, so we have to raise an `Exception` ourselves to feed
        # tenacity. See `_raise_for_retryable_status` below.
        retry=retry_if_exception_type((TimeoutException, _HTTPErrorForRetry)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _get_response(self, url: str) -> Response | None:
        """
        Make authenticated HTTP GET request to IBKR API with retry logic.

        Retries on:
        - httpx timeout/transport exceptions (via tenacity)
        - HTTP 429 (rate limit) and HTTP 5xx (server errors), by raising
          `_HTTPErrorForRetry` so tenacity's predicate catches them.

        Args:
            url: Full API endpoint URL

        Returns:
            httpx Response object on success; ``None`` only when retries are
            exhausted and the final attempt still returned a retryable HTTP
            status. (We return ``None`` rather than raising so the callers
            that already check ``response.status_code`` keep working.)

        Raises:
            tenacity.RetryError: when tenacity itself decides the call has
                exhausted its attempts (only for exception-class retries).
            httpx.TimeoutException: propagated when the *final* attempt
                still times out — also rare because tenacity reraises.
        """
        oauth_headers = self._signer._get_headers("GET", url)

        try:
            response = await self._session.get(
                url=url,
                headers=oauth_headers,
                timeout=GET_RESPONSE_TIME_OUT,
            )
        except (PoolTimeout, ReadTimeout, ConnectTimeout, TimeoutException) as exc:
            # Tenacity will retry; before_sleep_log announces the wait.
            raise

        if self._should_retry_response(response):
            # Raising lets tenacity's `retry_if_exception_type` decide whether
            # to retry. Tenacity counts this as attempt 1 of MAX_RETRIES.
            logger.warning(
                "Retryable HTTP status %s for %s", response.status_code, url,
            )
            raise _HTTPErrorForRetry(response.status_code)

        return response
    
    async def get_underliers(self, symbol: str) -> list[dict[str, str]]:
        """
        Fetch underlier information for a given symbol.

        Args:
            symbol: Stock/ETF/Index symbol (e.g., "SPY", "SPX")

        Returns:
            List of underlier data dictionaries (empty on failure).
        """
        url = UrlBuilder.build_underlier_url(symbol)
        logger.info("Fetching underliers for %s...", symbol)
        try:
            response = await self._get_response(url)
        except RetryError as exc:
            logger.error(
                "Failed to get underliers for %s after retries: %s",
                symbol, exc,
            )
            return []

        if response is None:
            logger.error("Failed to get underliers for %s: no response", symbol)
            return []

        if response.status_code == 200:
            data = response.json()
            logger.info("Successfully retrieved %s underlier(s)", len(data))
            return data
        else:
            logger.error(
                "Failed to get underliers for %s: HTTP %s",
                symbol, response.status_code,
            )
            return []

    async def get_strikes(self, conid: str, month: str, secType: str, exchange: str = "SMART") -> Response | None:
        """
        Fetch strike prices for a given contract and month.

        Args:
            conid: Contract ID of the underlying
            month: Expiration month (e.g., "JAN26")
            secType: Security type (e.g., "OPT")
            exchange: Exchange identifier

        Returns:
            httpx Response object with strike data, or ``None`` if the request
            could not be completed (transport exhaustion, retryable HTTP
            status, or a ``RetryError`` from tenacity).
        """
        url = UrlBuilder.build_strike_url(conid, month, secType, exchange)
        try:
            return await self._get_response(url)
        except RetryError as exc:
            logger.error(
                "Failed to get strikes for %s/%s after retries: %s",
                conid, month, exc,
            )
            return None

    async def get_contract(self, conid: str, month: str, strike: str, right: str, secType: str, exchange: str = "SMART") -> dict[str, str] | None:
        """
        Fetch contract details for a specific option.

        Args:
            conid: Contract ID of the underlying
            month: Expiration month (e.g., "JAN26")
            strike: Strike price
            right: Option type ("C" for call, "P" for put)
            secType: Security type (e.g., "OPT")
            exchange: Exchange identifier

        Returns:
            Dictionary with contract data, or None if failed (also on
            ``RetryError`` after tenacity has exhausted attempts).
        """
        url = UrlBuilder.build_contract_url(conid, month, strike, right, secType, exchange)
        try:
            response = await self._get_response(url)
        except RetryError as exc:
            logger.error(
                "Failed to get contract %s/%s/%s after retries: %s",
                conid, month, strike, exc,
            )
            return None

        if response is None:
            return None

        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                return data[0]
        return None
