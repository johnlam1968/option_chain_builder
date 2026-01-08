# Blocking calls to ibind
from ibind import IbkrClient # type: ignore
from config import SEARCH_PATH, STRIKE_PATH, INFO_PATH



def get_underliers(client: IbkrClient, symbol: str):
    """
    Args:
        symbol (str): symbol of the underlier, e.g. "CL" for Crude Oil Futures options, "ES" for E-mini S&P 500 Futures options, "SPX" for S&P 500 Index options, "SPY" for SPDR S&P 500 ETF options, etc.
    """
    return client.get(path=SEARCH_PATH, params={"symbol": symbol}) # type: ignore

def get_strikes(client: IbkrClient, conid: str, month: str, exchange: str = "SMART"):
    """
    Args:
        conid (str): contract id of underlier, e.g. "265598"
        month (str): month of the option, e.g. "MAR26"
        exchange (str): exchange of the option, e.g. for Futures Options, it could be "NYMEX" for underlying "CL", for stock options, it should be the default "SMART"
        """
    return client.get(path=STRIKE_PATH, params={"conid": conid, "secType": "OPT", "month": month, "exchange": exchange}) # type: ignore
    
def get_contracts(client: IbkrClient, conid: str, month: str, strike: str, right: str):
    """
    Args:
        conid (str): contract id of underlier, e.g. "265598"
        month (str): month of the option, e.g. "MAR26"
        strike (str): strike price of the option, e.g. "100"
        right (str): type of the option, e.g. "C" for call, "P" for put
    """
    return client.get(path=INFO_PATH, params={"conid": conid, "secType": "OPT", "month": month, "strike": strike, "right": right}) # type: ignore
