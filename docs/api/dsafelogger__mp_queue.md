# Multiprocess Queue Tracking

**Module**: `dsafelogger._mp_queue`

Multiprocess Queue with cross-platform qsize() support (v23h).

`multiprocessing.Queue.qsize()` raises NotImplementedError on platforms
whose underlying semaphore lacks `sem_getvalue(3)` (notably macOS, but
potentially other minor OSes).  TrackedQueue probes this support once
at construction time and falls back to a `multiprocessing.Value` counter
when the native call is unavailable.

Design:
    - Linux / Windows: native qsize() is used. Zero per-put/get overhead.
    - macOS / unsupported: Value counter is updated on every put/get.
      qsize() returns the (approximate) tracked count.

The detection uses an EAFP-style probe (calling qsize() and catching
NotImplementedError) — explicit OS detection is intentionally avoided
so future or minor platforms behave correctly without code changes.

## Classes

### `TrackedQueue(maxsize: 'int' = 0, *, ctx: 'Any') -> 'None'`

multiprocessing.Queue subclass that guarantees a working qsize().

Construction probes the native implementation once.  After that:
- native supported → native qsize() is forwarded (no extra cost)
- native unsupported → an internal Value counter is used

The detected mode and counter are pickled to child processes so all
workers share the same view of the queue depth.

Public methods:

- `empty(self) -> 'bool'`
- `get(self, block: 'bool' = True, timeout: 'float | None' = None) -> 'Any'`
- `get_nowait(self) -> 'Any'`
- `put(self, obj: 'Any', block: 'bool' = True, timeout: 'float | None' = None) -> 'None'`
- `put_nowait(self, obj: 'Any') -> 'None'`
- `qsize(self) -> 'int'`
