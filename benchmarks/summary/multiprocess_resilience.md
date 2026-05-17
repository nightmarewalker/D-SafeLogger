# Multiprocess Resilience Profile Summary

- Latest session: `benchmarks_multi_resilience_20260506_211129`
- Artifacts: [`benchmarks/results/benchmarks_multi_resilience_20260506_211129/summary.md`](../results/benchmarks_multi_resilience_20260506_211129/summary.md), [`benchmarks/results/benchmarks_multi_resilience_20260506_211129/summary.json`](../results/benchmarks_multi_resilience_20260506_211129/summary.json)
- D-SafeLogger produced classified loss/reject/drop fields for 12/12 summary rows.
- Fully explained D-SafeLogger rows: 12/12.

#### Python 3.13

##### GIL enabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 99 | 0 | 1 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |

##### GIL disabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 97 | 0 | 3 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |

#### Python 3.14

##### GIL enabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |

##### GIL disabled

| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |
|----------|---------|--------|------|----------:|---------:|----------:|--------------:|-------------:|----------------:|----------|---------------|-------|
| burst_backpressure | D-SafeLogger | ok | 1/1 | 100 | 100 | 100 | 0 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| burst_backpressure | stdlib logging | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| burst_backpressure | loguru | observability_gap | 1/1 | 100 | — | 100 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | D-SafeLogger | ok | 1/1 | 62 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| rolling_restart_mixed_shutdown | stdlib logging | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| rolling_restart_mixed_shutdown | loguru | observability_gap | 1/1 | 62 | — | 62 | — | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | D-SafeLogger | ok | 1/1 | 100 | 100 | 0 | 100 | 0 | 0 | clean | attempted, accepted, delivered, transport_timeout_drop, transport_overload_shed, writer_reject_counters, writer_partial_delivered, writer_drain_deadline_loss |  |
| sink_temporarily_unavailable | stdlib logging | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |
| sink_temporarily_unavailable | loguru | observability_gap | 1/1 | 100 | — | 0 | 100 | — | — | unknown | attempted, delivered |  |

## Source

- Manifest key: `multiprocess_resilience`
- Selected session: `benchmarks_multi_resilience_20260506_211129`
- Session artifacts: [`benchmarks/results/benchmarks_multi_resilience_20260506_211129/summary.md`](../results/benchmarks_multi_resilience_20260506_211129/summary.md), [`benchmarks/results/benchmarks_multi_resilience_20260506_211129/summary.json`](../results/benchmarks_multi_resilience_20260506_211129/summary.json)
