# Synchronous option chain builder
import sys
from SyncFetcher import SyncFetcher
from SyncOptionChainBuilder import SyncOptionChainBuilder
from ibind import IbkrClient
from config import DEFAULT_SYMBOL, DEFAULT_EXCHANGE


if __name__ == "__main__":
    # Redirect stdout to log file
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/sync_test_{timestamp}.log"
    
    with open(log_file, 'w') as f:
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
            print(f"ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            sys.stdout = sys.__stdout__
    
    print(f"Test log saved to: {log_file}")
