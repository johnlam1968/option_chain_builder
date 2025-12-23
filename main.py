from client import get_underlier, get_strikes, get_contracts

def get_option_chain(symbol: str, exchange: str = "SMART"):
    """
    Args:
        symbol (str): symbol of the underlier, e.g. "CL" for Crude Oil Futures options, "ES" for E-mini S&P 500 Futures options, "SPX" for S&P 500 Index options, "SPY" for SPDR S&P 500 ETF options, etc.

        exchange (str): exchange of the option, e.g. for Futures Options, it could be "NYMEX" for underlying "CL", for stock options, it should be the default "SMART"

    """

    _underliers = get_underlier(symbol).data # type: ignore
    _underlier = _underliers[0] # type: ignore
    _conid = _underlier.get("conid") # type: ignore
    expiration_months = _underlier.get("sections", [{}])[1].get("months", "").split(";") # type: ignore

    _dict: dict[str, dict[str, tuple[str, str]]] = {} # {maturity_date: {strike: (call_conid, put_conid)}

    for _month in expiration_months: # type: ignore
        _strikes = get_strikes(conid=_conid, month=_month, exchange=exchange).data # type: ignore
        _call_strikes = _strikes.get("call", []) # type: ignore
        # put_strikes = strikes.get("put", []) # type: ignore
        # call_strikes and put_strikes are identical lists, so we can use either

        for _strike in _call_strikes: # type: ignore
            _calls = get_contracts(conid=_conid, month=_month, strike=_strike, right="C").data # type: ignore
            _puts = get_contracts(conid=_conid, month=_month, strike=_strike, right="P").data # type: ignore
            if _calls:
                for _call in _calls: # type: ignore
                    _call_maturity_date = _call.get("maturityDate") # type: ignore
                    _strike_dict = _dict.get(_call_maturity_date) # type: ignore

                    if _strike_dict is None:
                        _call_conid = _call.get("conid") # type: ignore
                        _strike_dict = {_strike: (_call_conid, "N/A")} # type: ignore
                        _dict[_call_maturity_date] = _strike_dict # type: ignore
            if _puts:
                for _put in _puts: # type: ignore
                    _put_conid = _put.get("conid") # type: ignore
                    _put_maturity_date = _put.get("maturityDate") # type: ignore
                    _strike_dict = _dict.get(_put_maturity_date) # type: ignore
                    if _strike_dict is None:
                        _strike_dict = {_strike: ("N/A", _put_conid)} # type: ignore
                        _dict[_put_maturity_date] = _strike_dict # type: ignore
                    else:
                        if _strike_dict[_strike][1] == "N/A":
                            _strike_dict = {strike: (_strike_dict[0], _put_conid)} # type: ignore
                            _dict[_put_maturity_date] = _strike_dict # type: ignore

    # persistent store
    from util import write_csv
    write_csv(symbol, _dict)

if __name__ == "__main__":
    get_option_chain("KSA")
