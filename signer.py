from dotenv import load_dotenv
from ibind import IbkrClient # type: ignore

load_dotenv()

_signer = None

def get_signer():
    global _signer
    if _signer is None:
        _signer = IbkrClient()
    return _signer
