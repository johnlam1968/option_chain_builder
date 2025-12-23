from client import get_underlier, get_strikes, get_contracts
import pandas as pd

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

    # Create a list to store all option data
    option_data = []

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

    # Convert to DataFrame
    df = pd.DataFrame(option_data)

    # Pivot the data to get call and put conids for each maturity date
    pivot_df = df.pivot_table(
        index=["symbol", "maturity_date", "strike"],
        columns="right",
        values="conid",
        aggfunc="first"
    ).reset_index()

    # Flatten the multi-index columns
    pivot_df.columns = ["symbol", "maturity_date", "strike", "call_conid", "put_conid"]

    # Replace NaN with "N/A"
    pivot_df.fillna("N/A", inplace=True)

    # persistent store
    from util import write_csv
    write_csv(symbol, pivot_df)

if __name__ == "__main__":
    get_option_chain("KSA")
