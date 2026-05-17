# Multiprocess Comparison Benchmark — v23a

- Generated: 2026-05-06 21:13:29 UTC
- Profile: **resilience_profile**
- Messages per run: 100
- Repeats: 1
- Backends: D-SafeLogger, stdlib logging, loguru
- Patterns: root_p1, root_p4, root_p8, module_p4

## Environment

- OS: Windows 11
- Python: 3.14.3 (G:\マイドライブ\00_個人開発\pyDev\D-Logger\.venv\Scripts\python.exe)
- GIL: enabled
- CPU logical count: 16
- scratch_root: C:\TempX\D-SafeLogger-bench\benchmarks_multi_resilience_20260506_211129

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
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 99 | 0 | 1 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |

#### GIL disabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 97 | 0 | 3 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |

### Python 3.14

#### GIL enabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |

#### GIL disabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
