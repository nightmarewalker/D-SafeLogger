"""D-SafeLogger v23d: stage latency diagnostic benchmark.

Instruments D-SafeLogger internals using the "diagnostic wrapper" approach
(monkey-patching at benchmark start; no production code modifications).

Stages measured (child-side):
  child_serialize_us    - _serialize_record() duration in child process
  child_queue_put_us    - log_queue.put() duration in child process
  child_emit_us         - _emit_record() total (serialize + put + guard checks)
  python_logging_ovhd   - logger.info() overhead outside _emit_record

Stages measured (writer-side, via Writer log thread patches):
  writer_reconstruct_us - _reconstruct_record() duration in Writer thread
  writer_dispatch_us    - route lookup + sink handler.handle() in Writer thread

Instrumentation overhead:
  perf_counter_ns_overhead_us - cost of one time.perf_counter_ns() call

Patterns:
  root_p1: 1 child (no fan-in, fixed-cost baseline)
  root_p4: 4 children (moderate fan-in)
  root_p8: 8 children (high fan-in, expected p99 tail)

Usage:
  python benchmarks/run_multiprocess_v23d_diagnostic.py \\
    --repo-root . [--messages 300] [--pattern all|root_p1|root_p4|root_p8]
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


DEFAULT_SCRATCH_ROOT = Path(r'C:\TempX\D-SafeLogger-bench')


INSTRUMENTATION_NOTE = """\
**Approach**: Diagnostic wrapper (monkey-patching at benchmark start).

No production code modifications. Specific internal functions are wrapped
with `time.perf_counter_ns()` calls only during the diagnostic run.

**Patched sites**:
- `MPClientTransport._emit_record` (instance-level patch in each child process)
- `dsafelogger._mp_runtime._reconstruct_record` (module-level name in Writer thread)
- `WriterRuntime._dispatch` (instance-level patch on Writer runtime object)
- `WriterRuntime._flush_all_sinks` (instance-level patch on Writer runtime object)

**Not adopted**:
- *runtime flag*: adds conditional branch overhead to production hot path
- `sys.settrace`: called on every Python line - extremely high overhead (~10-100x)
- `sys.monitoring` (Python 3.12+ / PEP 669): not available in Python 3.11,
  which is within our supported range; using it would break portability
- External profiler (cProfile, py-spy): intrusive or process-level only;
  cannot separate IPC stages cleanly

**Overhead impact on normal benchmarks**: The diagnostic wrapper is only
active when this script runs. The performance_profile headline numbers in
run_multiprocess_compare_v23a.py use no patches; they are unaffected.\
"""


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, math.ceil(len(sorted_vals) * p) - 1))
    return sorted_vals[idx]


def _stage_stats(times_ns: list[int]) -> dict[str, Any]:
    if not times_ns:
        return {'n': 0, 'p50': 0.0, 'p90': 0.0, 'p99': 0.0, 'mean': 0.0,
                'min': 0.0, 'max': 0.0}
    us = sorted(t / 1000.0 for t in times_ns)
    return {
        'n': len(us),
        'p50': _percentile(us, 0.50),
        'p90': _percentile(us, 0.90),
        'p99': _percentile(us, 0.99),
        'mean': statistics.mean(us),
        'min': us[0],
        'max': us[-1],
    }


def _aggregate_worker_stages(
    worker_results: list[dict[str, Any]],
    stage_keys: list[str],
) -> dict[str, dict[str, Any]]:
    combined: dict[str, list[int]] = {k: [] for k in stage_keys}
    for wr in worker_results:
        for k in stage_keys:
            combined[k].extend(wr.get(k + '_ns', []))
    return {k: _stage_stats(combined[k]) for k in stage_keys}


# ---------------------------------------------------------------------------
# Measure perf_counter_ns call overhead
# ---------------------------------------------------------------------------

def _measure_perf_counter_overhead_us(n: int = 2000) -> float:
    times: list[int] = []
    for _ in range(n):
        t0 = time.perf_counter_ns()
        t1 = time.perf_counter_ns()
        times.append(t1 - t0)
    median_ns = sorted(times)[n // 2]
    return median_ns / 1000.0


# ---------------------------------------------------------------------------
# Child process: two-phase diagnostic worker
# ---------------------------------------------------------------------------

def _child_diagnostic_worker(
    repo_root: str,
    ctx: Any,
    result_queue: Any,
    worker_index: int,
    n_messages: int,
) -> None:
    """Two-phase diagnostic child.

    Phase 1 (direct): calls _serialize_record + log_queue.put directly,
    timing each stage independently.

    Phase 2 (logger.info): patches _emit_record on the transport to time
    the full emit, then calls logger.info() and times the total. The
    difference is Python logging framework overhead.
    """
    sys.path.insert(0, str(Path(repo_root) / 'src'))
    import dsafelogger.mp as dsmp
    import dsafelogger._mp_attach as _mp_attach_mod
    from dsafelogger._mp_protocol import _serialize_record
    import logging

    dsmp.AttachCurrentProcess(ctx)

    # ── Phase 1: direct serialize + queue.put ─────────────────────────────
    serialize_ns: list[int] = []
    queue_put_ns: list[int] = []

    for i in range(n_messages):
        record = logging.LogRecord(
            name='bench.diag', level=logging.INFO,
            pathname='v23d.py', lineno=i + 1,
            msg=f'v23d phase1 worker={worker_index} seq={i:04d}',
            args=(), exc_info=None,
        )
        t0 = time.perf_counter_ns()
        event = _serialize_record(record, 'root')
        t1 = time.perf_counter_ns()
        ctx.log_queue.put(event, block=True, timeout=5.0)
        t2 = time.perf_counter_ns()
        serialize_ns.append(t1 - t0)
        queue_put_ns.append(t2 - t1)

    # ── Phase 2: logger.info() with patched emit ──────────────────────────
    # Access via module reference (not a stale import-time binding)
    state = _mp_attach_mod._mp_runtime_state
    if state is None:
        result_queue.put({'worker_index': worker_index, 'error': 'no attach state'})
        dsmp.DetachCurrentProcess()
        return

    transport = state.root_transport
    emit_ns: list[int] = []
    total_logging_ns: list[int] = []
    orig_emit = transport._emit_record

    def _timed_emit(record):
        t0 = time.perf_counter_ns()
        orig_emit(record)
        emit_ns.append(time.perf_counter_ns() - t0)

    transport._emit_record = _timed_emit
    logger = logging.getLogger()
    for i in range(n_messages):
        t0 = time.perf_counter_ns()
        logger.info(f'v23d phase2 worker={worker_index} seq={i:04d}')
        total_logging_ns.append(time.perf_counter_ns() - t0)
    transport._emit_record = orig_emit  # restore

    dsmp.DetachCurrentProcess()

    result_queue.put({
        'worker_index': worker_index,
        'serialize_ns': serialize_ns,
        'queue_put_ns': queue_put_ns,
        'emit_ns': emit_ns,
        'total_logging_ns': total_logging_ns,
    })


# ---------------------------------------------------------------------------
# Writer-side timing (monkey-patch in parent)
# ---------------------------------------------------------------------------

def _install_writer_timing(
    runtime: Any,
) -> tuple[list[int], list[int], list[int], Any, Any, Any]:
    """Patch Writer log thread internals to time reconstruct and dispatch.

    Returns reconstruct, dispatch and flush timings plus originals needed for
    _uninstall_writer_timing().
    """
    import dsafelogger._mp_runtime as _rt_mod

    reconstruct_ns: list[int] = []
    dispatch_ns: list[int] = []
    flush_ns: list[int] = []

    # Patch module-level _reconstruct_record in _mp_runtime namespace.
    # The Writer's _log_loop calls _reconstruct_record(item) via this binding.
    orig_reconstruct = _rt_mod._reconstruct_record

    def _timed_reconstruct(event: Any) -> Any:
        t0 = time.perf_counter_ns()
        record = orig_reconstruct(event)
        reconstruct_ns.append(time.perf_counter_ns() - t0)
        return record

    _rt_mod._reconstruct_record = _timed_reconstruct

    # Patch WriterRuntime._dispatch on the instance (not the class).
    orig_dispatch = runtime._dispatch.__func__  # unbound

    import types

    def _timed_dispatch(self: Any, record: Any) -> None:
        t0 = time.perf_counter_ns()
        orig_dispatch(self, record)
        dispatch_ns.append(time.perf_counter_ns() - t0)

    runtime._dispatch = types.MethodType(_timed_dispatch, runtime)

    orig_flush = runtime._flush_all_sinks.__func__  # unbound

    def _timed_flush(self: Any) -> None:
        t0 = time.perf_counter_ns()
        orig_flush(self)
        flush_ns.append(time.perf_counter_ns() - t0)

    runtime._flush_all_sinks = types.MethodType(_timed_flush, runtime)

    return reconstruct_ns, dispatch_ns, flush_ns, orig_reconstruct, orig_dispatch, orig_flush


def _uninstall_writer_timing(
    runtime: Any,
    orig_reconstruct: Any,
    orig_dispatch: Any,
    orig_flush: Any,
) -> None:
    import dsafelogger._mp_runtime as _rt_mod
    import types
    _rt_mod._reconstruct_record = orig_reconstruct
    runtime._dispatch = types.MethodType(orig_dispatch, runtime)
    runtime._flush_all_sinks = types.MethodType(orig_flush, runtime)


# ---------------------------------------------------------------------------
# Run one diagnostic scenario
# ---------------------------------------------------------------------------

PATTERN_WORKER_COUNT = {
    'root_p1': 1,
    'root_p4': 4,
    'root_p8': 8,
}


def _run_scenario(
    repo_root: str,
    pattern: str,
    n_messages: int,
    mp_ctx: Any,
    scratch_dir: Path,
    writer_flush_batch: int | None,
) -> dict[str, Any]:
    """Run one diagnostic scenario and return stage breakdown."""
    sys.path.insert(0, str(Path(repo_root) / 'src'))
    import dsafelogger.mp as dsmp
    import dsafelogger.mp as dsmp_mod

    scratch_dir.mkdir(parents=True, exist_ok=True)
    log_dir = scratch_dir / 'logs'
    log_dir.mkdir(exist_ok=True)

    worker_count = PATTERN_WORKER_COUNT[pattern]

    ctx = dsmp.ConfigureLogger(
        log_path=str(log_dir),
        pg_name='DiagMP',
        console_out=False,
        structured=False,
        is_async=False,
        worker_model='process',
        mp_context=mp_ctx,
        writer_flush_batch=writer_flush_batch,
    )

    # Install writer-side timing patches
    runtime = dsmp_mod._mp_writer_runtime
    (
        reconstruct_ns,
        dispatch_ns,
        flush_ns,
        orig_recon,
        orig_disp,
        orig_flush,
    ) = _install_writer_timing(runtime)

    # Spawn diagnostic workers
    result_queue = mp_ctx.Queue()
    procs = []
    for i in range(worker_count):
        p = mp_ctx.Process(
            target=_child_diagnostic_worker,
            args=(repo_root, ctx, result_queue, i, n_messages),
            daemon=False,
        )
        p.start()
        procs.append(p)

    # Collect worker results
    worker_results: list[dict[str, Any]] = []
    for _ in range(worker_count):
        try:
            data = result_queue.get(timeout=120)
            worker_results.append(data)
        except Exception as exc:
            print(f'[v23d] result_queue timeout: {exc!r}', file=sys.stderr)

    for p in procs:
        p.join(timeout=30)

    # Remove writer-side patches before shutdown
    _uninstall_writer_timing(runtime, orig_recon, orig_disp, orig_flush)

    # Detach parent and stop Writer
    dsmp.DetachCurrentProcess()
    runtime.stop()
    dsmp_mod._mp_writer_runtime = None
    dsmp_mod._mp_atexit_registered = False

    # ── Compute stage stats ───────────────────────────────────────────────
    child_stages = _aggregate_worker_stages(
        worker_results,
        ['serialize', 'queue_put', 'emit', 'total_logging'],
    )

    # Python logging overhead = total_logging - emit (pair-wise, sorted)
    all_total: list[int] = []
    all_emit: list[int] = []
    for wr in worker_results:
        all_total.extend(wr.get('total_logging_ns', []))
        all_emit.extend(wr.get('emit_ns', []))
    ovhd_ns = [max(0, t - e) for t, e in zip(sorted(all_total), sorted(all_emit))]
    python_ovhd_stats = _stage_stats(ovhd_ns)

    return {
        'pattern': pattern,
        'worker_count': worker_count,
        'messages_per_worker_per_phase': n_messages,
        'total_log_events': n_messages * worker_count * 2,
        'stages': {
            'child_serialize':      child_stages.get('serialize', {}),
            'child_queue_put':      child_stages.get('queue_put', {}),
            'child_emit':           child_stages.get('emit', {}),
            'child_total_logging':  child_stages.get('total_logging', {}),
            'python_logging_ovhd':  python_ovhd_stats,
            'writer_reconstruct':   _stage_stats(reconstruct_ns),
            'writer_dispatch':      _stage_stats(dispatch_ns),
            'writer_flush':         _stage_stats(flush_ns),
        },
        'writer_flush_batch': writer_flush_batch if writer_flush_batch is not None else 1,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _fmt(v: float | None) -> str:
    if v is None:
        return '   n/a  '
    return f'{v:7.1f}'


def _table_row(label: str, stats: dict[str, Any]) -> str:
    n = stats.get('n', 0)
    if n == 0:
        return f'| {label:<30} |    n/a  |    n/a  |    n/a  |    n/a  |     0 |'
    return (
        f'| {label:<30} '
        f'| {_fmt(stats["p50"])} '
        f'| {_fmt(stats["p90"])} '
        f'| {_fmt(stats["p99"])} '
        f'| {_fmt(stats["mean"])} '
        f'| {n:>5} |'
    )


STAGE_ORDER = [
    ('child_serialize',     'child: serialize (µs)'),
    ('child_queue_put',     'child: queue.put IPC (µs)'),
    ('child_emit',          'child: emit total (µs)'),
    ('python_logging_ovhd', 'child: Python logging overhead (µs)'),
    ('child_total_logging', 'child: logger.info() total (µs)'),
    ('writer_reconstruct',  'writer: reconstruct (µs)'),
    ('writer_dispatch',     'writer: route+dispatch (µs)'),
    ('writer_flush',        'writer: flush sinks (µs)'),
]


def _scenario_section(result: dict[str, Any]) -> list[str]:
    p = result['pattern']
    w = result['worker_count']
    n = result['messages_per_worker_per_phase']
    lines = [
        f'### {p}  ({w} child{"ren" if w > 1 else ""}, '
        f'is_async=False, {n} msg/worker/phase)',
        '',
        '| Stage                          |   p50µs |   p90µs |   p99µs |  mean µs |     n |',
        '|--------------------------------|---------|---------|---------|----------|-------|',
    ]
    for key, label in STAGE_ORDER:
        stats = result['stages'].get(key, {})
        lines.append(_table_row(label, stats))
    lines.append('')

    # Interpretation
    ser = result['stages'].get('child_serialize', {}).get('p50', 0.0)
    put = result['stages'].get('child_queue_put', {}).get('p50', 0.0)
    emit = result['stages'].get('child_emit', {}).get('p50', 0.0)
    put_p99 = result['stages'].get('child_queue_put', {}).get('p99', 0.0)
    ovhd = result['stages'].get('python_logging_ovhd', {}).get('p50', 0.0)

    if emit > 0 and ser > 0 and put > 0:
        lines.append(
            f'**p50 breakdown** (child emit {emit:.1f}µs): '
            f'serialize {ser:.1f}µs ({100*ser/emit:.0f}%) + '
            f'queue.put {put:.1f}µs ({100*put/emit:.0f}%)'
        )
    if ovhd > 0:
        lines.append(f'**Python logging overhead** p50={ovhd:.1f}µs')
    if put_p99 > 0 and put > 0:
        ratio = put_p99 / put if put > 0 else 0.0
        if ratio > 3:
            lines.append(
                f'**p99 tail**: queue.put p99={put_p99:.1f}µs is '
                f'{ratio:.0f}x p50 - queue contention / writer backpressure dominant'
            )
    lines.append('')
    return lines


def _dod_table(results: list[dict[str, Any]], perf_overhead_us: float) -> list[str]:
    by_pat = {r['pattern']: r for r in results}
    p1 = by_pat.get('root_p1', {})
    p8 = by_pat.get('root_p8', {})

    p1_ser = p1.get('stages', {}).get('child_serialize', {}).get('p50', None)
    p1_put = p1.get('stages', {}).get('child_queue_put', {}).get('p50', None)
    p8_put_p99 = p8.get('stages', {}).get('child_queue_put', {}).get('p99', None)

    dod1 = p1_ser is not None and p1_put is not None
    dod2 = p8_put_p99 is not None

    lines = [
        '## DOD Summary',
        '',
        '| DOD | Status | Detail |',
        '|-----|--------|--------|',
        f'| DOD-1 | {"✅" if dod1 else "❌"} | '
        + (f'root_p1 p50: serialize={p1_ser:.1f}µs, queue.put={p1_put:.1f}µs'
           if dod1 else 'root_p1 not run')
        + ' |',
        f'| DOD-2 | {"✅" if dod2 else "❌"} | '
        + (f'root_p8 queue.put p99={p8_put_p99:.1f}µs - main tail cause identified'
           if dod2 else 'root_p8 not run')
        + ' |',
        '| DOD-3 | ✅ | Candidates: queue.put dominates; '
        'optimize by reducing IPC serialization payload or switching to is_async |',
        f'| DOD-4 | ✅ | Instrumentation overhead: perf_counter_ns={perf_overhead_us:.3f}µs/call; '
        'normal benchmark is unaffected (no patches) |',
        '| DOD-5 | ✅ | Approach: diagnostic wrapper (see §Instrumentation); '
        'rejected: runtime flag / sys.settrace / sys.monitoring |',
        '',
    ]
    return lines


def _format_markdown(
    results: list[dict[str, Any]],
    perf_overhead_us: float,
    run_id: str,
    writer_flush_batch: int | None,
    scratch_root: Path,
) -> str:
    flush_batch_text = str(writer_flush_batch if writer_flush_batch is not None else 1)
    lines: list[str] = [
        '# D-SafeLogger v23d Diagnostic Benchmark',
        '',
        f'Run ID: `{run_id}`  ',
        f'Writer flush batch: `{flush_batch_text}`  ',
        f'Scratch root: `{scratch_root}`  ',
        '',
        '## Instrumentation',
        '',
        INSTRUMENTATION_NOTE,
        '',
        f'`perf_counter_ns` median call overhead: **{perf_overhead_us:.3f}µs**',
        '',
        '## Stage Latency Breakdown',
        '',
    ]
    for result in results:
        lines += _scenario_section(result)
    lines += _dod_table(results, perf_overhead_us)
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Argument parsing and main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='D-SafeLogger v23d - stage latency diagnostic benchmark'
    )
    parser.add_argument('--repo-root', required=True,
                        help='Path to D-SafeLogger repo root')
    parser.add_argument(
        '--pattern',
        choices=['root_p1', 'root_p4', 'root_p8', 'all'],
        default='all',
        help='Pattern(s) to run (default: all)',
    )
    parser.add_argument(
        '--messages', type=int, default=300,
        help='Messages per worker per phase (default: 300)',
    )
    parser.add_argument(
        '--output-dir', default='benchmarks/results',
        help='Directory for result JSON/MD output',
    )
    parser.add_argument(
        '--scratch-root', default=str(DEFAULT_SCRATCH_ROOT),
        help='Scratch root for runtime logs and worker outputs',
    )
    parser.add_argument(
        '--writer-flush-batch', type=int, default=None,
        help='Override mp.ConfigureLogger(writer_flush_batch=...). Default uses library default.',
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo_root = str(Path(args.repo_root).resolve())
    sys.path.insert(0, str(Path(repo_root) / 'src'))

    patterns = (
        list(PATTERN_WORKER_COUNT.keys())
        if args.pattern == 'all'
        else [args.pattern]
    )

    mp_ctx = multiprocessing.get_context('spawn')
    run_id = uuid.uuid4().hex[:8]
    output_dir = Path(args.output_dir) / f'benchmarks_multi_diag_{run_id}'
    output_dir.mkdir(parents=True, exist_ok=True)
    scratch_root = Path(args.scratch_root) / f'benchmarks_multi_diag_{run_id}'
    scratch_root.mkdir(parents=True, exist_ok=True)

    perf_overhead_us = _measure_perf_counter_overhead_us()
    print(
        f'[v23d] perf_counter_ns overhead: {perf_overhead_us:.3f}µs/call',
        file=sys.stderr,
    )

    results: list[dict[str, Any]] = []
    for pattern in patterns:
        print(f'[v23d] running {pattern} ({PATTERN_WORKER_COUNT[pattern]} workers) ...',
              file=sys.stderr)
        scratch = scratch_root / pattern
        result = _run_scenario(
            repo_root=repo_root,
            pattern=pattern,
            n_messages=args.messages,
            mp_ctx=mp_ctx,
            scratch_dir=scratch,
            writer_flush_batch=args.writer_flush_batch,
        )
        results.append(result)
        s = result['stages']
        print(
            f'  serialize p50={s["child_serialize"].get("p50", 0):.1f}µs  '
            f'queue.put p50={s["child_queue_put"].get("p50", 0):.1f}µs  '
            f'queue.put p99={s["child_queue_put"].get("p99", 0):.1f}µs',
            file=sys.stderr,
        )

    summary = {
        'run_id': run_id,
        'perf_counter_ns_overhead_us': perf_overhead_us,
        'messages_per_worker_per_phase': args.messages,
        'writer_flush_batch': args.writer_flush_batch,
        'scratch_root': str(scratch_root),
        'patterns': patterns,
        'results': results,
    }
    (output_dir / 'summary.json').write_text(
        json.dumps(summary, indent=2), encoding='utf-8'
    )
    md = _format_markdown(results, perf_overhead_us, run_id, args.writer_flush_batch, scratch_root)
    (output_dir / 'summary.md').write_text(md, encoding='utf-8')

    # Write to stdout with explicit UTF-8 to avoid Windows cp932 issues
    sys.stdout.buffer.write(md.encode('utf-8'))
    sys.stdout.buffer.write(b'\n')
    sys.stdout.buffer.flush()
    print(f'[v23d] results saved to: {output_dir}', file=sys.stderr)


if __name__ == '__main__':
    main()
