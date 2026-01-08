import asyncio
from typing import List, Dict
import httpx
from ibind.client.ibkr_client import IbkrClient # type: ignore
from sqlmodel import Field, SQLModel, create_engine, Session
from client import get_underliers, get_strikes, get_contracts, _get_contracts, _get_underliers, _get_strikes, _async_limiting, get_signer, gate, limiter


class OptionChain(SQLModel, table=True):
    conid: str = Field(primary_key=True)
    symbol: str
    maturity_date: str # Or datetime.date
    strike: str
    right: str

# Replace 'localhost' with 'db' if Python is inside the Docker network
DATABASE_URL = "postgresql+psycopg://postgres:secret@localhost:5432/options_db"
engine = create_engine(DATABASE_URL)
SQLModel.metadata.create_all(engine)

async def get_option_chain(symbol: str, exchange: str = "SMART"):
    """
    Args:
        symbol (str): symbol of the underlier, e.g. "CL" for Crude Oil Futures options, "ES" for E-mini S&P 500 Futures options, "SPX" for S&P 500 Index options, "SPY" for SPDR S&P 500 ETF options, etc.

        exchange (str): exchange of the option, e.g. for Futures Options, it could be "NYMEX" for underlying "CL", for stock options, it should be the default "SMART"

    """
    _underliers = get_underliers(symbol).data # type: ignore
    _underlier = _underliers[0] # type: ignore
    _conid = _underlier.get("conid") # type: ignore
    expiration_months = _underlier.get("sections", [{}])[1].get("months", "").split(";") # type: ignore

    # Create a list to store all option data
    option_data: List[Dict[str,str]] = []

    import time
    start_time = time.time()

    for _month in expiration_months: # type: ignore
        _strikes = get_strikes(conid=_conid, month=_month, exchange=exchange).data # type: ignore
        _call_strikes = _strikes.get("call", []) # type: ignore

        for _strike in _call_strikes: # type: ignore
            _calls = get_contracts(conid=_conid, month=_month, strike=_strike, right="C").data # type: ignore
            _puts = get_contracts(conid=_conid, month=_month, strike=_strike, right="P").data # type: ignore

            # Process call options
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

            # Process put options
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

    # Batch Ingestion
    with Session(engine) as session:
        for data in option_data:
            session.merge(OptionChain(**data))
        session.commit()

async def _get_option_chain(symbol: str, exchange: str = "SMART") -> None:
    signer = get_signer()
    _healthy = signer.check_health()
    if not _healthy:
        print(f"Client is not healthy.")
        return

    option_data: List[Dict[str,str]] = []

    # limits = httpx.Limits(max_connections=500, max_keepalive_connections=100)
    # async with httpx.AsyncClient(limits=limits, timeout=30.0) as session:
    async with httpx.AsyncClient() as session:
        _underliers = await _get_underliers(session, signer, symbol)
        _underlier = _underliers[0]  # type: ignore
        _conid = _underlier.get("conid")
        if not _conid:
            return
        expiration_months = _underlier.get("sections", [{}])[1].get("months", "").split(";")  # type: ignore

        # _strike_tasks = [_get_strikes(session, signer, _conid, month, exchange) for month in expiration_months] # type: ignore
        # _months_strikes = await asyncio.gather(*_strike_tasks)

        _strike_tasks = [_async_limiting(session, signer, _get_strikes, _conid, month, exchange) for month in expiration_months]  # type: ignore
        _strikes_info = await asyncio.gather(*_strike_tasks)

        _call_tasks = []
        _put_tasks = []
        # for month, strikes in _months_strikes.items():
        for month_strikes in _strikes_info:
            month = list(month_strikes.keys())[0]
            strikes = month_strikes[month]
            for strike in strikes:
                _call_tasks.append(_async_limiting(session, signer, _get_contracts, _conid, month, strike, "C")) # type: ignore
                _put_tasks.append(_async_limiting(session, signer, _get_contracts, _conid, month, strike, "P")) # type: ignore

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

    with Session(engine) as orm_session:
        for data in option_data:
            orm_session.merge(OptionChain(**data))
        orm_session.commit()

if __name__ == "__main__":
    # asyncio.run(_get_option_chain("SPX"))
    asyncio.run(get_option_chain("SPX"))
