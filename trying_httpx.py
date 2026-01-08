# This does not work well yet.
import asyncio
from typing import List, Dict
from main import get_signer
from store_data import store_data

async def get_option_chain_async(symbol: str, exchange: str = "SMART") -> None:
    from httpx import AsyncClient
    from httpx_calls import get_contracts_async, get_underliers_async, get_strikes_async, async_limiting


    signer = get_signer()
    _healthy = signer.check_health()
    if not _healthy:
        print(f"Client is not healthy.")
        return

    option_data: List[Dict[str,str]] = []

    # limits = httpx.Limits(max_connections=500, max_keepalive_connections=100)
    # async with httpx.AsyncClient(limits=limits, timeout=30.0) as session:
    async with AsyncClient() as session:
        _underliers = await get_underliers_async(session, signer, symbol)
        _underlier = _underliers[0]  # type: ignore
        _conid = _underlier.get("conid")
        if not _conid:
            return
        expiration_months = _underlier.get("sections", [{}])[1].get("months", "").split(";")  # type: ignore

        # _strike_tasks = [_get_strikes(session, signer, _conid, month, exchange) for month in expiration_months] # type: ignore
        # _months_strikes = await asyncio.gather(*_strike_tasks)

        _strike_tasks = [async_limiting(session, signer, get_strikes_async, _conid, month, exchange) for month in expiration_months]  # type: ignore
        _strikes_info = await asyncio.gather(*_strike_tasks)

        _call_tasks = []
        _put_tasks = []
        # for month, strikes in _months_strikes.items():
        for month_strikes in _strikes_info:
            month = list(month_strikes.keys())[0]
            strikes = month_strikes[month]
            for strike in strikes:
                _call_tasks.append(async_limiting(session, signer, get_contracts_async, _conid, month, strike, "C")) # type: ignore
                _put_tasks.append(async_limiting(session, signer, get_contracts_async, _conid, month, strike, "P")) # type: ignore

        import time
        start_time = time.time()

        _calls = await asyncio.gather(*_call_tasks)
        _puts = await asyncio.gather(*_put_tasks)

        end_time = time.time()
        print(f"Fetched {_calls.__len__() + _puts.__len__()} contracts in {end_time - start_time} seconds.")

        for _call in _calls:
            if len(_call) == 0:
                continue
            _call_conid = _call[0].get("conid")  # type: ignore
            _call_maturity_date = _call[0].get("maturityDate")  # type: ignore
            option_data.append({
                "symbol": symbol,
                "maturity_date": _call_maturity_date,
                "strike": _call[0].get("strike"),  # type: ignore
                "right": "C",
                "conid": _call_conid,
            })
        for _put in _puts:
            _put_conid = _put[0].get("conid")  # type: ignore
            _put_maturity_date = _put[0].get("maturityDate")  # type: ignore
            option_data.append({
                "symbol": symbol,
                "maturity_date": _put_maturity_date,
                "strike": _put[0].get("strike"),  # type: ignore
                "right": "P",
                "conid": _put_conid,
            })

    store_data(option_data)


if __name__ == "__main__":
    asyncio.run(get_option_chain_async("SPX"))
