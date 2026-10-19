# Synchronous option chain builder
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from SyncFetcher import SyncFetcher
from SyncOptionChainBuilder import SyncOptionChainBuilder
from ibind import IbkrClient
from settings.config import DEFAULT_SYMBOL, DEFAULT_EXCHANGE


logger = logging.getLogger(__name__)


def get_option_chain_sync(symbol: str, exchange: str = "SMART") -> None:
    """
    Synchronous entry point for building the option chain.

    Used by the MCP server in a background thread (see ``mcp_server.py``).

    Args:
        symbol: Stock/ETF/Index symbol
        exchange: Exchange identifier
    """
    # Create IBKR client
    client = IbkrClient(use_oauth=True, timeout=15)

    # Create sync builder
    builder = SyncOptionChainBuilder(client, symbol, exchange)

    # Build option chain
    builder.get_option_chain()


# NOTE (M-1): the previous code was an ``async def get_option_chain`` with
# no ``await`` inside, which the MCP server called via ``loop.run_until_complete``
# inside a worker thread. That pattern wasted an event-loop create/destroy per
# job and misled readers into expecting an async implementation. We now expose
# the synchronous entry point as ``get_option_chain_sync`` and keep the old
# async name as a thin alias so existing imports keep working.
async def get_option_chain(symbol: str, exchange: str = "SMART") -> None:
    """Deprecated async wrapper around :func:`get_option_chain_sync`.

    Retained for backward compatibility — prefer the sync entry point.
    """
    get_option_chain_sync(symbol, exchange)


if __name__ == "__main__":
    # Redirect stdout to log file.
    # NOTE (H-6 / H-7): the project-wide pattern redirects stdout to a
    # timestamped log file so the CLI entry points produce an artifact on disk.
    # We echo the destination *before* swapping sys.stdout (H-7) so an open
    # failure surfaces in the terminal, and use the logging module (H-6) so
    # records still flow through the central handler chain even if the file
    # later becomes unwritable.
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/sync_test_{timestamp}.log"

    print(f"Starting sync test — output will be logged to {log_file}")

    try:
        f = open(log_file, 'w')
    except OSError as e:
        print(f"ERROR: could not open log file {log_file}: {e}")
        sys.exit(1)

    with f:
        sys.stdout = f

        try:
            print(f"Starting sync test for {DEFAULT_SYMBOL} at {timestamp}")

            # Create IBKR client
            client = IbkrClient(use_oauth=True, timeout=15)
            print("IBKR client created successfully")

            # Create sync builder
            builder = SyncOptionChainBuilder(client, DEFAULT_SYMBOL, DEFAULT_EXCHANGE)
            print(f"SyncOptionChainBuilder initialized for {DEFAULT_SYMBOL}/{DEFAULT_EXCHANGE}")

            # Build option chain
            builder.get_option_chain()

            print("\n" + "="*50)
            print("Test completed successfully!")
            print("="*50)

        except Exception as e:
            # Log full traceback through the logging module (H-6) while still
            # printing a short banner through stdout (which is the log file at
            # this point, by design).
            logger.exception("Sync test failed: %s: %s", type(e).__name__, e)
            print(f"ERROR: {type(e).__name__}: {e}")
        finally:
            sys.stdout = sys.__stdout__

    print(f"Test log saved to: {log_file}")
