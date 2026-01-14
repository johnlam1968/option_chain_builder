# Synchronous option chain builder using SyncFetcher
from SyncFetcher import SyncFetcher
from store_data import store_data
from ibind import IbkrClient
from typing import List, Dict
import time
from config import DEFAULT_SYMBOL, DEFAULT_EXCHANGE


class SyncOptionChainBuilder:
    """
    Synchronous builder for option chains using SyncFetcher.
    
    Uses simple, high-level code with direct API calls.
    """
    
    def __init__(self, client: IbkrClient, symbol: str, exchange: str = "SMART"):
        """
        Initialize SyncOptionChainBuilder with IBKR client.
        
        Args:
            client: IbkrClient instance for API calls
            symbol: Stock/ETF/Index symbol (e.g., "CL", "SPY")
            exchange: Exchange identifier (e.g., "SMART", "NYMEX")
        """
        self._fetcher = SyncFetcher(client)
        self._symbol = symbol
        self._exchange = exchange
    
    def get_option_chain(self) -> None:
        """
        Build complete option chain for the configured symbol.
        
        Main entry point for synchronous option chain building.
        """
        # Get underlier information
        underliers = self._fetcher.get_underliers(self._symbol)
        if not underliers:
            print(f"Cannot find underlier for {self._symbol}")
            return
        
        underlier = underliers[0]  # type: ignore
        conid = underlier.get("conid")
        
        if not conid:
            print(f"No contract ID found for {self._symbol}")
            return
        
        sections = underlier.get("sections", [{}])
        if len(sections) < 2:
            print("No derivatives found for underlier")
            return

        # Get option section (handle special exchange types)
        underlier_section = sections[0]
        if underlier_section.get('exchange') in {"SEHK;", "HKFE;"} or underlier_section.get('secType') == 'IND':
            option_section = sections[2]
            print(f"Option Section: {option_section}")
        else:
            option_section = sections[1]

        option_type = option_section.get('secType')
        option_exchange = option_section.get('exchange')
        # Extract only the first exchange if multiple are provided
        if option_exchange and ';' in option_exchange:
            option_exchange = option_exchange.split(';')[0]
        expiration_months = option_section.get("months", "").split(";")
        option_data: List[Dict[str, str | None]] = []
        start_time = time.time()
        
        # Iterate through months and strikes
        for month in expiration_months:
            strikes = self._fetcher.get_strikes(conid, month, option_type, option_exchange)
            if not strikes:
                print(f"No strikes found for {month}")
                continue
            
            # strikes can be either dict or list, handle both cases
            if isinstance(strikes, dict):
                call_strikes = strikes.get("call", [])
            elif isinstance(strikes, list):
                call_strikes = strikes
            else:
                continue
            
            for strike in call_strikes:
                # Get call contract
                call_result = self._fetcher.get_contract(
                    conid, month, strike, "C", option_type, option_exchange
                )
                
                if call_result:
                    call_conid = call_result.get("conid")  # type: ignore
                    call_maturity_date = call_result.get("maturityDate")  # type: ignore
                    option_data.append({
                        "symbol": self._symbol,
                        "maturity_date": call_maturity_date,
                        "strike": strike,
                        "right": "C",
                        "conid": call_conid,
                    })
                
                # Get put contract
                put_result = self._fetcher.get_contract(
                    conid, month, strike, "P", option_type, option_exchange
                )
                
                if put_result:
                    put_conid = put_result.get("conid")  # type: ignore
                    put_maturity_date = put_result.get("maturityDate")  # type: ignore
                    option_data.append({
                        "symbol": self._symbol,
                        "maturity_date": put_maturity_date,
                        "strike": strike,
                        "right": "P",
                        "conid": put_conid,
                    })

        end_time = time.time()
        elapsed = end_time - start_time
        print(f"Fetched {len(option_data)} contracts in {elapsed} seconds.")
        
        store_data(option_data)  # type: ignore


if __name__ == "__main__":
    client = IbkrClient(use_oauth=True, timeout=15)
    builder = SyncOptionChainBuilder(client, DEFAULT_SYMBOL, DEFAULT_EXCHANGE)
    builder.get_option_chain()
