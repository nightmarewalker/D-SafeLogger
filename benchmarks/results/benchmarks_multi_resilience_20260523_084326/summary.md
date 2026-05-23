# Multiprocess Comparison Benchmark — v23a

- Generated: 2026-05-23 08:45:38 UTC
- Profile: **resilience_profile**
- Messages per run: 100
- Repeats: 1
- Backends: D-SafeLogger, stdlib logging, loguru
- Patterns: root_p1, root_p4, root_p8, module_p4

## Environment

- OS: Windows 11
- Python: 3.14.3 (C:\Python\314\python.exe)
- GIL: enabled
- CPU logical count: 16
- scratch_root: C:\TempX\D-SafeLogger-bench\benchmarks_multi_resilience_20260523_084326

## Pattern Legend

- `root_p1`: 1 child -> root sink. Multiprocess IPC baseline without fan-in contention.
- `root_p4`: 4 children -> shared root sink. Moderate fan-in onto one parent writer.
- `root_p8`: 8 children -> shared root sink. High fan-in stress case for single-writer scaling.
- `module_p4`: 4 children -> module-specific route (bench.module) and dedicated module sink.

## Results

### Python 3.13

#### GIL enabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 50 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| ipc_forced_disconnect | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |

#### GIL disabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 50 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| ipc_forced_disconnect | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |

### Python 3.14

#### GIL enabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 50 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| ipc_forced_disconnect | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |

#### GIL disabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 50 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, partial_delivered, known_rejected, known_dropped, unexplained_lost, writer_reject_breakdown, worker_drop_breakdown, writer_drop_breakdown |  |
| ipc_forced_disconnect | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| ipc_forced_disconnect | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
