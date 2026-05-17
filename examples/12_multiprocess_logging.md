# Multiprocess Logging

`dsafelogger.mp` is the public multiprocess API for D-SafeLogger. This guide is the practical reference for using it: setup code, lifecycle, environment-variable knobs, classified failure modes, and reading the delivery-state output.

The README only sketches the multiprocess concept; this file is where the working code, edge cases, and operational reading live.

---

## 1. What this guide covers

This guide answers:

- When to use `dsafelogger.mp` and when not to.
- How to wire it up with `multiprocessing.Process`, `multiprocessing.Pool`, and `concurrent.futures.ProcessPoolExecutor`.
- The Windows-specific rules (`spawn`, `if __name__ == "__main__"`, same `mp_context`).
- The `Attach` / `Detach` lifecycle and what happens if you skip it.
- How structured logging, `extra`, `contextualize`, and custom log levels behave across processes.
- The four multiprocess environment variables and when to touch them.
- What the runtime does under backpressure, sink unavailability, worker crash, and mixed shutdown.
- How to read the delivery-state counters and the shutdown summary.
- `mp.ReopenLogFiles()` for external rotation.
- A checklist of common failure modes and a troubleshooting section.

The single-process tutorial in [`01_quick_start.md`](01_quick_start.md) and the configuration layers in [`02_configuration_guide.md`](02_configuration_guide.md) are prerequisites.

## 2. When to use `dsafelogger.mp` (and when not to)

Use it when:

- Multiple worker processes need to write to a shared destination, and you do not want each worker to open its own copy of the file (which on Windows is fragile and on every OS makes routing/manifest accounting much harder).
- You want one place to look for delivery-state counters and shutdown summaries across all workers.
- You need centralized integrity sidecars and manifest entries instead of per-worker fragments.

You do not need it when:

- The application is single-process. Use `dsafelogger.ConfigureLogger()` from `dsafelogger` instead.
- Workers only log to stdout/stderr and a separate aggregator (for example a sidecar that tails container logs) is responsible for combining them.
- You only fan out short-lived subprocesses for unrelated tasks and accept that each opens its own file.

`dsafelogger.mp` does not replace `dsafelogger`. The single-process API is still the entry point for the parent process when multiprocess is not used. The two `ConfigureLogger` symbols are separate: `dsafelogger.ConfigureLogger` and `dsafelogger.mp.ConfigureLogger` configure different runtimes and must not be mixed in the same process.

## 3. What the Writer guarantees, and what it does not

D-SafeLogger centralizes file ownership in a parent-side Writer and classifies the delivery outcome of records the runtime accepts. That is the contract.

The Writer does **not** guarantee:

- That every record survives a hard process termination, an OS crash, or power loss.
- That records lost before the runtime accepts them (for example, a worker that crashes before `mp.AttachCurrentProcess()` returns) are recovered.
- That `UnexplainedLost` is always zero. The whole point of that counter is that some abnormal scenarios cannot be classified more precisely; the value is making them visible rather than silent.
- That records are never dropped under backpressure. If the queue saturates and the timeout elapses, drops happen — but they are counted as `KnownDropped`, not silent loss.

A useful one-line summary: *D-SafeLogger centralizes file ownership and classifies delivery outcomes. It does not guarantee that records survive hard process termination, OS crash, power loss, or records that were never accepted by the logging runtime.*

## 4. The basic model

```
   Parent process                                Worker processes
   ┌────────────────────────────────┐            ┌──────────────────┐
   │ mp.ConfigureLogger(...)        │            │ mp.AttachCurrent │
   │                                │            │   Process(ctx)   │
   │   ┌──────────────────────┐     │            │                  │
   │   │ Writer runtime       │     │            │ logger =         │
   │   │  ├─ log thread       │◀───IPC log queue──┤   mp.GetLogger()│
   │   │  ├─ control thread   │◀───IPC control    │ logger.info(..) │
   │   │  └─ counters/summary │     │            │                  │
   │   └──────────────────────┘     │            │ mp.DetachCurrent │
   │             │                  │            │   Process()      │
   │             ▼                  │            └──────────────────┘
   │   File sinks (owned here)      │
   │   - routed log files           │
   │   - SHA-256 sidecars           │
   │   - optional manifest          │
   └────────────────────────────────┘
```

Key invariants:

- The Writer runtime lives in the parent process. It owns the file sinks, routing strategy, integrity sidecars, manifest, archive/purge, and reopen.
- Workers **never** open the shared log files directly. They submit `LogEvent` messages over an IPC queue.
- The control plane (attach, detach, reopen, bootstrap-ready) uses a separate IPC queue and a `Pipe` for ACKs.
- Delivery-state counters and the shutdown summary are produced by the Writer side, not by individual workers.

## 5. Pattern A — `multiprocessing.Process`

This is the explicit pattern. It makes the lifecycle visible and is the easiest to reason about on Windows.

```python
"""mp_process_demo.py — Writer-owned logging from worker processes."""

import multiprocessing
from dsafelogger import mp


def worker(log_ctx, worker_id: int) -> None:
    mp.AttachCurrentProcess(log_ctx)
    try:
        logger = mp.GetLogger("jobs.worker")
        with logger.contextualize(worker=worker_id):
            logger.info("worker started")
            # ... work ...
            logger.info("worker finished")
    finally:
        mp.DetachCurrentProcess()


def main() -> None:
    proc_ctx = multiprocessing.get_context("spawn")

    log_ctx = mp.ConfigureLogger(
        log_path="./logs",
        pg_name="MPDemo",
        routing_mode="daily",
        structured=True,
        mp_context=proc_ctx,
    )

    processes = [
        proc_ctx.Process(target=worker, args=(log_ctx, i))
        for i in range(4)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join()
        if p.exitcode != 0:
            raise RuntimeError(f"worker failed: pid={p.pid} exit={p.exitcode}")

    mp.DetachCurrentProcess()


if __name__ == "__main__":
    main()
```

Notes:

- `if __name__ == "__main__"` is required on Windows and harmless on POSIX. Without it, the spawned children re-run `main()` recursively.
- `proc_ctx` is reused for both `mp.ConfigureLogger(mp_context=...)` and `proc_ctx.Process(...)`. Mixing contexts (for example, calling `multiprocessing.Process(...)` directly while the Writer was configured with a spawn context) can produce IPC primitives that are incompatible across platforms.
- The parent process is also attached automatically by `mp.ConfigureLogger`. The final `mp.DetachCurrentProcess()` releases the parent.

## 6. Pattern B — `multiprocessing.Pool`

`Pool` workers are short-lived but reused. The initializer attaches each worker once; per-worker cleanup follows the pool's own worker lifecycle rather than an explicit detach call from your code.

```python
import multiprocessing
from dsafelogger import mp


def run_job(job_id: int) -> int:
    logger = mp.GetLogger("jobs.pool")
    logger.info("processing job", extra={"job_id": job_id})
    return job_id


if __name__ == "__main__":
    proc_ctx = multiprocessing.get_context("spawn")
    log_ctx = mp.ConfigureLogger(
        log_path="./logs",
        pg_name="PoolDemo",
        mp_context=proc_ctx,
    )
    init_fn, init_args = mp.GetWorkerInitializer(log_ctx)

    with proc_ctx.Pool(initializer=init_fn, initargs=init_args) as pool:
        results = pool.map(run_job, range(10))

    mp.DetachCurrentProcess()
```

Notes:

- `mp.GetWorkerInitializer(log_ctx)` returns an initializer function and init arguments that attach each worker to the Writer session represented by the `BootstrapContext`. The `Pool` calls it once per worker before any task runs.
- Inside `run_job`, no explicit attach is needed; `mp.GetLogger()` works because the initializer already attached the worker.
- The initializer attaches each worker before tasks run. Worker cleanup is handled by the worker process lifetime; use the explicit `Process` pattern when you need full attach/detach visibility per worker.

## 7. Pattern C — `concurrent.futures.ProcessPoolExecutor`

`ProcessPoolExecutor` accepts the same initializer pair, plus an `mp_context` parameter:

```python
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from dsafelogger import mp


def run_job(job_id: int) -> int:
    logger = mp.GetLogger("jobs.executor")
    logger.info("processing job", extra={"job_id": job_id})
    return job_id


if __name__ == "__main__":
    proc_ctx = multiprocessing.get_context("spawn")
    log_ctx = mp.ConfigureLogger(
        log_path="./logs",
        pg_name="ExecutorDemo",
        mp_context=proc_ctx,
    )
    init_fn, init_args = mp.GetWorkerInitializer(log_ctx)

    with ProcessPoolExecutor(
        max_workers=4,
        mp_context=proc_ctx,
        initializer=init_fn,
        initargs=init_args,
    ) as executor:
        list(executor.map(run_job, range(10)))

    mp.DetachCurrentProcess()
```

Notes:

- Pass `mp_context=proc_ctx` to `ProcessPoolExecutor` so the executor's IPC primitives match the Writer's. This is the same rule as for `Pool`.
- `executor.map` and `executor.submit` both work; the initializer ensures every worker is attached before user functions run.

## 8. Windows: required rules for `spawn`

Windows uses `spawn` exclusively. Several rules turn into hard requirements:

- **`if __name__ == "__main__"` is mandatory** in any module that creates worker processes. Without it, the spawned children re-import the module and re-execute the parent setup, which on top of being incorrect will also try to re-create the Writer.
- **No process-creating side effects at import time.** `mp.ConfigureLogger(...)` should run inside a function (typically `main()`), not at module top level.
- **One `mp_context` value used everywhere.** Pass the same `proc_ctx = multiprocessing.get_context("spawn")` to `mp.ConfigureLogger(mp_context=...)` and to whatever creates workers (`proc_ctx.Process`, `proc_ctx.Pool`, or `ProcessPoolExecutor(mp_context=proc_ctx, ...)`).
- **Do not mix `multiprocessing.Process` and `proc_ctx.Process`.** They use different default IPC primitives and cannot share queues safely.
- **Custom log levels must be registered in workers as well.** See section 11.
- **Configuration is created in the parent.** Workers attach with the `BootstrapContext` they receive; they do not call `mp.ConfigureLogger` themselves.

The Writer validates the `BootstrapContext` during `AttachCurrentProcess`. If the worker has a different `protocol_version` or `registry_hash` (for example, a different set of registered custom levels), the attach fails fast instead of silently producing records with mismatched level names.

## 9. POSIX: `fork` notes

POSIX systems default to `fork`, which copies the parent's address space. Some practical consequences:

- The Writer runtime threads themselves are *not* inherited by forked children — Python's `fork` does not duplicate non-main threads. This is fine because workers are expected to attach explicitly anyway.
- File descriptors held by the parent (including those owned by the Writer's sinks) are duplicated into the child. Workers must not write to these file descriptors directly. The contract is: workers send `LogEvent`s over IPC and let the Writer do the file I/O.
- If you want the same code to run on Windows and POSIX without surprises, prefer `multiprocessing.get_context("spawn")` explicitly. Treating `spawn` as the baseline keeps the Windows rules in section 8 from becoming silent footguns elsewhere.
- If you use `fork`, do not call `mp.ConfigureLogger` and then immediately fork without re-attaching. The child should call `mp.AttachCurrentProcess(log_ctx)` exactly like a spawned worker.

## 10. Attach / Detach lifecycle

Lifecycle states for one process:

```
unattached --AttachCurrentProcess(ctx)--> attached --DetachCurrentProcess()--> unattached
```

Rules:

- The parent process is automatically attached as a side effect of `mp.ConfigureLogger(...)`. You do not call `AttachCurrentProcess` again in the parent.
- Each worker calls `mp.AttachCurrentProcess(log_ctx)` exactly once at startup. With `Pool`/`ProcessPoolExecutor`, the initializer does this.
- `mp.DetachCurrentProcess()` is **idempotent**: calling it on an unattached process is a no-op. `try / finally` blocks are safe even if attach failed.
- `mp.GetLogger()` raises `RuntimeError` if the calling process is not attached. Do not catch and ignore this; it means the logger configuration is missing.
- A second `AttachCurrentProcess` to a different `BootstrapContext` (different session) raises `RuntimeError`. One process is attached to one Writer at a time.
- The parent registers an `atexit` hook that detaches and stops the Writer cleanly. You do not need to call shutdown manually for normal exits, but doing so is fine and idempotent.

## 11. Structured logging, `extra`, `contextualize`

Multiprocess logging supports the same data path as single-process. The difference is *when* the snapshot is taken.

- `structured=True` is honored end-to-end. The Writer applies the structured formatter when emitting to the file sink. Workers do not format records themselves; they hand off `LogEvent`s containing the source state.
- `extra={...}` keys appear as first-class fields in the JSON output. Reserved `LogRecord` attributes are not overwritten.
- `logger.contextualize(...)` and `dsafelogger`'s context propagation work in workers. The producer-side snapshot is taken at hand-off so the Writer does not look up live `contextvars` on its side; this is what makes async hand-off safe across thread and process boundaries.
- Sensitive-keyword masking is applied on the Writer side using the keyword set established at parent `mp.ConfigureLogger` time. Worker-side runtime overrides do not bypass this.

A practical pattern:

```python
def worker(log_ctx, worker_id: int, request_id: str) -> None:
    mp.AttachCurrentProcess(log_ctx)
    try:
        logger = mp.GetLogger("api.worker")
        with logger.contextualize(worker=worker_id, request_id=request_id):
            logger.info("request received")
            # downstream calls inherit the same context
    finally:
        mp.DetachCurrentProcess()
```

## 12. Custom log levels with `spawn`

Custom levels live in a per-process registry. With `spawn`, that registry starts empty in each new worker.

Two valid patterns:

- **Module-level registration.** `register_level(...)` is called at import time in a module that every process imports. With `spawn`, this re-runs in each worker. Order it before any `mp.AttachCurrentProcess` call.
- **Initializer registration.** Wrap registration and attach in a small initializer function and pass that as the `initializer=` to `Pool` / `ProcessPoolExecutor`:

  ```python
  def init_worker(log_ctx):
      from dsafelogger import register_level, mp
      register_level("TRACE", value=5, abbreviation="TRC")
      mp.AttachCurrentProcess(log_ctx)
  ```

  Then `initargs=(log_ctx,)`.

The Writer validates the worker's level registry against the parent's during `AttachCurrentProcess` (see the registry hash in `BootstrapContext`). A mismatch fails the attach immediately.

`register_level()` must be called **before** `ConfigureLogger` in any process. Calling it after the runtime is initialized raises `RuntimeError`.

## 13. Multiprocess environment-variable knobs

These four environment variables tune the multiprocess data plane. They use the configured `env_prefix` (default `D_LOG`):

| Variable | Purpose | Default |
|---|---|---|
| `D_LOG_IPC_LOG_TIMEOUT` | Worker-side timeout when enqueuing a record into the log queue. | `0.5` (seconds) |
| `D_LOG_IPC_LOG_QUEUE_MAXSIZE` | Maximum size of the cross-process log queue. | `10000` |
| `D_LOG_IPC_CLIENT_QUEUE_MAXSIZE` | Maximum size of the per-client (per-worker) intermediate queue, if applicable. | mirrors `IPC_LOG_QUEUE_MAXSIZE` |
| `D_LOG_WRITER_FLUSH_BATCH` | Number of records the Writer flushes to the sink per batch. | `1` |

Guidelines:

- **You normally do not touch these.** The defaults are picked to keep memory bounded and shutdown predictable.
- Lower the maxsize values during a backpressure investigation to make drops happen sooner and visibly. Do not run production this way.
- Raising the maxsize values can mask a slow sink at the cost of larger memory usage in the parent. Do not raise above `100_000` without measuring; the runtime will warn.
- Lower `IPC_LOG_TIMEOUT` to keep workers from blocking longer than acceptable when the queue is full. Lower values increase the rate of `KnownDropped`.
- Raise `WRITER_FLUSH_BATCH` to reduce flush overhead at the cost of slightly delayed visibility on disk. Values above `1024` are accepted but trigger a warning at configure time, since high batch sizes reduce flush visibility.

All four variables are validated at parent `mp.ConfigureLogger` time. An unparseable value fails fast (since v23h) instead of being silently ignored.

## 14. Behavior under backpressure

When workers produce log records faster than the Writer can drain the queue:

1. The worker tries to enqueue. The IPC queue is bounded.
2. If the queue is full, the worker waits up to `D_LOG_IPC_LOG_TIMEOUT` seconds.
3. If the timeout elapses without space, the record is **dropped**, and the worker increments the local `KnownDropped` counter.
4. None of this hangs the host process indefinitely. There is no path where a single saturated worker can block the others forever.
5. At shutdown, the parent emits a summary that includes `attempted`, `accepted`, `delivered`, `KnownRejected`, `KnownDropped`, and `UnexplainedLost` totals.

What this means in practice:

- A bursty workload that briefly exceeds the queue size produces some `KnownDropped` count and zero `UnexplainedLost`.
- A workload that exceeds queue capacity for a long time produces a larger `KnownDropped` count, but still classifies the loss instead of leaving it invisible.
- If `UnexplainedLost` is non-zero in normal operation, that is a signal worth investigating — usually it points to a worker that crashed mid-record or to a configuration mismatch.

The `multiprocess_resilience` profile in [BENCHMARK.md](../BENCHMARK.md) exercises this scenario and documents what counters the runtime produces.

## 15. Behavior when a sink is unavailable

A sink can be unavailable for several reasons: the destination directory is missing, the disk is full, the file is locked by another process (most commonly an external rotator on Windows), or permissions changed at runtime.

When the Writer attempts to deliver and the sink rejects:

- The record is classified as `KnownRejected`. It is **not** silently retried until the queue saturates.
- The rejection cause is surfaced through the runtime's stderr warnings. The Writer does not swallow the exception.
- File-sink ownership stays with the Writer. Workers do not see the failure directly — they see the queue continuing to accept records, and the rejection counter rising on the Writer side.
- Once the underlying condition clears (disk freed, permissions corrected, external rotator releases the file), subsequent records can be delivered. There is no implicit retry of already-rejected records; rejected is a terminal classification.

For external rotation specifically (the rotator owns the file briefly), see section 17.

## 16. Behavior on worker crash and mixed shutdown

A "mixed shutdown" is when some workers exit cleanly through `Detach` and at least one worker terminates abnormally (segfault, `kill -9`, OOM kill, uncaught exception that bypasses `try/finally`).

What the Writer observes:

- Records the crashed worker had already enqueued **before** the crash are still in the IPC queue and will be processed normally.
- Records that were in flight on the worker side at crash time are lost — the worker process is gone.
- The Writer cannot distinguish "in flight and lost" from "never produced" for the crashed worker. The shutdown summary distinguishes a clean Writer shutdown that coincided with abnormal worker termination from a fully clean run — in the resilience profile, the corresponding value is `clean_with_worker_crash` rather than `clean` — so the operator can see that some `UnexplainedLost` count is expected for that run.
- The Writer itself shuts down cleanly: it drains the queue, finalizes counters, and writes the summary even when one or more workers exited abnormally.

What the Writer cannot do:

- Reconstruct records that were never sent.
- Distinguish between a clean termination and a hard kill on the worker side beyond what the OS exposes (`exitcode`).
- Recover from a power loss or OS crash that takes the parent down with the workers.

The benchmark resilience profile contains a `rolling_restart_mixed_shutdown` scenario that exercises this and shows what the summary looks like.

## 17. `mp.ReopenLogFiles` for external rotation

When an external rotator (`logrotate`, a Windows scheduled task, a manual `mv` + `touch`) renames or deletes the active log file, the Writer's open file descriptor still points at the renamed/deleted inode. The new file is not written.

`mp.ReopenLogFiles()` tells the Writer to close and re-open all file sinks:

```python
import signal
from dsafelogger import mp

def handle_hup(signum, frame):
    mp.ReopenLogFiles()

signal.signal(signal.SIGHUP, handle_hup)
```

Constraints:

- This is intended for `routing_mode='none'` (no internal routing). Internal routing already opens the next file at boundaries; calling reopen there is rejected by the Writer with `ValueError`.
- The call sends a `REOPEN` control request and waits synchronously for the ACK. If the control plane does not ACK within the configured timeout, `TimeoutError` is raised.
- The single-process equivalent is `dsafelogger.ReopenLogFiles()`. The two are not interchangeable: each operates on its own runtime.

See [`13_external_rotation_reopen.md`](13_external_rotation_reopen.md) for the full external-rotation scenario.

## 18. Common failure modes

The patterns that show up most often in user reports:

- **Mixing `mp_context`s.** The Writer is configured with a spawn context but workers are created with `multiprocessing.Process(...)` (default context). The IPC queues then come from different contexts and message exchange becomes unreliable. Always reuse one `proc_ctx`.
- **Missing `if __name__ == "__main__"` on Windows.** Children re-execute the parent setup and try to re-configure the Writer. Symptoms: hanging startup or `RuntimeError: mp.ConfigureLogger() has already been called in this process` from the spawned child.
- **Calling `mp.GetLogger()` in a worker without attaching.** Raises `RuntimeError`. The fix is to use `GetWorkerInitializer` (Pool/Executor) or call `AttachCurrentProcess` explicitly (`Process`).
- **Forgetting `Detach` in a `Process` worker.** The atexit hook still runs in the parent, but the worker may not get a chance to send a clean detach. The result is usually fine for short jobs but can leave the run summary marked as not fully clean.
- **Skipping `process.join()` in the parent.** The parent's `atexit` hook may stop the Writer while worker queues are still being drained. Always `join()` workers before letting the parent exit.
- **Registering custom levels only in the parent under `spawn`.** Workers fail to attach because the registry hash differs. Register in workers too (module-level import or initializer function).
- **Setting queue maxsize too small.** `D_LOG_IPC_LOG_QUEUE_MAXSIZE=10` produces a flood of `KnownDropped`. Useful for testing the failure path; not useful for production.
- **Re-using a single `BootstrapContext` across multiple `mp.ConfigureLogger` calls.** A `BootstrapContext` is tied to one Writer session and one parent process. If the parent restarts, generate a new context.
- **Adding stdlib `logging.FileHandler` to a worker logger.** This bypasses the Writer and takes ownership of a file the Writer thinks it owns. Do not mix; let the Writer own all sinks.

## 19. Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| Worker logs do not appear in the file. | Worker not attached, or `mp.GetLogger()` returned the stdlib logger. | Verify `AttachCurrentProcess` is reached; check the Writer's `attempted`/`accepted` counters. |
| Process hangs at shutdown. | Worker still has the queue open and the parent is waiting for drain. | Ensure `process.join()` happens before the parent exits; check for missing `Detach`. |
| Spawned worker on Windows fails immediately. | Missing `if __name__ == "__main__"` or process-creating side effect at import. | Move setup into a `main()` function; ensure the entry point is guarded. |
| `RuntimeError: mp.ConfigureLogger() has already been called in this process`. | Either the parent ran `ConfigureLogger` twice, or a spawned child is re-executing parent setup. | Check the entry-point guard; do not call `mp.ConfigureLogger` from worker code. |
| `RuntimeError: mp.GetLogger() requires the current process to be attached`. | Worker did not attach. | Use `GetWorkerInitializer` (Pool/Executor) or call `AttachCurrentProcess` (Process). |
| `RuntimeError` on attach with registry-hash mismatch. | Custom levels registered in parent but not in worker (or vice versa). | Register the same set of custom levels in every process before attach. |
| Records counted as `KnownDropped` even though throughput looks low. | `D_LOG_IPC_LOG_TIMEOUT` is set too low, or maxsize was tuned down. | Inspect the relevant env variables; restore defaults during normal operation. |
| Records counted as `KnownRejected` after an external tool ran. | Sink became unavailable (lock, permissions, deleted directory). | Inspect the Writer's stderr warnings for the rejection cause. |
| Duplicate logs appear. | A worker also added a stdlib `FileHandler` to the same path. | Remove the worker-side handler; let the Writer own the sink. |
| Logs appear in parent but not workers. | Workers attached to a different Writer session or skipped attach. | Confirm workers receive the same `BootstrapContext` instance the parent created. |
| Environment overrides have no effect on workers. | The override is read at parent `mp.ConfigureLogger` time, not at worker attach time. | Set environment variables before the parent starts. |
| `mp.ReopenLogFiles()` raises `ValueError`. | Configured `routing_mode` is not `'none'`. | Reopen is only meaningful with no internal routing; let internal routing handle boundaries instead. |
| `mp.ReopenLogFiles()` raises `TimeoutError`. | Control plane is saturated or the Writer is unresponsive. | Investigate Writer-side stderr; consider whether the sink is blocking. |

If a symptom is not on this list and `UnexplainedLost` is non-zero in the shutdown summary, that counter is the right starting point: it means the runtime knows it cannot account for some records, and the BENCHMARK.md resilience profile shows how the same scenarios look in controlled tests.

## See also

- [README](../README.md) — entry-point overview.
- [`02_configuration_guide.md`](02_configuration_guide.md) — three-layer configuration shared with single-process mode.
- [`13_external_rotation_reopen.md`](13_external_rotation_reopen.md) — full external-rotation walkthrough.
- [`BENCHMARK.md`](../BENCHMARK.md) — selected resilience profile and the explicit "what to claim / what not to claim" boundaries.
- [`docs/api/dsafelogger__mp.md`](../docs/api/dsafelogger__mp.md) — generated API reference for `dsafelogger.mp`.
