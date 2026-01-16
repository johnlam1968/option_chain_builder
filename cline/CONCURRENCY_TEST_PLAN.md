# Systematic Concurrency Test Plan

## Objective
Find the optimal `MAX_CONCURRENCY` setting that maximizes throughput while avoiding HTTP 503 errors (IBKR's concurrent request limit).

## Background Analysis

### Previous Performance Data
- **Sync approach**: 733.58s for 6772 contracts (0.108s per request)
- **Async (MAX_CONCURRENCY=5)**: 5441.86s for 6772 contracts (0.80s per request)
- **Async is 7.4x slower than sync**

### Why Is Async So Much Slower?
Unknown - needs investigation. Possible causes:
1. IBKR throttles async requests differently (per-connection vs per-IP)
2. HTTP/1.1 connection overhead in async
3. aiometer's batch processing overhead
4. Different endpoint behavior for concurrent INFO_PATH requests

### Key Calculations
- **MAX_RATE**: 10 requests/second (IBKR's documented limit)
- **Actual async response time**: 0.80 seconds per request (from MAX_CONCURRENCY=5 test)
- **Natural concurrency needed**: 10 req/s × 0.80s = **8 concurrent requests**
- **MAX_CONCURRENCY=5 bottleneck**: Processes only 5 out of 8 possible concurrent requests

### IBKR's Limits Discovered
- Rate limit: 10 requests per second (documented)
- Concurrent request limit: < 20 (triggers HTTP 503 errors)
- MAX_CONCURRENCY=20 caused massive 503 errors in previous tests

## Test Matrix

| Test | MAX_CONCURRENCY | Connection Pool Settings | Expected Outcome |
|------|----------------|-------------------------|------------------|
| 1 | 2 | MAX_CONNECTIONS=4, MAX_KEEPALIVE=2 | Very conservative, slowest |
| 2 | 8 | MAX_CONNECTIONS=16, MAX_KEEPALIVE=8 | Matches natural concurrency (theoretically optimal) |
| 3 | 10 | MAX_CONNECTIONS=20, MAX_KEEPALIVE=10 | Above natural, higher throughput risk |
| 4 | 12 | MAX_CONNECTIONS=24, MAX_KEEPALIVE=12 | Higher throughput, higher 503 risk |
| 5 | 15 | MAX_CONNECTIONS=30, MAX_KEEPALIVE=15 | Aggressive, near 503 threshold |

## Test Execution

### Test 1: MAX_CONCURRENCY=2 ✅ COMPLETED
- **Total time**: 6799.50 seconds (~113 minutes)
- **Throughput**: 0.996 contracts/second
- **503 errors**: None
- **Status**: Very safe but very slow

### Test 2: MAX_CONCURRENCY=8 ⏳ IN PROGRESS
- **Started**: 2026-01-15 22:56:08
- **PID**: 2658767
- **Expected time**: ~30-40 minutes (if 2-3x faster than MAX_CONCURRENCY=2)
- **Status**: Running in background

### Test 3: MAX_CONCURRENCY=10
- **Not started yet**
- **Expected time**: ~25-35 minutes
- **Risk**: Moderate 503 error possibility

### Test 4: MAX_CONCURRENCY=12
- **Not started yet**
- **Expected time**: ~20-30 minutes
- **Risk**: Higher 503 error possibility

### Test 5: MAX_CONCURRENCY=15
- **Not started yet**
- **Expected time**: ~15-25 minutes
- **Risk**: High 503 error possibility

## Configuration Settings

Each test requires updating `config.py`:

```python
# Example for MAX_CONCURRENCY=10
MAX_CONCURRENCY = 10
MAX_RATE = 10
MAX_CONNECTIONS = 20  # 2x MAX_CONCURRENCY
MAX_KEEPALIVE_CONNECTIONS = 10  # Equal to MAX_CONCURRENCY
```

## Success Criteria

Optimal `MAX_CONCURRENCY` value should:
1. **Highest throughput** (contracts per second)
2. **No 503 errors** (concurrent limit not exceeded)
3. **Shortest total time**

## Expected Results

Based on natural concurrency calculation:
- **MAX_CONCURRENCY=2**: Bottlenecked (50% of capacity)
- **MAX_CONCURRENCY=5**: Bottlenecked (62.5% of capacity)
- **MAX_CONCURRENCY=8**: **Should match natural capacity** (100%)
- **MAX_CONCURRENCY=10**: May exceed capacity, risk 503 errors
- **MAX_CONCURRENCY=12**: Likely exceeds capacity, high 503 risk
- **MAX_CONCURRENCY=15**: Definitely exceeds capacity, very high 503 risk

## Next Steps

1. ✅ Wait for MAX_CONCURRENCY=8 test to complete
2. Analyze results (total time, throughput, 503 errors)
3. If no 503 errors: Test MAX_CONCURRENCY=10
4. If 503 errors: Test MAX_CONCURRENCY=6 or 7
5. Continue testing until optimal value found
6. Compare all results and recommend optimal setting

## Notes

- Each test takes 15-90 minutes depending on concurrency level
- Tests run in background with output to timestamped log files
- Log files are in `logs/async_test_YYYYMMDD_HHMMSS.log`
- Monitor progress with: `tail -f logs/async_test_*.log`
