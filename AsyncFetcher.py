# Direct calls to IBKR API using httpx with async rate limiting and error handling
# ibind client for OAuth signing
import asyncio
import random
from httpx import AsyncClient, Response, PoolTimeout, TimeoutException, ReadTimeout, ConnectTimeout
from aiolimiter import AsyncLimiter
import json
import os
from functools import wraps

from ibind.client.ibkr_client import IbkrClient # type: ignore
from typing import Any, List, Dict, Callable, Optional
from RetryHandler import RetryHandler
from config import SEARCH_PATH, STRIKE_PATH, INFO_PATH, STATE_FILE, MAX_RATE, IBKR_BASE_URL, GET_RESPONSE_TIME_OUT


# Create global retry handler instance for convenience
retry_handler = RetryHandler()


def retry_with_backoff(max_retries: Optional[int] = None, initial_backoff: Optional[float] = None, 
                     backoff_multiplier: Optional[float] = None, max_backoff: Optional[float] = None):
    """
    Decorator for async functions that implements retry logic with exponential backoff using RetryHandler class.
    """
    def decorator(func: Callable) -> Callable:
        handler = RetryHandler(
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            backoff_multiplier=backoff_multiplier,
            max_backoff=max_backoff
        )
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await handler.retry_async(func, *args, **kwargs)
        
        return wrapper
    return decorator


# Rate limiter for API calls
limiter = AsyncLimiter(10, 1)


class AsyncFetcher:
    """
    Encapsulates all IBKR API fetching operations with retry logic and rate limiting.
    
    Handles:
    - Fetching underliers (search)
    - Fetching option strikes
    - Fetching contract details
    - Rate limiting
    - Retry logic via RetryHandler
    """
    
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
    
    @retry_with_backoff()
    async def _get_response(self, url: str) -> Response:
        """
        Make authenticated HTTP GET request to IBKR API with retry logic.
        
        Args:
            url: Full API endpoint URL
            
        Returns:
            httpx Response object
        """
        oauth_headers = self._signer._get_headers("GET", url)
        response = await self._session.get(
            url=url,
            headers=oauth_headers, 
            timeout=GET_RESPONSE_TIME_OUT
        )
        return response
    
    async def get_underliers(self, symbol: str) -> List[Dict[str, str]]:
        """
        Fetch underlier information for a given symbol.
        
        Args:
            symbol: Stock/ETF/Index symbol (e.g., "SPY", "SPX")
            
        Returns:
            List of underlier data dictionaries
        """
        url = self._build_underlier_url(symbol)
        response = await self._get_response(url)
        return response.json()
    
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
    
    async def get_contract(self, conid: str, month: str, strike: str, right: str, secType: str, exchange: str = "SMART") -> Dict[str, str] | None:
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
        return await self._get_response(url)

    async def fetch_with_limiting(self, function: Callable[..., Any], *args: Any) -> List[Dict[str, str]] | Dict[str, List[str]] | Dict[str, str] | None:
        """
        Execute a fetch function with rate limiting.
        
        Args:
            function: Async fetch function to execute
            *args: Arguments to pass to function
            
        Returns:
            Parsed response data or None if failed
        """
        async with limiter:
            try:
                response = await function(*args)

                if not response:
                    return None

                # Handle dict responses
                if isinstance(response, dict):
                    return response

                # Handle Response objects with status_code
                if hasattr(response, 'status_code'):
                    if response.status_code == 200:
                        # Parse JSON and format appropriately
                        _dict = response.json()
                        if function == self.get_contract:
                            return _dict
                        elif function == self.get_strikes:
                            _call_strikes = _dict.get("call", [])
                            month = args[1]
                            return {month: _call_strikes}

                    elif response.status_code == 429:
                        print(f"⚠️ Rate limit hit (429). Waiting 15 minutes due to IP ban...")
                        await asyncio.sleep(900)
                        return None

            except (PoolTimeout, ReadTimeout, ConnectTimeout) as e:
                print(f"⏱️ Timeout ({type(e).__name__}): {e}")
                return None
            except Exception as e:
                print(f"❌ Unexpected error: {type(e).__name__}: {e}")
                return None
        
        return None


# Backward compatibility functions
async def get_underliers_async(session: AsyncClient, signer: IbkrClient, symbol: str) -> List[Dict[str, str]]:
    """Legacy wrapper for backward compatibility."""
    fetcher = AsyncFetcher(session, signer)
    return await fetcher.get_underliers(symbol)

async def get_strikes_async(session: AsyncClient, signer: IbkrClient, conid: str, month: str, secType: str, exchange: str = "SMART") -> Response:
    """Legacy wrapper for backward compatibility."""
    fetcher = AsyncFetcher(session, signer)
    return await fetcher.get_strikes(conid, month, secType, exchange)

async def get_contracts_async(session: AsyncClient, signer: IbkrClient, conid: str, month: str, strike: str, right: str, secType: str, exchange: str = "SMART") -> Dict[str, str] | None:
    """Legacy wrapper for backward compatibility."""
    fetcher = AsyncFetcher(session, signer)
    return await fetcher.get_contract(conid, month, strike, right, secType, exchange)

async def async_limiting(session: AsyncClient, signer: IbkrClient, function: Callable[..., Any], *args: Any) -> List[Dict[str, str]] | Dict[str, List[str]] | Dict[str, str] | None:
    """Legacy wrapper for backward compatibility."""
    fetcher = AsyncFetcher(session, signer)
    return await fetcher.fetch_with_limiting(function, *args)
