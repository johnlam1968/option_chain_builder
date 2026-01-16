# Synchronous calls to IBKR API using ibind
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ibind import IbkrClient
from typing import Union, Optional
from SyncRetryHandler import SyncRetryHandler
from utils.url_builder import UrlBuilder
from settings.config import SEARCH_PATH, STRIKE_PATH, INFO_PATH


class SyncFetcher:
    """
    Encapsulates synchronous IBKR API operations using ibind client.
    
    Handles:
    - Fetching underliers (search)
    - Fetching option strikes
    - Fetching contract details
    - Retry logic for 429 rate limits and 5xx server errors
    
    All methods return data directly or None on failure.
    """
    
    def __init__(self, client: IbkrClient):
        """
        Initialize SyncFetcher with IBKR client.
        
        Args:
            client: IbkrClient instance for API calls
        """
        self._client = client
        self._retry_handler = SyncRetryHandler()
    
    def get_underliers(self, symbol: str) -> Optional[Union[list, dict]]:
        """
        Fetch underlier information for a given symbol.
        
        Args:
            symbol: Stock/ETF/Index symbol (e.g., "CL", "ES", "SPX", "SPY")
            
        Returns:
            List/dict of underlier data, or None if failed
        """
        def _make_request():
            params = UrlBuilder.build_underlier_params(symbol)
            return self._client.get(path=SEARCH_PATH, params=params)
        
        result = self._retry_handler.retry(_make_request)
        if result is not None:
            return result.data
        return None
    
    def get_strikes(self, conid: str, month: str, sectype: str, exchange: str = "SMART") -> Optional[Union[list, dict]]:
        """
        Fetch strike prices for a given contract and month.
        
        Args:
            conid: Contract ID of the underlying (e.g., "265598")
            month: Expiration month (e.g., "MAR26")
            sectype: Security type (e.g., "OPT")
            exchange: Exchange identifier (e.g., "SMART", "NYMEX")
            
        Returns:
            List/dict of strike data, or None if failed
        """
        def _make_request():
            params = UrlBuilder.build_strike_params(conid, month, sectype, exchange)
            return self._client.get(path=STRIKE_PATH, params=params)
        
        result = self._retry_handler.retry(_make_request)
        if result is not None:
            return result.data
        return None
    
    def get_contract(self, conid: str, month: str, strike: str, right: str, sectype: str, exchange: str = "SMART") -> Optional[dict]:
        """
        Fetch contract details for a specific option.
        
        Args:
            conid: Contract ID of the underlying (e.g., "265598")
            month: Expiration month (e.g., "MAR26")
            strike: Strike price (e.g., "100")
            right: Option type ("C" for call, "P" for put)
            sectype: Security type (e.g., "OPT")
            exchange: Exchange identifier (e.g., "SMART", "NYMEX")
            
        Returns:
            Dictionary with contract data, or None if failed
        """
        def _make_request():
            params = UrlBuilder.build_contract_params(conid, month, strike, right, sectype, exchange)
            return self._client.get(path=INFO_PATH, params=params)
        
        result = self._retry_handler.retry(_make_request)
        if result is not None:
            data = result.data
            # Handle both list and dict responses - always return dict
            if isinstance(data, list) and len(data) > 0:
                return data[0]  # type: ignore
            return data  # type: ignore
        return None
