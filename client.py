from dotenv import load_dotenv
from ibind.client.ibkr_client import IbkrClient # type: ignore
from config import SEARCH_PATH, STRIKE_PATH, INFO_PATH

load_dotenv()

_ibind_client = None

def get_client():
    global _ibind_client
    if _ibind_client is None:
        _ibind_client = IbkrClient()
    return _ibind_client

def get_underlier(symbol: str):
    """
    Args:
        symbol (str): symbol of the underlier, e.g. "CL" for Crude Oil Futures options, "ES" for E-mini S&P 500 Futures options, "SPX" for S&P 500 Index options, "SPY" for SPDR S&P 500 ETF options, etc.
    """
    client = get_client()
    return client.get(path=SEARCH_PATH, params={"symbol": symbol}) # type: ignore

def get_strikes(conid: str, month: str, exchange: str = "SMART"):
    """
    Args:
        conid (str): contract id of underlier, e.g. "265598"
        month (str): month of the option, e.g. "MAR26"
        exchange (str): exchange of the option, e.g. for Futures Options, it could be "NYMEX" for underlying "CL", for stock options, it should be the default "SMART"
        """
    client = get_client()
    return client.get(path=STRIKE_PATH, params={"conid": conid, "secType": "OPT", "month": month, "exchange": exchange}) # type: ignore

def get_contracts(conid: str, month: str, strike: str, right: str):
    """
    Args:
        conid (str): contract id of underlier, e.g. "265598"
        month (str): month of the option, e.g. "MAR26"
        strike (str): strike price of the option, e.g. "100"
        right (str): type of the option, e.g. "C" for call, "P" for put
    """
    client = get_client()
    return client.get(path=INFO_PATH, params={"conid": conid, "secType": "OPT", "month": month, "strike": strike, "right": right}) # type: ignore
