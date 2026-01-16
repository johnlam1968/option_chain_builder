# Direct calls to IBKR API using httpx with tenacity retry logic
# ibind client for OAuth signing
import logging
import asyncio
from httpx import AsyncClient, Response, PoolTimeout, ReadTimeout, ConnectTimeout

from ibind.client.ibkr_client import IbkrClient  # type: ignore
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError
)
from config import (
    SEARCH_PATH, STRIKE_PATH, INFO_PATH, IBKR_BASE_URL, 
    GET_RESPONSE_TIME_OUT, MAX_RETRIES, MAX_BACKOFF
)

# Configure logger for tenacity
logger = logging.getLogger(__name__)


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
    
    def _build_underlier_url(self, underlier: str) -> str:
        """Build URL for underlier search endpoint."""
        endpoint = SEARCH_PATH + f"?symbol={underlier}"
        return f"{IBKR_BASE_URL}{endpoint}"
    
    def _build_strike_url(self, conid: str, month: str, secType: str, exchange: str = "SMART") -> str:
        """Build URL for strikes endpoint."""
        clean_month = month.replace(" ", "")
        if exchange == "SMART":
            endpoint = STRIKE_PATH + f"?conid={conid}&sectype={secType}&month={clean_month}"
        else:
            endpoint = STRIKE_PATH + f"?conid={conid}&sectype={secType}&month={clean_month}&exchange={exchange}"
        return f"{IBKR_BASE_URL}{endpoint}"
    
    def _build_contract_url(self, conid: str, month: str, strike: str, right: str, secType: str, exchange: str) -> str:
        """Build URL for contract info endpoint."""
        if " " not in month:
            month = f"{month[:3]} {month[3:]}"
        endpoint = INFO_PATH + f"?conid={conid}&secType={secType}&month={month}&strike={strike}&right={right}&exchange={exchange}"
        return f"{IBKR_BASE_URL}{endpoint}"
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_random_exponential(multiplier=1, max=MAX_BACKOFF),
        retry=retry_if_exception_type((PoolTimeout, ReadTimeout, ConnectTimeout)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def _get_response(self, url: str) -> Response:
        """
        Make authenticated HTTP GET request to IBKR API with retry logic.
        
        Handles retries for:
        - Timeout exceptions (via tenacity decorator)
        - HTTP 429 (rate limit)
        - HTTP 5xx (server errors)
        
        Args:
            url: Full API endpoint URL
            
        Returns:
            httpx Response object
            
        Raises:
            RetryError: After max retries exhausted
        """
        oauth_headers = self._signer._get_headers("GET", url)
        
        # Manual retry loop for HTTP errors (429, 5xx)
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._session.get(
                    url=url,
                    headers=oauth_headers, 
                    timeout=GET_RESPONSE_TIME_OUT
                )
                
                # Check if response indicates a retryable HTTP error
                if self._should_retry_response(response):
                    if attempt < MAX_RETRIES - 1:
                        backoff_time = min(1.0 * (2 ** attempt), MAX_BACKOFF)
                        if response.status_code == 429:
                            print(f"⚠️ Rate limit hit (429). Retry {attempt + 1}/{MAX_RETRIES} after {backoff_time:.1f}s")
                        else:
                            print(f"⚠️ Server error {response.status_code}. Retry {attempt + 1}/{MAX_RETRIES} after {backoff_time:.1f}s")
                        await asyncio.sleep(backoff_time)
                        continue
                    else:
                        # Max retries exhausted for HTTP error
                        print(f"❌ HTTP error {response.status_code} after {MAX_RETRIES} retries. Giving up.")
                        return response
                
                # Success (non-retryable response) - return immediately
                return response
                
            except (PoolTimeout, ReadTimeout, ConnectTimeout):
                # Let tenacity handle timeout retries
                raise
        
        # Should not reach here due to tenacity decorator
        return None  # type: ignore
    
    async def get_underliers(self, symbol: str) -> list[dict[str, str]]:
        """
        Fetch underlier information for a given symbol.
        
        Args:
            symbol: Stock/ETF/Index symbol (e.g., "SPY", "SPX")
            
        Returns:
            List of underlier data dictionaries
        """
        url = self._build_underlier_url(symbol)
        print(f"Fetching underliers for {symbol}...")
        response = await self._get_response(url)
        
        if response.status_code == 200:
            data = response.json()
            print(f"Successfully retrieved {len(data)} underlier(s)")
            return data
        else:
            print(f"Failed to get underliers for {symbol}: HTTP {response.status_code}")
            return []
    
    async def get_strikes(self, conid: str, month: str, secType: str, exchange: str = "SMART") -> Response:
        """
        Fetch strike prices for a given contract and month.
        
        Args:
            conid: Contract ID of the underlying
            month: Expiration month (e.g., "JAN26")
            secType: Security type (e.g., "OPT")
            exchange: Exchange identifier
            
        Returns:
            httpx Response object with strike data
        """
        url = self._build_strike_url(conid, month, secType, exchange)
        return await self._get_response(url)
    
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
            Dictionary with contract data, or None if failed
        """
        url = self._build_contract_url(conid, month, strike, right, secType, exchange)
        response = await self._get_response(url)
        
        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                return data[0]
        return None
