import asyncio
from signer import get_signer
from typing import List, Dict
from store_data import store_data

async def get_option_chain(symbol: str, exchange: str = "SMART") -> None:
    """
    Args:
        symbol (str): symbol of the underlier, e.g. "CL" for Crude Oil Futures options, "ES" for E-mini S&P 500 Futures options, "SPX" for S&P 500 Index options, "SPY" for SPDR S&P 500 ETF options, etc.

        exchange (str): exchange of the option, e.g. for Futures Options, it could be "NYMEX" for underlying "CL", for stock options, it should be the default "SMART"

    """
    from ibind_calls import get_underliers, get_strikes, get_contracts

    _client = get_signer()
    _healthy = _client.check_health()
    if not _healthy:
        print(f"Client is not healthy. Exiting...")
        return

    _underliers = get_underliers(client=_client, symbol=symbol).data # type: ignore
    _underlier = _underliers[0] # type: ignore
    _conid = _underlier.get("conid") # type: ignore
    expiration_months = _underlier.get("sections", [{}])[1].get("months", "").split(";") # type: ignore

    option_data: List[Dict[str,str]] = []

    import time
    start_time = time.time()

    for _month in expiration_months: # type: ignore
        _strikes = get_strikes(client=_client, conid=_conid, month=_month, exchange=exchange).data # type: ignore
        _call_strikes = _strikes.get("call", []) # type: ignore

        for _strike in _call_strikes: # type: ignore
            _calls = get_contracts(client=_client, conid=_conid, month=_month, strike=_strike, right="C").data # type: ignore
            _puts = get_contracts(client=_client, conid=_conid, month=_month, strike=_strike, right="P").data # type: ignore

            if _calls:
                for _call in _calls: # type: ignore
                    _call_conid = _call.get("conid") # type: ignore
                    _call_maturity_date = _call.get("maturityDate") # type: ignore
                    option_data.append({
                        "symbol": symbol,
                        "maturity_date": _call_maturity_date,
                        "strike": _strike,
                        "right": "C",
                        "conid": _call_conid,
                    })

            if _puts:
                for _put in _puts: # type: ignore
                    _put_conid = _put.get("conid") # type: ignore
                    _put_maturity_date = _put.get("maturityDate") # type: ignore
                    option_data.append({
                        "symbol": symbol,
                        "maturity_date": _put_maturity_date,
                        "strike": _strike,
                        "right": "P",
                        "conid": _put_conid,
                    })

    end_time = time.time()
    print(f"Fetched {len(option_data)} contracts in {end_time - start_time} seconds.")

    store_data(option_data)

if __name__ == "__main__":
    asyncio.run(get_option_chain("SPY"))
