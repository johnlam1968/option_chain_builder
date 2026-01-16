"""
UrlBuilder class for standardizing IBKR API URL construction.

This class provides static methods to build consistent URLs for
IBKR API endpoints, making it shareable between synchronous and
asynchronous implementations.
"""

from typing import Dict, Optional
from settings.config import IBKR_BASE_URL, SEARCH_PATH, STRIKE_PATH, INFO_PATH


class UrlBuilder:
    """
    Utility class for building IBKR API URLs.
    
    All methods are static and don't require instantiation.
    """
    
    @staticmethod
    def build_underlier_url(symbol: str) -> str:
        """
        Build URL for underlier search endpoint.
        
        Args:
            symbol: Stock/ETF/Index symbol (e.g., "SPY", "CL", "ES")
            
        Returns:
            Full URL for underlier search endpoint
        """
        endpoint = f"{SEARCH_PATH}?symbol={symbol}"
        return f"{IBKR_BASE_URL}{endpoint}"
    
    @staticmethod
    def build_strike_url(conid: str, month: str, sectype: str, exchange: str = "SMART") -> str:
        """
        Build URL for strikes endpoint.
        
        Args:
            conid: Contract ID of the underlying
            month: Expiration month (e.g., "JAN26", "MAR 26")
            sectype: Security type (e.g., "OPT")
            exchange: Exchange identifier (default: "SMART")
            
        Returns:
            Full URL for strikes endpoint
        """
        # Clean month (remove spaces)
        clean_month = month.replace(" ", "")
        
        # Build endpoint - exchange only included if not SMART
        if exchange == "SMART":
            endpoint = f"{STRIKE_PATH}?conid={conid}&sectype={sectype}&month={clean_month}"
        else:
            endpoint = f"{STRIKE_PATH}?conid={conid}&sectype={sectype}&month={clean_month}&exchange={exchange}"
        
        return f"{IBKR_BASE_URL}{endpoint}"
    
    @staticmethod
    def build_contract_url(
        conid: str, 
        month: str, 
        strike: str, 
        right: str, 
        sectype: str, 
        exchange: str = "SMART"
    ) -> str:
        """
        Build URL for contract info endpoint.
        
        Args:
            conid: Contract ID of the underlying
            month: Expiration month (e.g., "JAN26", "MAR 26")
            strike: Strike price
            right: Option type ("C" for call, "P" for put)
            sectype: Security type (e.g., "OPT")
            exchange: Exchange identifier (default: "SMART")
            
        Returns:
            Full URL for contract info endpoint
        """
        # Format month: "JAN26" -> "JAN 26" if not already formatted
        if " " not in month:
            formatted_month = f"{month[:3]} {month[3:]}"
        else:
            formatted_month = month
        
        # Build endpoint
        endpoint = (
            f"{INFO_PATH}?conid={conid}&secType={sectype}&month={formatted_month}"
            f"&strike={strike}&right={right}&exchange={exchange}"
        )
        
        return f"{IBKR_BASE_URL}{endpoint}"
    
    # Parameter building methods for ibind (sync implementation)
    
    @staticmethod
    def build_underlier_params(symbol: str) -> Dict[str, str]:
        """
        Build parameters for underlier search endpoint (for ibind).
        
        Args:
            symbol: Stock/ETF/Index symbol (e.g., "SPY", "CL")
            
        Returns:
            Dictionary of query parameters
        """
        return {"symbol": symbol}
    
    @staticmethod
    def build_strike_params(conid: str, month: str, sectype: str, exchange: str = "SMART") -> Dict[str, str]:
        """
        Build parameters for strikes endpoint (for ibind).
        
        Args:
            conid: Contract ID of the underlying
            month: Expiration month (e.g., "JAN26")
            sectype: Security type (e.g., "OPT")
            exchange: Exchange identifier (default: "SMART")
            
        Returns:
            Dictionary of query parameters
        """
        params = {
            "conid": conid,
            "sectype": sectype,
            "month": month
        }
        if exchange != "SMART":
            params["exchange"] = exchange
        return params
    
    @staticmethod
    def build_contract_params(
        conid: str, 
        month: str, 
        strike: str, 
        right: str, 
        sectype: str, 
        exchange: str = "SMART"
    ) -> Dict[str, str]:
        """
        Build parameters for contract info endpoint (for ibind).
        
        Args:
            conid: Contract ID of the underlying
            month: Expiration month (e.g., "JAN26", "MAR 26")
            strike: Strike price
            right: Option type ("C" for call, "P" for put)
            sectype: Security type (e.g., "OPT")
            exchange: Exchange identifier (default: "SMART")
            
        Returns:
            Dictionary of query parameters
        """
        # Format month: "JAN26" -> "JAN 26" if not already formatted
        if " " not in month:
            formatted_month = f"{month[:3]} {month[3:]}"
        else:
            formatted_month = month
        
        return {
            "conid": conid,
            "secType": sectype,
            "month": formatted_month,
            "strike": strike,
            "right": right,
            "exchange": exchange
        }
