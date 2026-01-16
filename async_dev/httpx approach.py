# Refactored with aiometer and tenacity
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import asyncio
import functools
from typing import List, Dict
from utils.database import store_data
import httpx
from httpx import AsyncClient
from AsyncFetcher import AsyncFetcher
from ibind import IbkrClient
from utils.session_health_helper import create_session_aware_client
import time
from aiometer import run_all
from settings.config import (
    DEFAULT_SYMBOL, DEFAULT_EXCHANGE, DEFAULT_USE_LOOP, 
    GET_RESPONSE_TIME_OUT, MAX_RATE, MAX_CONCURRENCY,
    MAX_CONNECTIONS, MAX_KEEPALIVE_CONNECTIONS, KEEPALIVE_EXPIRY
)
from utils.response_extraction import ResponseExtraction

load_dotenv()

# Suppress INFO logs (only show WARNING and above)
import logging
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('ibind').setLevel(logging.WARNING)
logging.getLogger('ibind_fh').setLevel(logging.WARNING)
logging.getLogger('ibind_ibkr_client').setLevel(logging.WARNING)


class AsyncOptionChainBuilder:
    def __init__(
        self, 
        session: AsyncClient, 
        signer: IbkrClient, 
        symbol: str, 
        exchange: str = "SMART", 
        use_loop: bool = False,
        show_progress: bool = False
    ):
        """
        Initialize AsyncOptionChainBuilder.
        
        Args:
            session: httpx AsyncClient for HTTP requests
            signer: IbkrClient for OAuth authentication
            symbol: Stock/ETF/Index symbol
            exchange: Exchange identifier (default: "SMART")
            use_loop: If True, use sequential loop instead of batch processing
            show_progress: If True, show progress indicators during fetching
        """
        self._session = session
        self._signer = signer
        self._symbol = symbol
        self._exchange = exchange
        self.use_loop = use_loop
        self.show_progress = show_progress
        
        # Initialize Fetcher for all IBKR API operations
        self._fetcher = AsyncFetcher(session, signer)

    async def get_option_chain_async(self) -> None:
        """Main method to fetch complete option chain for a symbol."""
        
        # Get underlier information
        _underliers = await self._fetcher.get_underliers(self._symbol)
        
        if not _underliers or len(_underliers) == 0:
            print(f"No underliers found for symbol {self._symbol}")
            return
            
        _underlier = _underliers[0]  # type: ignore
        
        # Extract underlier info using ResponseExtraction
        extracted_info = ResponseExtraction.extract_underlier_info(_underlier, self._symbol)
        if extracted_info is None:
            return
        
        _conid, _option_type, _option_exchange, expiration_months = extracted_info
        
        # Validate extracted values
        if not _option_type:
            print("No option type found in underlier data")
            return
        if not _option_exchange:
            print("No exchange found in underlier data")
            return

        # Fetch strikes for all expiration months using aiometer
        _strike_tasks = [
            functools.partial(self._fetcher.get_strikes, _conid, month, _option_type, _option_exchange)
            for month in expiration_months
        ]
        
        _strike_responses = await run_all(
            _strike_tasks,
            max_at_once=MAX_CONCURRENCY,
            max_per_second=MAX_RATE
        )
        
        # Parse strike responses
        _strike_dicts = []
        for month, response in zip(expiration_months, _strike_responses):
            if response and response.status_code == 200:
                _dict = response.json()
                # Extract call strikes using ResponseExtraction
                _call_strikes = ResponseExtraction.extract_strikes_info(_dict)
                _strike_dicts.append({month: _call_strikes})
            else:
                print(f"Failed to fetch strikes for {month}")

        # Choose processing method
        start_time = time.time()
        if self.use_loop:
            await self.get_option_chain_loop(_conid, _option_type, _option_exchange, _strike_dicts)
        else:
            await self.get_option_chain_gather(_conid, _option_type, _option_exchange, _strike_dicts)
        end_time = time.time()
        print(f"Time taken: {end_time - start_time}")

    async def get_option_chain_loop(self, conid, option_type, option_exchange, list_of_dict) -> None:
        """Fetch option chain using sequential loop with Fetcher class."""
        stat_time = time.time()
        
        # Collect call and put results
        call_results = []
        put_results = []
        
        for _dict in list_of_dict:
            for k, v in _dict.items():
                month = k
                strikes = v
                for strike in strikes:
                    # Use Fetcher for contract details
                    c_response = await self._fetcher.get_contract(conid, month, strike, "C", option_type, option_exchange)
                    if c_response:
                        call_results.append(c_response)

                    p_response = await self._fetcher.get_contract(conid, month, strike, "P", option_type, option_exchange)
                    if p_response:
                        put_results.append(p_response)

        end_time = time.time()
        _lapse = end_time - stat_time
        
        # Extract option data using ResponseExtraction
        option_data = ResponseExtraction.extract_option_results(
            call_results, put_results, self._symbol
        )
        
        print(f"Retrieved {len(option_data)} contracts in {_lapse}")
        store_data(option_data)

    async def get_option_chain_gather(self, conid, option_type, option_exchange, strike_dicts) -> None:
        """Fetch option chain using aiometer for rate limiting and concurrency control."""
        option_data: List[Dict[str, str | None]] = []
        
        # Collect all tasks
        _call_tasks = []
        _put_tasks = []
        
        for _dict in strike_dicts:
            for k, v in _dict.items():
                month = k
                strikes = v
                for strike in strikes:
                    _call_tasks.append(
                        functools.partial(self._fetcher.get_contract, conid, month, strike, "C", option_type, option_exchange)
                    )
                    _put_tasks.append(
                        functools.partial(self._fetcher.get_contract, conid, month, strike, "P", option_type, option_exchange)
                    )

        import time
        start_time = time.time()
        
        # Use aiometer to process all call tasks with rate limiting and concurrency control
        print(f"Fetching {len(_call_tasks)} call contracts...")
        _call_result_list = await run_all(
            _call_tasks,
            max_at_once=MAX_CONCURRENCY,
            max_per_second=MAX_RATE
        )
        
        print(f"Fetching {len(_put_tasks)} put contracts...")
        _put_result_list = await run_all(
            _put_tasks,
            max_at_once=MAX_CONCURRENCY,
            max_per_second=MAX_RATE
        )

        end_time = time.time()
        print(f"Fetched {len(_call_result_list) + len(_put_result_list)} contracts in {end_time - start_time} seconds.")

        # Extract option data using ResponseExtraction
        option_data = ResponseExtraction.extract_option_results(
            _call_result_list, _put_result_list, self._symbol
        )

        _task_length = len(_call_tasks) + len(_put_tasks)
        _retrieved_length = len(option_data)
        _diff = _task_length - _retrieved_length
        print(f"Retrieved {_retrieved_length} out of requested {_task_length}, with {_diff} not retrieved.")

        store_data(option_data)

if __name__ == "__main__":
    # Redirect stdout to log file
    import datetime
    import sys
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/async_test_{timestamp}.log"
    
    with open(log_file, 'w') as f:
        sys.stdout = f
        
        try:
            print(f"Starting async test for {DEFAULT_SYMBOL} at {timestamp}")
            
            # Create IBKR client with session health management
            _session_manager = create_session_aware_client(
                use_oauth=True,
                timeout=15,
                retry_on_410=True,
                max_health_retries=3,
                health_check_interval=60.0,  # Check session health every 60 seconds
                tickler_retry_delay=5.0,
                auto_reinitialize=True
            )
            
            if _session_manager is None:
                print("❌ Failed to create IBKR client. Please check your OAuth credentials.")
                sys.exit(1)
            
            print("IBKR client created successfully with session health management")
            
            # Get the client from the session manager
            _signer = _session_manager.client
            
            # Configure connection pool to prevent PoolTimeout
            # Note: IBKR uses HTTP/1.1 (no multiplexing), so connection pool is critical
            _session = AsyncClient(
                limits=httpx.Limits(
                    max_connections=MAX_CONNECTIONS,
                    max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
                    keepalive_expiry=KEEPALIVE_EXPIRY
                ),
                timeout=GET_RESPONSE_TIME_OUT
            )
            print(f"AsyncClient created with connection pool: max={MAX_CONNECTIONS}, keepalive={MAX_KEEPALIVE_CONNECTIONS}")
            
            _symbol = DEFAULT_SYMBOL
            print(f"Creating AsyncOptionChainBuilder for {_symbol}/{DEFAULT_EXCHANGE}")
            
            # Ensure session is healthy before starting
            _healthy_client = _session_manager.ensure_healthy_session()
            if _healthy_client is None:
                print("❌ Failed to establish healthy session. Please check your connection and try again.")
                sys.exit(1)
            
            chain_builder = AsyncOptionChainBuilder(
                _session, 
                _signer, 
                _symbol, 
                DEFAULT_EXCHANGE, 
                DEFAULT_USE_LOOP,
                show_progress=False  # Set to True to see progress indicators
            )
            
            # Build option chain
            asyncio.run(chain_builder.get_option_chain_async())
            
            print("\n" + "="*50)
            print("Async test completed successfully!")
            print("="*50)
            
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            sys.stdout = sys.__stdout__
    
    print(f"Async test log saved to: {log_file}")
