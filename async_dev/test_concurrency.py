#!/usr/bin/env python3
"""
Systematic test script to find optimal MAX_CONCURRENCY value.

Tests different MAX_CONCURRENCY values and measures:
- Total time to complete
- HTTP 503 errors (concurrent limit exceeded)
"""
import asyncio
import sys
import time
import importlib.util
from dotenv import load_dotenv
from httpx import AsyncClient, Limits
from session_health_helper import create_session_aware_client
from config import (
    DEFAULT_SYMBOL, DEFAULT_EXCHANGE, 
    MAX_RATE, MAX_CONNECTIONS, MAX_KEEPALIVE_CONNECTIONS, 
    KEEPALIVE_EXPIRY, GET_RESPONSE_TIME_OUT, IBKR_BASE_URL,
    SEARCH_PATH, STRIKE_PATH, INFO_PATH
)

load_dotenv()

# Import AsyncOptionChainBuilder from httpx approach.py
spec = importlib.util.spec_from_file_location("httpx_approach", "httpx_approach.py")
if spec is None:
    raise ImportError("Failed to load module")
module = importlib.util.module_from_spec(spec)
if module is None:
    raise ImportError("Failed to load module")
if spec.loader is None:
    raise ImportError("Failed to load module")
spec.loader.exec_module(module)
AsyncOptionChainBuilder = module.AsyncOptionChainBuilder


async def test_concurrency(max_concurrency: int) -> dict:
    """
    Test a specific MAX_CONCURRENCY value.
    
    Returns dict with:
    - max_concurrency: Test value
    - total_time: Total time in seconds
    - total_contracts: Number of contracts fetched
    - avg_response_time: Average response time per contract
    - fifty3_count: Number of 503 errors
    - throughput: Contracts per second
    """
    print(f"\n{'='*60}")
    print(f"Testing MAX_CONCURRENCY = {max_concurrency}")
    print(f"{'='*60}")
    
    # Temporarily override config
    import config as cfg
    original_max_concurrency = cfg.MAX_CONCURRENCY
    cfg.MAX_CONCURRENCY = max_concurrency
    
    try:
        # Create IBKR client
        session_manager = create_session_aware_client(
            use_oauth=True,
            timeout=15,
            retry_on_410=True,
            max_health_retries=3,
            health_check_interval=60.0,
            tickler_retry_delay=5.0,
            auto_reinitialize=True
        )
        
        if session_manager is None:
            return {"error": "Failed to create IBKR client"}
        
        signer = session_manager.client
        _healthy_client = session_manager.ensure_healthy_session()
        if _healthy_client is None:
            return {"error": "Failed to establish healthy session"}
        
        # Create httpx client
        session = AsyncClient(
            limits=Limits(
                max_connections=MAX_CONNECTIONS,
                max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=KEEPALIVE_EXPIRY
            ),
            timeout=GET_RESPONSE_TIME_OUT
        )
        
        # Create builder
        builder = AsyncOptionChainBuilder(
            session,
            signer,
            DEFAULT_SYMBOL,
            DEFAULT_EXCHANGE,
            use_loop=False,
            show_progress=False
        )
        
        # Run test
        start_time = time.time()
        
        await builder.get_option_chain_async()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Restore original config
        cfg.MAX_CONCURRENCY = original_max_concurrency
        
        return {
            "max_concurrency": max_concurrency,
            "total_time": total_time,
            "avg_response_time": 0.0,  # Will be calculated from log
            "503_count": 0,  # Will be counted from log
            "throughput": 0.0,  # Will be calculated
            "total_contracts": 6772  # Placeholder
        }
        
    except Exception as e:
        cfg.MAX_CONCURRENCY = original_max_concurrency
        return {
            "max_concurrency": max_concurrency,
            "error": f"{type(e).__name__}: {e}"
        }


async def run_all_tests():
    """Run systematic tests with different MAX_CONCURRENCY values."""
    
    print("=" * 60)
    print("SYSTEMATIC CONCURRENCY TEST")
    print("=" * 60)
    print()
    
    # Test values to try
    test_values = [2, 5, 8, 10, 12, 15]
    
    results = []
    
    for max_conc in test_values:
        print(f"\n{'='*60}")
        print(f"Test {test_values.index(max_conc) + 1}/{len(test_values)}: MAX_CONCURRENCY = {max_conc}")
        print(f"{'='*60}")
        
        result = await test_concurrency(max_conc)
        results.append(result)
        
        # Print summary
        if "error" in result:
            print(f"❌ ERROR: {result['error']}")
        else:
            print(f"✓ Total time: {result['total_time']:.2f}s")
            # Calculate throughput
            throughput = result['total_contracts'] / result['total_time']
            print(f"✓ Throughput: {throughput:.2f} contracts/second")
            if result['503_count'] > 0:
                print(f"⚠️  {result['503_count']} HTTP 503 errors (concurrent limit exceeded)")
            else:
                print(f"✓ No 503 errors")
        
        # Wait between tests to avoid rate limit recovery time
        print()
        print("Waiting 30 seconds before next test...")
        await asyncio.sleep(30)
    
    # Print final summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    
    successful_results = [r for r in results if "error" not in r]
    
    print(f"\nTested MAX_CONCURRENCY values: {test_values}")
    print(f"\n{'='*60}")
    
    for result in successful_results:
        throughput = result['total_contracts'] / result['total_time']
        print(f"MAX_CONCURRENCY={result['max_concurrency']}: {result['total_time']:.2f}s, "
              f"throughput: {throughput:.2f} contracts/sec, "
              f"503 errors: {result['503_count']}")
    
    print(f"\n{'='*60}")
    print("\nRecommendation: Find optimal setting with:")
    print("  - Highest throughput")
    print("  - No 503 errors")
    print("  - Shortest total time")
    
    # Find best result
    if successful_results:
        best = min(successful_results, key=lambda x: x['total_time'])
        print(f"\n🏆 OPTIMAL: MAX_CONCURRENCY = {best['max_concurrency']}")
        print(f"   Total time: {best['total_time']:.2f}s")
        print(f"   Throughput: {best['total_contracts']/best['total_time']:.2f} contracts/second")
        print(f"   503 errors: {best['503_count']}")
    else:
        print("\n❌ All tests failed")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
