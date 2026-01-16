"""
ResponseExtraction class for standardizing IBKR API response parsing.

This class provides static methods to extract structured information from
IBKR API responses, making it shareable between synchronous and
asynchronous implementations.
"""

from typing import List, Dict, Tuple, Optional, Any


class ResponseExtraction:
    """
    Utility class for extracting structured data from IBKR API responses.
    
    All methods are static and don't require instantiation.
    """
    
    @staticmethod
    def extract_underlier_info(
        underlier: Dict[str, Any],
        symbol: str
    ) -> Optional[Tuple[str, Optional[str], Optional[str], List[str]]]:
        """
        Extract option-related information from underlier data.
        
        Args:
            underlier: Underlier dictionary from API response
            symbol: Symbol name for error messages
            
        Returns:
            Tuple containing (conid, option_type, option_exchange, expiration_months)
            or None if extraction fails
        """
        conid = underlier.get("conid")
        
        if not conid:
            print(f"No contract ID found for {symbol}")
            return None
        
        sections = underlier.get("sections", [{}])
        if len(sections) < 2:
            print("No derivatives found for underlier")
            return None

        # Get option section (handle special exchange types)
        underlier_section = sections[0]
        if underlier_section.get('exchange') in {"SEHK;", "HKFE;"}:
            option_section = sections[2]
            print(f"Option Section: {option_section}")
        else:
            option_section = sections[1]

        option_type = option_section.get('secType')
        option_exchange = option_section.get('exchange')
        
        # Extract only to first exchange if multiple are provided
        if option_exchange and ';' in option_exchange:
            option_exchange = option_exchange.split(';')[0]
        
        expiration_months = option_section.get("months", "").split(";")
        
        return conid, option_type, option_exchange, expiration_months
    
    @staticmethod
    def extract_strikes_info(strikes: Any) -> List[str]:
        """
        Extract call strike list from strikes response.
        
        The API always returns a dict in this format:
        {
            "call": [200.0, {...}, 7800.0],
            "put": [200.0, {...}, 7800.0]
        }
        
        Args:
            strikes: Response from get_strikes endpoint (dict with "call" and "put" keys)
            
        Returns:
            List of strike prices (strings)
        """
        # Handle the standardized API response format
        if isinstance(strikes, dict):
            call_strikes = strikes.get("call", [])
            # Convert to list of strings
            if isinstance(call_strikes, list):
                return [str(strike) for strike in call_strikes if strike is not None]
            return []
        else:
            # Fallback for unexpected formats
            return []
    
    @staticmethod
    def extract_option_results(
        call_results: List[Any],
        put_results: List[Any],
        symbol: str
    ) -> List[Dict[str, str | None]]:
        """
        Process call and put contract results into standardized option data.
        
        Args:
            call_results: List of call contract results from API
            put_results: List of put contract results from API
            symbol: Symbol name for all contracts
            
        Returns:
            List of standardized option contract dictionaries
        """
        option_data: List[Dict[str, str | None]] = []
        
        # Process call results
        for call_result in call_results:
            if not call_result:
                continue
            
            call_conid = call_result.get("conid")
            call_maturity_date = call_result.get("maturityDate")
            call_strike = call_result.get("strike")
            
            if all([call_conid, call_maturity_date, call_strike]):
                option_data.append({
                    "symbol": symbol,
                    "maturity_date": call_maturity_date,
                    "strike": call_strike,
                    "right": "C",
                    "conid": call_conid,
                })
        
        # Process put results
        for put_result in put_results:
            if not put_result:
                continue
            
            put_conid = put_result.get("conid")
            put_maturity_date = put_result.get("maturityDate")
            put_strike = put_result.get("strike")
            
            if all([put_conid, put_maturity_date, put_strike]):
                option_data.append({
                    "symbol": symbol,
                    "maturity_date": put_maturity_date,
                    "strike": put_strike,
                    "right": "P",
                    "conid": put_conid,
                })
        
        return option_data
