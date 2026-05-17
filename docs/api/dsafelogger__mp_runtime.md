# Multiprocess Writer Runtime

**Module**: `dsafelogger._mp_runtime`

Writer runtime for D-SafeLogger multiprocess.

WriterRuntime runs in the parent (Writer) process as two background threads:
  - _log_loop: drains the log plane queue, reconstructs LogRecords, dispatches to sinks
  - _control_loop: handles ATTACH / DETACH / REOPEN / STOP / STATUS requests

The WriterRuntime owns all file and console sink handlers; worker processes
only send serialised LogEvent dicts via the log_queue.

v23b: drain completion is determined by client close markers on the log plane,
not by Queue.empty(). Each client registered via ATTACH is expected to send a
CloseMarker on the log_queue before sending DETACH on the control_queue.
If a client cannot send its close marker (close_marker_failed=True in the DETACH
payload), the Writer records it as degraded and includes it in drain completion.

v23h: counters revised for spec §12.3 alignment.
  - `_writer_sink_reject` / `_writer_policy_reject` now count *per record*
    over the *required* sink set (best-effort sinks such as ColorStreamHandler
    do not contribute).
  - `_writer_event_reject` was split into `_writer_reconstruct_reject`
    (LogEvent reconstruct failure) and `_writer_close_marker_reject`
    (invalid CloseMarker / session mismatch / unknown client).
  - `_writer_best_effort_failures` is a visibility-only counter for
    best-effort sink failures (not aggregated into `_reject_counter`).
  - stderr warnings for sink/policy/best-effort/reconstruct/close-marker
    rejects are rate-limited (1st + every 100th).
  - idle / shutdown flush logic only runs when `writer_flush_batch > 1`.
  - `__init__` validates `ctx.writer_flush_batch >= 1`.

## Classes

### `WriterRuntime(ctx: 'BootstrapContext', sink_groups: 'dict[str, list[logging.Handler]]') -> 'None'`

Owns sink handlers and drives log/control event loops.

Public methods:

- `start(self) -> 'None'`
- `stop(self, timeout: 'float' = 10.0) -> 'None'`

## Constants

| Name | Type | Value |
|---|---|---|
| `WRITER_STOP_WAIT_TIMEOUT_SEC` | `float` | `10.0` |
