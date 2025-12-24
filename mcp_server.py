import asyncio
import threading
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from typing import Callable, TypeVar, Awaitable
from main import get_option_chain


load_dotenv()

server = FastMCP("option_chain_server")

# Type variables for the decorator
F = TypeVar('F', bound=Callable[..., Awaitable[str]])

def mcp_tool(func: F) -> F:
    """Custom decorator for MCP tools that automatically sets structured_output=False"""
    return server.tool(structured_output=False)(func)  # type: ignore

@mcp_tool
async def fetch_option_chain(symbol: str, exchange: str = "SMART") -> str:
    """Retrieve option chain data for a given symbol and exchange. It will takes a while."""
    thread = threading.Thread(target=_thread_worker, args=(symbol, exchange))
    thread.start()
    return f"Started to fetch option chain data for {symbol} on {exchange}, please come back later to check if the data is ready."

def _thread_worker(symbol: str, exchange: str = "SMART") -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(get_option_chain(symbol, exchange))
    finally:
        loop.close()
            
@mcp_tool
async def check_option_chain(symbol: str) -> str:
    """Check if option chain data ("option_chain_dataset.csv") is available for a given symbol and exchange."""
    import os, csv, json
    data = []
    with open("option_chain_dataset.csv", 'r', encoding='utf-8') as f:
        if not os.path.exists(f.name):
            return json.dumps({"error": "Option Chain File not found"}, indent=4)
        reader = csv.DictReader(f)
        for row in reader:
            if symbol not in row['symbol']:
                continue
            data.append(row) # type: ignore
    return str(data) # type: ignore

if __name__ == "__main__":
    server.run()
