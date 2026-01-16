import asyncio
import threading
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from typing import Callable, TypeVar, Awaitable
from sync.main import get_option_chain


load_dotenv()

server = FastMCP("option_chain_server")

# Type variables for the decorator
F = TypeVar('F', bound=Callable[..., Awaitable[str]])

def mcp_tool(func: F) -> F:
    """Custom decorator for MCP tools that automatically sets structured_output=False"""
    return server.tool(structured_output=False)(func)  # type: ignore

@mcp_tool
async def fetch_option_chain(symbol: str, exchange: str = "SMART") -> str:
    """
    Retrieve option chain data for a given symbol and exchange, using synchronous approach. For a option chain with X contracts, it takes approximately X * 10 seconds in total.

    Args:
        symbol (str): The symbol of the underlier, for which to retrieve the option chain data.
        exchange (str, optional): Refer to underlier_mapping.md. Defaults to "SMART".
    """
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
    """Check if option chain data is available in PostgreSQL for a given symbol."""
    import json
    from utils.database import query_option_chain
    
    try:
        data = query_option_chain(symbol)
        if not data:
            return json.dumps({"error": f"No option chain data found for symbol '{symbol}'"}, indent=4)
        return json.dumps(data, indent=4)
    except Exception as e:
        return json.dumps({"error": f"Database query failed: {str(e)}"}, indent=4)

if __name__ == "__main__":
    server.run()
