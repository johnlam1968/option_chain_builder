# Direct salls to IBKR API using httpx with async rate limiting and error handling
# ibind client for OAuth signing
import asyncio
import random
from httpx import AsyncClient, Response
from aiolimiter import AsyncLimiter
import json
import os

from ibind.client.ibkr_client import IbkrClient # type: ignore
from typing import Any, List, Dict, Callable
from config import SEARCH_PATH, STRIKE_PATH, INFO_PATH, STATE_FILE, MAX_RATE


def save_api_state(marginal_rate: float):
    state = {
        "initial_rate": max(10, marginal_rate * 0.8), # Start at 80% of where you crashed
        "marginal_rate": marginal_rate
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_initial_rate(default: float = 20):
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            return state.get("initial_rate", default)
    return default

_initial_rate = load_initial_rate(default=10)
# limiter = AsyncLimiter(_initial_rate, 1)
limiter = AsyncLimiter(10, 1)
gate = asyncio.Event()
gate.set()

# pool_semaphore = asyncio.Semaphore(100) # Only allow 100 tasks to "work" at once

def _build_underlier_url(signer: IbkrClient, underlier: str) -> str:
    endpoint = SEARCH_PATH + f"?symbol={underlier}"
    full_url = f"{signer.base_url}{endpoint}"
    return full_url

def _build_strike_url(signer: IbkrClient, conid: str, month: str, exchange: str = "SMART") -> str:
    clean_month = month.replace(" ", "")
    if exchange == "SMART":
        endpoint = f"iserver/secdef/strikes?conid={conid}&sectype=OPT&month={clean_month}"
        endpoint = STRIKE_PATH + f"?conid={conid}&sectype=OPT&month={clean_month}"
    else:
        endpoint = STRIKE_PATH + f"?conid={conid}&sectype=OPT&month={clean_month}&exchange={exchange}"
    full_url = f"{signer.base_url}{endpoint}"
    return full_url

def _build_contract_url(signer: IbkrClient, conid: str, month: str, strike: str, right: str) -> str:
    if " " not in month:
        month = f"{month[:3]} {month[3:]}"
    endpoint = INFO_PATH + f"?conid={conid}&secType=OPT&month={month}&strike={strike}&right={right}"
    full_url = f"{signer.base_url}{endpoint}"
    return full_url

async def get_underliers_async(session: AsyncClient, signer: IbkrClient, symbol: str) -> List[Dict[str, str]]:
    url = _build_underlier_url(signer, symbol)
    oauth_headers = signer._get_headers(request_method="GET", request_url=url) # type: ignore
    response = await session.get(
        url,
        headers=oauth_headers,  # type: ignore
        timeout=15.0
    )
    if response.status_code == 503:
        print("🚨 Service Unavailable (503). Retrying after brief pause...")
        await asyncio.sleep(5)  # Wait before retrying
        response = await session.get(
            url,
            headers=oauth_headers,  # type: ignore
            timeout=15.0
        )

    # if response.status_code == 200:
    return response.json()

async def get_strikes_async(session: AsyncClient, signer: IbkrClient, conid: str, month: str, exchange: str = "SMART") -> Response:
    url = _build_strike_url(signer, conid, month, exchange)
    oauth_headers = signer._get_headers(request_method="GET", request_url=url) # type: ignore
    response = await session.get(
        url,
        headers=oauth_headers,  # type: ignore
        timeout=15.0
    )
    return response

async def async_limiting(session: AsyncClient, signer: IbkrClient, function: Callable[..., Any],*args: Any) -> List[Dict[str, str]] | Dict[str, List[str]]:
    auth_status = await session.get(f"{signer.base_url}iserver/auth/status")
    if auth_status.status_code != 200 or not auth_status.json().get('authenticated'):
        print("❌ Session lost. Re-authentication required.")
        # Trigger your login logic here

    # async with pool_semaphore:

    while True:

        await gate.wait()

        async with limiter:
            if not gate.is_set():
                continue
            try:
                response = await function(session, signer, *args)

                if response is None:
                    continue

                if response.status_code == 200:
                    # Heuristic: Slowly increase rate if we are successful
                    # (e.g., add 0.1 to max_rate every 100 successful calls)
                    if random.random() < 0.2:
                        limiter.max_rate  = min(limiter.max_rate + 1, MAX_RATE)
                    if function == get_contracts_async:
                        return response.json()
                    elif function == get_strikes_async:
                        _dict = response.json()
                        _call_strikes = _dict.get("call", [])
                        month = args[1]
                        _result_dict = {month: _call_strikes}
                        return _result_dict

                elif response.status_code == 429:
                    if gate.is_set():
                        gate.clear()

                    _marginal_rate = limiter.max_rate
                    save_api_state(_marginal_rate)
                    print(f"🚨 429 at {_marginal_rate} req/s. Throttling down... Pause for a 15 minutes penalty period.")

                    limiter.max_rate = max(1, limiter.max_rate - 1)
                    print(f"Rate limit hit. Reducing rate to {limiter.max_rate} req/s.")
                    
                    await asyncio.sleep(900) # 15 minute ban
                    print("✅ Penalty over. Opening gate.")
                    gate.set()
                    continue  # Retry after sleep

            except (simple_approach.PoolTimeout, simple_approach.ReadTimeout, simple_approach.ConnectTimeout):
                limiter.max_rate = max(5, limiter.max_rate - 5)
                print(f"⏱️ Timeout. Reducing rate to {limiter.max_rate} req/s.")
                await asyncio.sleep(2) # Give the network a breather
                continue

async def get_contracts_async(session: AsyncClient, signer: IbkrClient, conid: str, month: str, strike: str, right: str) -> Response | None:
    _healthy = signer.check_health()
    if not _healthy:
        print(f"Signer is not healthy.")
        return None

    try:
        url = _build_contract_url(signer, conid, month, strike, right)
        oauth_headers = signer._get_headers(request_method="GET", request_url=url) # type: ignore
        response = await session.get(
                        url,
                        headers=oauth_headers,  # type: ignore
                        timeout=15.0
                    )
        
        return response

    except simple_approach.PoolTimeout as e:
        print("📁 Connection Pool Full: Waiting for a slot...")
        await asyncio.sleep(1) # Back off to let the pool clear
        return None # Or 'continue' if inside a 'while True' loop
    except simple_approach.TimeoutException as e:
        print(f"⏱️ General Timeout (Read/Connect): {e}")
        return None