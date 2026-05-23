# v23k Multiprocess Observability Test Matrix

This supplement maps the v23k multiprocess observability behavior to tests.

## Runtime Warning

- `tests/test_runtime_warning.py` verifies JSONL required/optional fields.
- It verifies Writer-side warnings, worker warning queue aggregation, queue-full fallback files, and non-blocking worker warning behavior.
- It verifies rate limiting, module transport drops, concurrent writes, and warning queue drain completion/incompletion.

## Delivery Accounting

- `tests/test_mp_runtime.py` verifies `attempted`, `accepted`, `delivered`, `partial_delivered`, writer reject breakdown, worker drop breakdown, writer drop breakdown, and accounting invariants.
- It verifies sink/policy mixed failure is counted as one rejected record.
- It verifies runtime STATUS does not classify active clients as missing-detach clients.

## Shutdown Report

- `tests/test_shutdown_report.py` verifies atomic write, clean shutdown report shape, missing worker identity, drain deadline result, write failure fallback, source-separated drop breakdowns, partial delivery independence, and warning queue drain reporting.
- Shutdown report tests verify both writer-side and attempted-side invariants when `snapshot_complete` is true.

## Public API

- `tests/test_delivery_status_api.py` verifies `mp.GetDeliveryStatus()` before/after configure, ACK timeout propagation, active-client incomplete snapshots, sink reject reporting, partial delivery, complete snapshots after detach, and writer-side invariants.
- `tests/typing_smoke/public_api_smoke.py` verifies the public `mp.DeliveryStatus` type from a user perspective.

## Benchmark Coverage

- `benchmarks/run_multiprocess_compare_v23a.py` consumes public `mp.GetDeliveryStatus()` instead of private WriterRuntime status methods.
- Resilience summaries use `writer_reject_breakdown`, `worker_drop_breakdown`, and `writer_drop_breakdown` so `partial_delivered` remains an independent terminal state and writer-originated drops are not mixed into worker drops.
