# Async & High-Throughput Logging

In a web server handling 10,000 requests/second, each `logger.info()` call that
blocks on disk I/O steals microseconds from your response time. Over thousands of
requests, that's milliseconds of accumulated latency. D-SafeLogger's async mode
decouples the caller from the writer: your application thread enqueues a log record
quickly while a dedicated background thread handles the actual file I/O.

## When to Use Async

| Scenario | Recommendation |
|---|---|
| CLI scripts | Sync (default) — simpler, no drain delay |
| Simple web services | Sync — unless you measure I/O as a bottleneck |
| High-throughput API (>1k req/s) | **Async** — prevents I/O from stalling request threads |
| GUI applications (Tkinter, Qt) | **Async** — never block the UI thread |
| Batch data pipelines | **Async** — maximize throughput |

## Prerequisites

- **Python 3.11+**
- Install D-SafeLogger:

```bash
pip install d-safelogger
```

## Setup

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs',
    pg_name='HighThroughput',
    is_async=True,
)

logger = GetLogger(__name__)
logger.info('This call returns after enqueueing the record')
```

## How It Works Internally

1. `logger.info()` snapshots the LogRecord + context + traceback
2. Record is enqueued to an unbounded `queue.Queue`
3. Background `QueueListener` thread dequeues and writes to file
4. Caller returns immediately without waiting for disk I/O

The bottleneck shifts from per-call disk latency to aggregate disk bandwidth,
enabling substantially higher throughput on workloads where disk I/O is the bottleneck.

## Context Preservation

`contextualize()` context is snapshot at enqueue time. Even if the context manager
exits before the background thread writes the record, the context is correctly
attached:

```python
logger = GetLogger('myservice')

def handle_request(request_id: str):
    with logger.contextualize(request_id=request_id):
        logger.info('Request received')        # context captured here
        result = process(request_id)
        logger.info('Request completed')       # context captured here
    # Context manager exits, but both records still carry request_id
    # even if the background writer hasn't flushed yet
```

Output:
```
2026-04-03 09:15:22.738 [INF][server.py:6:handle_request] Request received [request_id:abc-123]
2026-04-03 09:15:22.812 [INF][server.py:8:handle_request] Request completed [request_id:abc-123]
```

## Shutdown Behavior

D-SafeLogger registers an `atexit` handler that performs an orderly shutdown:

1. **Stop accepting** — new records after the handler fires are discarded
2. **Drain queue** — the consumer thread flushes all pending records (5-second timeout)
3. **Join workers** — hash, purge, and archive threads are joined
4. **Flush and close** — all file handlers are flushed and closed

No manual cleanup is needed. If the queue cannot be drained within 5 seconds,
remaining records are lost and a warning is emitted to stderr.

## Combining with Other Features

Async mode works transparently with every other D-SafeLogger feature:

```python
ConfigureLogger(
    log_path='./logs',
    pg_name='FullFeature',
    is_async=True,
    routing_mode='daily',
    structured=True,
    enable_hash=True,
)
```

This gives you non-blocking writes **plus** daily file rotation, JSON output,
and SHA-256 integrity hashing — all in one call.

## Complete Example

Save the following as `async_demo.py`:

```python
"""async_demo.py — Demonstrate non-blocking async logging with threads."""

import threading
import time
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs',
    pg_name='AsyncPerfDemo',
    is_async=True,
)

logger = GetLogger(__name__)

def worker(worker_id: int, iterations: int = 20):
    """Simulate a busy worker producing logs without blocking."""
    with logger.contextualize(worker=worker_id):
        for i in range(iterations):
            logger.info(f'Processing item {i}')
            time.sleep(0.005)  # simulate work
        logger.info('Worker finished')

# Launch several threads — all logging is non-blocking
num_workers = 8
threads = [
    threading.Thread(target=worker, args=(n,))
    for n in range(num_workers)
]

start = time.perf_counter()
for t in threads:
    t.start()
for t in threads:
    t.join()
elapsed = time.perf_counter() - start

logger.info(f'All {num_workers} workers done in {elapsed:.3f}s')
print(f'Finished in {elapsed:.3f}s — {num_workers * 20} log records from {num_workers} threads')
print('Check ./logs/AsyncPerfDemo.log')
```

### Expected Output

Terminal:
```
Finished in 0.117s — 160 log records from 8 threads
Check ./logs/AsyncPerfDemo.log
```

`logs/AsyncPerfDemo.log` (order may vary between workers):
```
2026-04-03 12:34:56.789 [INF][async_demo.py:19:worker] Processing item 0 [worker:0]
2026-04-03 12:34:56.789 [INF][async_demo.py:19:worker] Processing item 0 [worker:3]
2026-04-03 12:34:56.790 [INF][async_demo.py:19:worker] Processing item 0 [worker:1]
2026-04-03 12:34:56.790 [INF][async_demo.py:19:worker] Processing item 0 [worker:5]
...
2026-04-03 12:34:56.905 [INF][async_demo.py:21:worker] Worker finished [worker:7]
2026-04-03 12:34:56.906 [INF][async_demo.py:21:worker] Worker finished [worker:2]
2026-04-03 12:34:56.906 [INF][async_demo.py:37:<module>] All 8 workers done in 0.117s
```

Records from different workers are interleaved — this is expected and correct.
Each record carries its own `[worker:N]` context, so you can always trace which
thread produced which line.

## How to Run

```bash
pip install d-safelogger
python async_demo.py
cat logs/AsyncPerfDemo.log
```
