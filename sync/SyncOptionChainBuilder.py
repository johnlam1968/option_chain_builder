# Synchronous option chain builder using SyncFetcher
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from SyncFetcher import SyncFetcher
from utils.database import store_data
from ibind import IbkrClient
from typing import List, Dict, Any
import time
from settings.config import DEFAULT_SYMBOL, DEFAULT_EXCHANGE
from utils.response_extraction import ResponseExtraction


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
        
        # Extract underlier info using ResponseExtraction
        extracted_info = ResponseExtraction.extract_underlier_info(underlier, self._symbol)
        if extracted_info is None:
            return
        
        conid, option_type, option_exchange, expiration_months = extracted_info
        
        # Validate extracted values
        if not option_type:
            print("No option type found in underlier data")
            return
        if not option_exchange:
            print("No exchange found in underlier data")
            return
        
        option_data: List[Dict[str, str | None]] = []
        start_time = time.time()
        
        # Iterate through months and strikes
        for month in expiration_months:
            strikes = self._fetcher.get_strikes(conid, month, option_type, option_exchange)
            if not strikes:
                print(f"No strikes found for {month}")
                continue
            
            # Extract call strikes using ResponseExtraction
            call_strikes = ResponseExtraction.extract_strikes_info(strikes)
            
            # Collect call and put results
            call_results = []
            put_results = []
            
            for strike in call_strikes:
                # Get call contract
                call_result = self._fetcher.get_contract(
                    conid, month, strike, "C", option_type, option_exchange
                )
                if call_result:
                    call_results.append(call_result)
                
                # Get put contract
                put_result = self._fetcher.get_contract(
                    conid, month, strike, "P", option_type, option_exchange
                )
                if put_result:
                    put_results.append(put_result)
            
            # Extract option data using ResponseExtraction
            month_option_data = ResponseExtraction.extract_option_results(
                call_results, put_results, self._symbol
            )
            option_data.extend(month_option_data)

        end_time = time.time()
        elapsed = end_time - start_time
        print(f"Fetched {len(option_data)} contracts in {elapsed} seconds.")
        
        store_data(option_data)  # type: ignore


if __name__ == "__main__":
    client = IbkrClient(use_oauth=True, timeout=15)
    builder = SyncOptionChainBuilder(client, DEFAULT_SYMBOL, DEFAULT_EXCHANGE)
    builder.get_option_chain()
