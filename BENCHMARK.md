# Benchmark Analysis

This document is the public benchmark analysis for D-SafeLogger. It is manually edited and is intended to be usable as the basis for README benchmark claims.

Benchmark facts are kept separately from this analysis:

- Per-run artifacts: [`benchmarks/results/`](benchmarks/results/)
- Selected-session manifest: [`benchmarks/summary/manifest.json`](benchmarks/summary/manifest.json)
- Generated summary index: [`benchmarks/summary/index.md`](benchmarks/summary/index.md)

## Executive Summary

D-SafeLogger is competitive in single-process logging, especially in async mode and single-thread workloads. In the selected single-process run, D-SafeLogger async was the throughput leader in 8/16 cells and achieved the lowest p50 latency in 12/16 cells. D-SafeLogger async also beat D-SafeLogger sync in both throughput and p50 latency in all 16 comparable cells.

Multiprocess results should be interpreted differently. D-SafeLogger is not the fastest multiprocess backend in this benchmark; stdlib logging leads throughput in all measured multiprocess performance cells. D-SafeLogger's multiprocess value is not raw speed. Its value is Writer-owned sinks, explicit attach/detach, bounded shutdown, and classified delivery-state observability under operational stress.

The resilience profile is the strongest multiprocess evidence. Across 16 D-SafeLogger resilience summary rows, D-SafeLogger produced classified loss/reject/drop fields for 16/16 rows and fully explained 16/16 rows. That is the benchmark-backed claim: D-SafeLogger can explain what happened to records under backpressure, sink rejection, mixed worker shutdown, and warning-IPC fallback, instead of leaving delivery state ambiguous.

## Published Summaries

- Single-process comparison: [`benchmarks/summary/single_process.md`](benchmarks/summary/single_process.md)
- Multiprocess integrity profile: [`benchmarks/summary/multiprocess_integrity.md`](benchmarks/summary/multiprocess_integrity.md)
- Multiprocess performance profile: [`benchmarks/summary/multiprocess_performance.md`](benchmarks/summary/multiprocess_performance.md)
- Multiprocess resilience profile: [`benchmarks/summary/multiprocess_resilience.md`](benchmarks/summary/multiprocess_resilience.md)

## Selected Runs

| Category | Selected Session | Purpose |
|---|---|---|
| Single-process | `benchmark_20260506_180018` | Throughput and latency comparison across D-SafeLogger, stdlib logging, loguru, and structlog |
| Multiprocess integrity | `benchmarks_multi_integ_20260506_185947` | Normal-condition delivery completeness and JSON/route integrity |
| Multiprocess performance | `benchmarks_multi_perf_20260506_190518` | Raw multiprocess throughput and latency comparison |
| Multiprocess resilience | `benchmarks_multi_resilience_20260523_084326` | Operational failure-mode observability and classified delivery state |

The selected sessions are controlled by [`benchmarks/summary/manifest.json`](benchmarks/summary/manifest.json). Running a new benchmark does not automatically change the public analysis.

Selection rationale:

- The selected sessions were refreshed together after the v23i publication-readiness fixes so the public summaries and analysis use one current benchmark set.
- A benchmark session should only replace a selected session when it is intentionally promoted in the manifest and this analysis is reviewed for updated claims.

## Single-Process Results

The single-process benchmark covers Python 3.13 and 3.14, GIL enabled and disabled, text and JSON output, single-thread and multi-thread workloads, and sync/async modes where applicable.

Key results from the selected run:

- D-SafeLogger async beat D-SafeLogger sync on throughput in 16/16 comparable cells.
- D-SafeLogger async beat D-SafeLogger sync on p50 latency in 16/16 comparable cells.
- Throughput leaders across all 16 cells: D-SafeLogger async 8/16, structlog sync 5/16, stdlib logging async 3/16.
- Best D-SafeLogger mode beat all non-D-SafeLogger backends on throughput in 8/16 cells.
- Best D-SafeLogger mode achieved the lowest p50 latency in 12/16 cells.

The strongest D-SafeLogger single-process result is Python 3.14 with GIL enabled:

| Scenario | D-SafeLogger Mode | Throughput | p50 | p90 | p99 |
|---|---|---:|---:|---:|---:|
| text | async | 51,554 msg/s | 16.7 us | 19.6 us | 39.6 us |
| JSON | async | 52,081 msg/s | 16.7 us | 19.2 us | 36.8 us |

Interpretation:

- D-SafeLogger async is the preferred high-throughput single-process mode in this benchmark.
- D-SafeLogger's strongest area is low-latency single-process logging, especially under Python 3.14/GIL enabled.
- Multi-thread throughput is not universally led by D-SafeLogger. structlog sync is strong in several multi-thread cells, and stdlib logging async wins some Python 3.14/GIL enabled multi-thread cells.
- The correct single-process claim is "competitive and often fastest in low-latency async single-process logging," not "always fastest."

## Multiprocess Integrity Results

The integrity profile checks normal-condition delivery completeness and structured output integrity across D-SafeLogger, stdlib logging, and loguru.

Selected result summary:

| Backend | Raw Runs | Failures | Missing | Duplicates | JSON Parse | Route Mismatch |
|---|---:|---:|---:|---:|---:|---:|
| D-SafeLogger | 96 | 0 | 0 | 0 | 0 | 0 |
| stdlib logging | 96 | 0 | 0 | 0 | 0 | 0 |
| loguru | 96 | 0 | 0 | 0 | 0 | 0 |

Interpretation:

- Under normal benchmark conditions, all three backends delivered the expected records without missing, duplicate, JSON parse, or route mismatch anomalies.
- This profile is a correctness gate, not D-SafeLogger's differentiating claim.
- The result supports that D-SafeLogger's Writer-based multiprocess architecture preserves normal delivery integrity, but it should not be used to claim uniqueness.

## Multiprocess Performance Results

The multiprocess performance profile measures raw throughput and latency for process counts and routing patterns. In this profile, stdlib logging wins throughput in all measured cells.

Average throughput by pattern and scenario:

| Pattern | Scenario | D-SafeLogger avg | stdlib avg | loguru avg | Throughput Wins (DS/std/loguru) |
|---|---:|---:|---:|---:|---:|
| root_p1 | text | 797 | 1,280 | 995 | 0/4/0 |
| root_p1 | JSON | 803 | 1,253 | 1,009 | 0/4/0 |
| root_p4 | text | 653 | 1,110 | 849 | 0/4/0 |
| root_p4 | JSON | 659 | 1,134 | 874 | 0/4/0 |
| root_p8 | text | 468 | 852 | 650 | 0/4/0 |
| root_p8 | JSON | 456 | 802 | 656 | 0/4/0 |
| module_p4 | text | 644 | 1,120 | 872 | 0/4/0 |
| module_p4 | JSON | 643 | 1,084 | 878 | 0/4/0 |

Interpretation:

- D-SafeLogger multiprocess mode has measurable fixed costs: record serialization, client-to-writer IPC, route dispatch, Writer-side reconstruction, sink classification, and close-marker drain accounting.
- Those costs are intentional tradeoffs for central sink ownership and delivery-state observability.
- The correct multiprocess performance claim is not "fastest." The correct claim is "controlled, observable, Writer-owned multiprocess logging with explicit failure accounting."

## Multiprocess Resilience Results

The resilience profile measures what can be explained during operational stress. This is the most important multiprocess benchmark for D-SafeLogger's design goals.

Selected result summary:

- D-SafeLogger produced classified loss/reject/drop fields for 16/16 summary rows.
- D-SafeLogger fully explained 16/16 summary rows.
- stdlib logging and loguru rows are marked `observability_gap` where accepted/dropped/unexplained state cannot be classified by the benchmarked backend contract.

Representative D-SafeLogger rows:

| Scenario | Python/GIL | Attempted | Accepted | Delivered | KnownRejected | KnownDropped | UnexplainedLost | Shutdown |
|---|---|---:|---:|---:|---:|---:|---:|---|
| burst_backpressure | all measured | 100 | 100 | 100 | 0 | 0 | 0 | clean |
| ipc_forced_disconnect | all measured | 100 | 100 | 100 | 0 | 0 | 0 | clean |
| rolling_restart_mixed_shutdown | all measured | 50 | 62 | 62 | 0 | 0 | 0 | clean_with_worker_crash |
| sink_temporarily_unavailable | all measured | 100 | 100 | 0 | 100 | 0 | 0 | clean |

Interpretation:

- In backpressure scenarios, D-SafeLogger may drop records, but the drops are classified as known drops rather than unexplained loss.
- In warning-IPC fallback scenarios, D-SafeLogger records per-worker fallback warning files while preserving delivery accounting.
- In mixed shutdown scenarios, D-SafeLogger can distinguish a clean writer shutdown with worker crash/termination from unexplained record loss.
- In mixed shutdown rows, `attempted` can be lower than `accepted` because a crashed worker may enqueue records before it can report its local attempted count via DETACH. `clean_with_worker_crash` and `snapshot_complete=false` mark that attempted-side worker accounting is incomplete.
- In sink-unavailable scenarios, D-SafeLogger classifies rejected records as known sink rejects rather than reporting ambiguous loss.
- This is the core multiprocess claim: D-SafeLogger does not promise impossible failure-free logging; it promises explicit accounting of what happened.

### Console-less Observability

The resilience benchmark now reads D-SafeLogger delivery state through the public `dsafelogger.mp.GetDeliveryStatus()` API instead of a Writer runtime private method. The benchmark records the public accounting schema, including `writer_reject_breakdown`, `worker_drop_breakdown`, `writer_drop_breakdown`, and `partial_delivered` as a separate non-reject category.

`partial_delivered` is a third terminal state: it is neither `delivered` (all required sinks succeeded) nor `known_rejected` (zero required sinks succeeded). The writer-side invariant is `accepted = delivered + partial_delivered + known_rejected + writer_known_dropped + unexplained_lost`.

For new resilience sessions, D-SafeLogger also enables `runtime_warning_path` and `shutdown_report_path` in the benchmark scratch directory. Runtime warnings are emitted to an independent JSON Lines sink, and shutdown reports provide an atomic final snapshot for post-run diagnosis without requiring console output. Workers that cannot reach the Writer warning IPC path fall back to per-pid local files named `<runtime_warning_path>.<pid>.fallback.jsonl`; console-less deployments should collect both the primary warning file and any fallback files.

See [`docs/design/D-SafeLogger_DeliveryStatusSchema_v23m.md`](docs/design/D-SafeLogger_DeliveryStatusSchema_v23m.md) for the authoritative accounting contract.

## What To Claim

- D-SafeLogger has zero runtime dependencies.
- D-SafeLogger provides append-only file handling without rename/truncate rotation.
- D-SafeLogger supports structured JSON logging and stdlib-compatible logger integration.
- D-SafeLogger async is competitive in single-process logging and leads several low-latency cells in the selected benchmark.
- D-SafeLogger multiprocess mode centralizes sink ownership in a Writer runtime.
- D-SafeLogger multiprocess resilience profiling exposes classified delivery-state counters: attempted, accepted, delivered, known rejected, known dropped, and unexplained lost.
- D-SafeLogger multiprocess observability can be consumed without console output through `GetDeliveryStatus()`, runtime warning JSON Lines, and shutdown report JSON.

## What Not To Claim

- Do not claim D-SafeLogger is always the fastest backend.
- Do not claim D-SafeLogger multiprocess mode beats stdlib logging on raw throughput in this benchmark.
- Do not claim multiprocess logging can never lose records under operational failure.
- Do not claim sink outage, worker crash, or hard process termination is made impossible.
- Do not mix diagnostic benchmark results with normal logging throughput results.

## Reproduction

Official tests use the dev dependency group. The library runtime remains dependency-free; the test environment does not.

```bash
uv sync --group dev
uv run pytest tests -v
```

Single-process benchmark:

```bash
uv sync --group benchmark
uv run python benchmarks/run_benchmark.py
```

Multiprocess resilience benchmark:

```bash
uv sync --group benchmark
uv run python benchmarks/run_multiprocess_compare_v23a.py --repo-root . --profile resilience_profile --messages 100 --repeat 1
```

Regenerate selected summary files from the manifest:

```bash
uv run python benchmarks/update_summary.py
```

## Maintenance Model

Benchmark runners write session artifacts under `benchmarks/results/`. They do not edit this document.

To promote a benchmark run into the public summary:

1. Add or update the session name in `benchmarks/summary/manifest.json`.
2. Run `uv run python benchmarks/update_summary.py`.
3. Review the generated files in `benchmarks/summary/`.
4. Manually update this analysis only when the interpretation or published claim changes.
5. When promoted benchmark values are cited in `README.md` or `README_ja.md`, update those README claims in the same change.
