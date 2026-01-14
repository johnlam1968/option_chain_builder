# This does not work well yet.
from dotenv import load_dotenv
import asyncio
from typing import List, Dict
from store_data import store_data
import httpx
from httpx import AsyncClient
from AsyncFetcher import AsyncFetcher
from ibind import IbkrClient
import time
from config import DEFAULT_SYMBOL, DEFAULT_EXCHANGE, GET_RESPONSE_TIME_OUT

load_dotenv()

class AsyncOptionChainBuilder:
    def __init__(self, session: AsyncClient, signer: IbkrClient, symbol: str, exchange: str = "SMART", use_loop: bool = False):
        self._session = session
        self._signer = signer
        self._symbol = symbol
        self._exchange = exchange
        self.use_loop = use_loop
        
        # Initialize Fetcher for all IBKR API operations
        self._fetcher = AsyncFetcher(session, signer)

    async def get_option_chain_async(self) -> None:
        """Main method to fetch complete option chain for a symbol."""
        
        # Get underlier information
        _underliers = await self._fetcher.get_underliers(self._symbol)
        _underlier = _underliers[0]  # type: ignore
        _conid = _underlier.get("conid")
        
        if not _conid:
            return
        
        _sections = _underlier.get("sections", [{}])
        if len(_sections) < 2:
            print("No derivatives found for underlier")
            return

        _underlier_section = _sections[0]
        # Handle special exchange types (HK/China)
        if _underlier_section.get('exchange') in {"SEHK;", "HKFE;"} or _underlier_section.get('secType') == 'IND':
            _option_section = _sections[2]
            print(f"Option Section: {_option_section}")
        else:
            _option_section = _sections[1]

        _option_type = _option_section.get('secType')
        _option_exchange = _option_section.get('exchange')
        expiration_months = _option_section.get("months", "").split(";") 

        # Fetch strikes for all expiration months with rate limiting
        _strike_tasks = [
            self._fetcher.fetch_with_limiting(
                self._fetcher.get_strikes, 
                _conid, month, _option_type, _option_exchange
            ) 
            for month in expiration_months
        ]
        
        _strike_dicts = await asyncio.gather(*_strike_tasks)

        # Choose processing method
        if self.use_loop:
            await self.get_option_chain_loop(_conid, _option_type, _option_exchange, _strike_dicts)
        else:
            await self.get_option_chain_gather(_conid, _option_type, _option_exchange, _strike_dicts)

    async def get_option_chain_loop(self, conid, option_type, option_exchange, list_of_dict) -> None:
        """Fetch option chain using sequential loop with Fetcher class."""
        stat_time = time.time()
        option_data: List[Dict[str,str]] = []
        
        for _dict in list_of_dict:
            for k, v in _dict.items():
                month = k
                strikes = v
                for strike in strikes:
                    # Use Fetcher for contract details
                    c_response = await self.get_contract_response(conid, month, strike, "C", option_type, option_exchange)

                    if c_response:
                        _call_conid = c_response.get('conid')
                        _call_maturity_date = c_response.get('maturity_date')
                        _call_strike = c_response.get('strike')
                        option_data.append({
                            "symbol": self._symbol,
                            "maturity_date": _call_maturity_date,
                            "strike": _call_strike,
                            "right": "C",
                            "conid": _call_conid,
                        })

                    p_response = await self.get_contract_response(conid, month, strike, "P", option_type, option_exchange)

                    if p_response:
                        _put_conid = p_response.get("conid")
                        _put_maturity_date = p_response.get('maturity_date')
                        _put_strike = p_response.get("strike")
                        option_data.append({
                            "symbol": self._symbol,
                            "maturity_date": _put_maturity_date,
                            "strike": _put_strike,
                            "right": "P",
                            "conid": _put_conid,
                        })

        end_time = time.time()
        _lapse = end_time - stat_time
        print(f"Retrieved {len(option_data)} contracts in {_lapse}")

        store_data(option_data)

    async def get_option_chain_gather(self, conid, option_type, option_exchange, strike_dicts) -> None:
        """Fetch option chain using batch processing with Fetcher class."""
        option_data: List[Dict[str,str]] = []
        
        # Collect all tasks first using Fetcher's rate limiting
        _call_tasks = []
        _put_tasks = []
        
        for _dict in strike_dicts:
            for k, v in _dict.items():
                month = k
                strikes = v
                for strike in strikes:
                    # Use Fetcher with rate limiting for contracts
                    _c_task = self._fetcher.fetch_with_limiting(
                        self._fetcher.get_contract, 
                        conid, month, strike, "C", option_type, option_exchange
                    )
                    _call_tasks.append(_c_task)
                    
                    _p_task = self._fetcher.fetch_with_limiting(
                        self._fetcher.get_contract,
                        conid, month, strike, "P", option_type, option_exchange
                    )
                    _put_tasks.append(_p_task)

        import time
        start_time = time.time()
        
        # Process in batches to avoid overwhelming the connection pool
        BATCH_SIZE = 50
        
        # Process call tasks in batches
        _call_result_list = []
        for i in range(0, len(_call_tasks), BATCH_SIZE):
            batch = _call_tasks[i:i + BATCH_SIZE]
            results = await asyncio.gather(*batch)
            _call_result_list.extend(results)
            print(f"Processed calls batch {i//BATCH_SIZE + 1}/{(len(_call_tasks) + BATCH_SIZE - 1)//BATCH_SIZE}")
        
        # Process put tasks in batches
        _put_result_list = []
        for i in range(0, len(_put_tasks), BATCH_SIZE):
            batch = _put_tasks[i:i + BATCH_SIZE]
            results = await asyncio.gather(*batch)
            _put_result_list.extend(results)
            print(f"Processed puts batch {i//BATCH_SIZE + 1}/{(len(_put_tasks) + BATCH_SIZE - 1)//BATCH_SIZE}")

        end_time = time.time()
        print(f"Fetched {_call_result_list.__len__() + _put_result_list.__len__()} contracts in {end_time - start_time} seconds.")

        option_data = self._process_batch_results(_call_result_list, _put_result_list)

        _task_length = len(_call_tasks) + len(_put_tasks)
        _retrieved_length = len(option_data)
        _diff = _task_length - _retrieved_length
        print(f"Retrieved {_retrieved_length} out of requested {_task_length}, with {_diff} not retrieved.")

        store_data(option_data)

    def _process_batch_results(self, _call_result_list, _put_result_list) -> List[Dict[str, str]]:
        """Process batch results from Fetcher calls into consistent format."""
        option_data: List[Dict[str,str]] = []

        for _call_item in _call_result_list:
            if not _call_item:
                continue
            
            # Handle dict responses (formatted contract data)
            if isinstance(_call_item, dict):
                _call_conid = _call_item.get("conid")
                _call_maturity_date = _call_item.get("maturity_date")
                _call_strike = _call_item.get("strike")
                if _call_conid:
                    option_data.append({
                        "symbol": self._symbol,
                        "maturity_date": _call_maturity_date,
                        "strike": _call_strike,
                        "right": "C",
                        "conid": _call_conid,
                    })
            elif isinstance(_call_item, list) and len(_call_item) > 0:
                _call_data = _call_item[0]
                _call_conid = _call_data.get("conid")
                _call_maturity_date = _call_data.get("maturityDate")
                _call_strike = _call_data.get("strike")
                if _call_conid:
                    option_data.append({
                        "symbol": self._symbol,
                        "maturity_date": _call_maturity_date,
                        "strike": _call_strike,
                        "right": "C",
                        "conid": _call_conid,
                    })

        for _put_item in _put_result_list:
            if not _put_item:
                continue
            
            # Handle dict responses (formatted contract data)
            if isinstance(_put_item, dict):
                _put_conid = _put_item.get("conid")
                _put_maturity_date = _put_item.get("maturity_date")
                _put_strike = _put_item.get("strike")
                if _put_conid:
                    option_data.append({
                        "symbol": self._symbol,
                        "maturity_date": _put_maturity_date,
                        "strike": _put_strike,
                        "right": "P",
                        "conid": _put_conid,
                    })
            elif isinstance(_put_item, list) and len(_put_item) > 0:
                _put_data = _put_item[0]
                _put_conid = _put_data.get("conid")
                _put_maturity_date = _put_data.get("maturityDate")
                _put_strike = _put_data.get("strike")
                if _put_conid:
                    option_data.append({
                        "symbol": self._symbol,
                        "maturity_date": _put_maturity_date,
                        "strike": _put_strike,
                        "right": "P",
                        "conid": _put_conid,
                    })
        
        return option_data

    async def get_contract_response(self, conid: str, month: str, strike: str, right: str, secType: str, exchange: str = "SMART") -> Dict[str, str] | None:
        """Fetch contract details using Fetcher class and parse response."""
        _response = await self._fetcher.get_contract(conid, month, strike, right, secType, exchange)

        if not _response:
            return None
        
        if hasattr(_response, 'status_code') and _response.status_code == 200:
            try:
                _data = _response.json()
                if len(_data) > 0:
                    _section = _data[0]
                    _conid = _section.get('conid')
                    _maturity_date = _section.get('maturityDate')
                    _item = {
                        "symbol": self._symbol,
                        "maturity_date": _maturity_date,
                        "strike": strike,
                        "right": right,
                        "conid": _conid
                    }
                    return _item
            except Exception as e:
                print(f"Error parsing contract data: {e}")
                return None
        return None

if __name__ == "__main__":
    _signer = IbkrClient(use_oauth=True, timeout=15)
    # Configure connection pool to prevent PoolTimeout
    _session = AsyncClient(
        limits=httpx.Limits(
            max_connections=100,      # Maximum concurrent connections
            max_keepalive_connections=20,  # Keep-alive connections
            keepalive_expiry=30.0     # Seconds before closing keep-alive connections
        ),
        timeout=GET_RESPONSE_TIME_OUT
    )
    _symbol = DEFAULT_SYMBOL
    chain_builder = AsyncOptionChainBuilder(_session, _signer, _symbol, DEFAULT_EXCHANGE, False)
    asyncio.run(chain_builder.get_option_chain_async())
