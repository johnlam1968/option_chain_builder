# Synchronous calls to IBKR API using ibind
from ibind import IbkrClient
from config import SEARCH_PATH, STRIKE_PATH, INFO_PATH
from typing import Union, Optional


class SyncFetcher:
    """
    Encapsulates synchronous IBKR API operations using ibind client.
    
    Handles:
    - Fetching underliers (search)
    - Fetching option strikes
    - Fetching contract details
    
    All methods return data directly or None on failure.
    """
    
    def __init__(self, client: IbkrClient):
        """
        Initialize SyncFetcher with IBKR client.
        
        Args:
            client: IbkrClient instance for API calls
        """
        self._client = client
    
    def get_underliers(self, symbol: str) -> Optional[Union[list, dict]]:
        """
        Fetch underlier information for a given symbol.
        
        Args:
            symbol: Stock/ETF/Index symbol (e.g., "CL", "ES", "SPX", "SPY")
            
        Returns:
            List/dict of underlier data, or None if failed
        """
        result = self._client.get(path=SEARCH_PATH, params={"symbol": symbol}).data
        return result
    
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
        result = self._client.get(path=STRIKE_PATH, params={
            "conid": conid,
            "sectype": sectype,
            "month": month,
            "exchange": exchange
        }).data
        return result
    
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
        try:
            result = self._client.get(path=INFO_PATH, params={
                "conid": conid,
                "secType": sectype,
                "month": month,
                "strike": strike,
                "right": right,
                "exchange": exchange
            }).data
            # Handle both list and dict responses - always return dict
            if isinstance(result, list) and len(result) > 0:
                return result[0]  # type: ignore
            return result  # type: ignore
        except Exception as e:
            return None
