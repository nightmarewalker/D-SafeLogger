"""Multiprocess comparison benchmark runner — v23a.

Maintained multiprocess comparison benchmark with sequence-completeness
verification, benchmark profiles, run_id / repeat_index tracking, and
environment recording.

Changes from v22i benchmark:
  - Every log message embeds a machine-readable marker:
      DSL_BENCH run_id=<id> repeat=<n> worker=<w> seq=<s> msg_index=<m>
  - After each run the log files are parsed to detect:
      missing IDs, duplicate IDs, JSON parse failures, route mismatches
  - Benchmark profiles (input-config-declared, not post-hoc):
      integrity_profile  – queue ≥ 2× messages; missing/dup are integrity failures
      performance_profile – default queue; headline throughput/latency
      overload_profile   – intentionally small queue; verifies shedding policy
      resilience_profile – operational failure-mode observability comparison
  - run_id (8-char hex) + repeat_index are part of logical_message_id
  - Summary includes environment snapshot

v23g note: D-SafeLogger default log queue maxsize is 10000. The runner still
sets explicit queue sizes for integrity/overload profiles so profile semantics
do not silently change when production defaults change.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import multiprocessing as mp
import os
import platform
import re
import secrets
import statistics
import subprocess
import sys
import sysconfig
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))



# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PYTHON_313 = r"C:\Python\313\python3.13t.exe"
DEFAULT_PYTHON_314 = r"C:\Python\314\python3.14t.exe"
DEFAULT_SCRATCH_ROOT = Path(r"C:\TempX\D-SafeLogger-bench")
DEFAULT_MESSAGES = 5_000
DEFAULT_MESSAGES_INTEGRITY = 500
DEFAULT_REPEAT = 3               # v23a: repeat >= 3 for integrity
DEFAULT_TIMEOUT_SEC = 120
GIL_ENV_MAP = {"enabled": "1", "disabled": "0"}
BACKENDS = ["D-SafeLogger", "stdlib logging", "loguru"]
SCENARIOS = ["text", "json"]

PROFILES = ["integrity_profile", "performance_profile", "overload_profile", "resilience_profile"]
RESILIENCE_SCENARIOS = [
    "rolling_restart_mixed_shutdown",
    "burst_backpressure",
    "sink_temporarily_unavailable",
    "ipc_forced_disconnect",
]
# For overload_profile: force messages >> queue to trigger D-SafeLogger drops.
OVERLOAD_QUEUE_DIVISOR = 6
OVERLOAD_QUEUE_MAXSIZE = 1000

_BENCH_MARKER_RE = re.compile(
    r"DSL_BENCH run_id=(?P<run_id>[0-9a-f]+)"
    r" repeat=(?P<repeat>\d+)"
    r" worker=(?P<worker>\d+)"
    r" seq=(?P<seq>\d+)"
    r" msg_index=(?P<msg_index>\d+)"
)


# ---------------------------------------------------------------------------
# Pattern specs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatternSpec:
    name: str
    process_count: int
    module_route: bool
    description: str


PATTERNS = [
    PatternSpec(
        "root_p1", 1, False,
        "1 child -> root sink. Multiprocess IPC baseline without fan-in contention.",
    ),
    PatternSpec(
        "root_p4", 4, False,
        "4 children -> shared root sink. Moderate fan-in onto one parent writer.",
    ),
    PatternSpec(
        "root_p8", 8, False,
        "8 children -> shared root sink. High fan-in stress case for single-writer scaling.",
    ),
    PatternSpec(
        "module_p4", 4, True,
        "4 children -> module-specific route (bench.module) and dedicated module sink.",
    ),
]
PATTERN_MAP = {p.name: p for p in PATTERNS}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class IntegrityReport:
    profile: str
    run_id: str
    repeat_index: int
    backend: str
    python_label: str
    gil_label: str
    pattern: str
    scenario: str
    expected_count: int
    observed_count: int
    missing_count: int
    duplicate_count: int
    json_parse_failure_count: int
    route_mismatch_count: int
    missing_ids: list[str]        # first 50 missing (worker=W seq=S)
    duplicate_ids: list[str]      # first 50 duplicates
    is_integrity_failure: bool
    failure_reasons: list[str]


@dataclass
class ResilienceReport:
    scenario: str
    attempted_count: int
    accepted_count: int | None
    delivered_count: int
    known_rejected_count: int | None
    known_dropped_count: int | None
    unexplained_lost_count: int | None
    shutdown_result: str
    observability_fields_available: list[str]
    worker_exit_summary: dict[str, int] = field(default_factory=dict)
    writer_status: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawRunRecord:
    python_label: str
    gil_label: str
    python_version: str
    runtime_gil: str
    backend: str
    scenario: str
    pattern: str
    process_count: int
    module_route: bool
    messages: int
    run_index: int
    status: str
    run_id: str = ""
    repeat_index: int = 0
    profile: str = "performance_profile"
    is_async: bool = False
    throughput: int | None = None
    p50_us: float | None = None
    p90_us: float | None = None
    p99_us: float | None = None
    delivered_lines: int | None = None
    integrity: IntegrityReport | None = None
    resilience: ResilienceReport | None = None
    note: str | None = None


@dataclass
class SummaryRow:
    python_label: str
    gil_label: str
    python_version: str
    runtime_gil: str
    backend: str
    scenario: str
    pattern: str
    process_count: int
    module_route: bool
    messages: int
    profile: str
    status: str
    successful_runs: int
    total_runs: int
    is_async: bool = False
    throughput_avg: int | None = None
    throughput_min: int | None = None
    throughput_max: int | None = None
    p50_us: float | None = None
    p90_us: float | None = None
    p99_us: float | None = None
    delivered_lines: int | None = None
    integrity_failures: int = 0   # runs with is_integrity_failure=True
    resilience_scenario: str = ""
    attempted_count: int | None = None
    accepted_count: int | None = None
    known_rejected_count: int | None = None
    known_dropped_count: int | None = None
    unexplained_lost_count: int | None = None
    shutdown_result: str = ""
    note: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _generate_run_id() -> str:
    return secrets.token_hex(4)  # 8-char hex


def _bench_marker(run_id: str, repeat_index: int, worker_index: int, seq: int, msg_index: int) -> str:
    return (
        f"DSL_BENCH run_id={run_id} repeat={repeat_index}"
        f" worker={worker_index} seq={seq} msg_index={msg_index}"
    )


def _runtime_gil_text() -> str:
    fn = getattr(sys, "_is_gil_enabled", None)
    if callable(fn):
        try:
            return "enabled" if fn() else "disabled"
        except Exception:
            return "unknown"
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        return "unknown"
    return "enabled"


def _percentile_value(sorted_latencies: list[float], fraction: float) -> float:
    rank = max(1, math.ceil(len(sorted_latencies) * fraction))
    return sorted_latencies[rank - 1]


def _compute_metrics(latencies: list[float], elapsed_sec: float) -> dict[str, float]:
    sorted_latencies = sorted(latencies)
    return {
        "throughput": len(latencies) / elapsed_sec,
        "p50_us": statistics.median(sorted_latencies) * 1e6,
        "p90_us": _percentile_value(sorted_latencies, 0.90) * 1e6,
        "p99_us": _percentile_value(sorted_latencies, 0.99) * 1e6,
    }


def _split_message_ranges(total_messages: int, process_count: int) -> list[tuple[int, int]]:
    base_count = total_messages // process_count
    extra_count = total_messages % process_count
    ranges: list[tuple[int, int]] = []
    start_index = 0
    for process_index in range(process_count):
        count = base_count + (1 if process_index < extra_count else 0)
        ranges.append((start_index, count))
        start_index += count
    return ranges


def _count_log_lines(log_root: Path) -> int:
    total = 0
    for path in log_root.rglob("*.log"):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            total += sum(1 for _ in handle)
    return total


def _event_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def _event_from_stdlib_record(record: logging.LogRecord, route: str) -> dict[str, Any]:
    return {
        "timestamp": _event_timestamp(),
        "level": record.levelname,
        "logger": record.name,
        "file": record.filename,
        "line": record.lineno,
        "function": record.funcName,
        "message": record.getMessage(),
        "route": route,
    }


def _text_line(event: dict[str, Any]) -> str:
    return (
        f"{event['timestamp']} [{event['level']}][{event['file']}:{event['line']}:{event['function']}] "
        f"{event['message']}"
    )


def _json_line(event: dict[str, Any]) -> str:
    payload = {
        "timestamp": event["timestamp"],
        "level": event["level"],
        "logger": event["logger"],
        "file": event["file"],
        "line": event["line"],
        "function": event["function"],
        "message": event["message"],
    }
    return json.dumps(payload, ensure_ascii=False)


def _collect_environment(
    *,
    python_label: str,
    gil_label: str,
    messages: int,
    repeat: int,
    profile: str,
    patterns: list[str],
    scenarios: list[str],
    backends: list[str],
    scratch_root: Path,
) -> dict[str, Any]:
    cpu_count = os.cpu_count()
    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
            "runtime_gil": _runtime_gil_text(),
        },
        "cpu": {
            "processor": platform.processor() or "unknown",
            "count_logical": cpu_count,
        },
        "scratch_root": str(scratch_root),
        "benchmark_config": {
            "messages": messages,
            "repeat": repeat,
            "profile": profile,
            "patterns": patterns,
            "scenarios": scenarios,
            "backends": backends,
            "python_label": python_label,
            "gil_label": gil_label,
        },
    }


# ---------------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------------

def _extract_marker_from_line(line: str, *, is_json: bool) -> re.Match[str] | None:
    """Extract DSL_BENCH marker from a log line (text or JSON)."""
    text = line
    if is_json:
        try:
            obj = json.loads(line)
            # Search all string values for the marker
            for v in obj.values():
                if isinstance(v, str):
                    m = _BENCH_MARKER_RE.search(v)
                    if m is not None:
                        return m
            return None
        except json.JSONDecodeError:
            return None
    return _BENCH_MARKER_RE.search(text)


def _verify_integrity(
    *,
    log_root: Path,
    run_id: str,
    repeat_index: int,
    pattern: PatternSpec,
    scenario: str,
    backend: str,
    python_label: str,
    gil_label: str,
    messages: int,
    profile: str,
) -> IntegrityReport:
    is_json = scenario == "json"
    ranges = _split_message_ranges(messages, pattern.process_count)

    # Build expected set: {(worker_index, seq)}
    expected: set[tuple[int, int]] = set()
    for worker_index, (_, count) in enumerate(ranges):
        for seq in range(count):
            expected.add((worker_index, seq))

    observed: dict[tuple[int, int], int] = {}
    json_parse_failures = 0
    route_mismatches = 0

    for log_file in sorted(log_root.rglob("*.log")):
        is_module_file = log_file.name == "bench_module.log"
        with log_file.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.rstrip("\n")
                if not line:
                    continue

                if is_json:
                    try:
                        obj = json.loads(line)
                        text_for_marker = None
                        for v in obj.values():
                            if isinstance(v, str) and "DSL_BENCH" in v:
                                text_for_marker = v
                                break
                    except json.JSONDecodeError:
                        json_parse_failures += 1
                        continue
                    m = _BENCH_MARKER_RE.search(text_for_marker) if text_for_marker else None
                else:
                    m = _BENCH_MARKER_RE.search(line)

                if m is None:
                    continue

                if m.group("run_id") != run_id or int(m.group("repeat")) != repeat_index:
                    continue

                worker = int(m.group("worker"))
                seq = int(m.group("seq"))
                key = (worker, seq)
                observed[key] = observed.get(key, 0) + 1

                # Route check: module_route patterns → all messages go to bench_module.log
                if pattern.module_route and not is_module_file:
                    route_mismatches += 1

    observed_set = set(observed.keys())
    missing_set = expected - observed_set
    duplicate_keys = {k for k, v in observed.items() if v > 1}

    missing_ids = [
        f"worker={w} seq={s}" for w, s in sorted(missing_set)
    ][:50]
    duplicate_ids = [
        f"worker={w} seq={s} (count={observed[(w, s)]})"
        for w, s in sorted(duplicate_keys)
    ][:50]

    is_failure = False
    failure_reasons: list[str] = []

    if profile == "integrity_profile":
        if missing_set:
            is_failure = True
            failure_reasons.append(f"missing={len(missing_set)}")
        if duplicate_keys:
            is_failure = True
            failure_reasons.append(f"duplicates={len(duplicate_keys)}")
        if json_parse_failures > 0:
            is_failure = True
            failure_reasons.append(f"json_parse_failures={json_parse_failures}")
        if route_mismatches > 0:
            is_failure = True
            failure_reasons.append(f"route_mismatches={route_mismatches}")
    # performance_profile / overload_profile: record but do not fail

    return IntegrityReport(
        profile=profile,
        run_id=run_id,
        repeat_index=repeat_index,
        backend=backend,
        python_label=python_label,
        gil_label=gil_label,
        pattern=pattern.name,
        scenario=scenario,
        expected_count=len(expected),
        observed_count=len(observed_set),
        missing_count=len(missing_set),
        duplicate_count=len(duplicate_keys),
        json_parse_failure_count=json_parse_failures,
        route_mismatch_count=route_mismatches,
        missing_ids=missing_ids,
        duplicate_ids=duplicate_ids,
        is_integrity_failure=is_failure,
        failure_reasons=failure_reasons,
    )


# ---------------------------------------------------------------------------
# Event aggregator (for stdlib / loguru)
# ---------------------------------------------------------------------------

class EventAggregator:
    def __init__(self, queue_obj: Any, log_root: Path, *, structured: bool, module_route: bool):
        self._queue = queue_obj
        self._structured = structured
        self._root_path = log_root / "bench_root.log"
        self._module_path = log_root / "bench_module.log"
        self._module_route = module_route
        self._root_handle = self._root_path.open("w", encoding="utf-8", buffering=1)
        self._module_handle = (
            self._module_path.open("w", encoding="utf-8", buffering=1) if module_route else None
        )
        self._thread = threading.Thread(target=self._run, name="mp-aggregator", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _write_event(self, event: dict[str, Any]) -> None:
        line = _json_line(event) if self._structured else _text_line(event)
        handle = self._root_handle
        if (
            self._module_route
            and event.get("route") == "bench.module"
            and self._module_handle is not None
        ):
            handle = self._module_handle
        handle.write(line + "\n")
        handle.flush()

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                break
            self._write_event(event)

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join()
        self._root_handle.close()
        if self._module_handle is not None:
            self._module_handle.close()


# ---------------------------------------------------------------------------
# Child worker functions (v23a: embed bench marker in every message)
# ---------------------------------------------------------------------------

def _module_config(log_root: Path) -> dict[str, dict[str, str]]:
    return {
        "dsafelogger:bench.module": {
            "level": "INFO",
            "path": str(log_root / "bench_module.log"),
        }
    }


def _child_dsafelogger_v23a(
    *,
    repo_root: str,
    bootstrap_ctx: Any,
    start_event: Any,
    result_path: str,
    run_id: str,
    repeat_index: int,
    worker_index: int,
    start_index: int,
    count: int,
    module_route: bool,
) -> None:
    sys.path.insert(0, str(Path(repo_root) / "src"))
    import dsafelogger.mp as dsmp

    logger_name = "bench.module" if module_route else "bench"
    dsmp.AttachCurrentProcess(bootstrap_ctx)
    logger = dsmp.GetLogger(logger_name)
    latencies: list[float] = []
    start_event.wait()
    for seq in range(count):
        msg_index = start_index + seq
        msg = _bench_marker(run_id, repeat_index, worker_index, seq, msg_index)
        started = time.perf_counter()
        logger.info(msg)
        latencies.append(time.perf_counter() - started)
    Path(result_path).write_text(json.dumps(latencies), encoding="utf-8")
    dsmp.DetachCurrentProcess()


class StdlibMPHandler(logging.Handler):
    def __init__(self, queue_obj: Any, route: str):
        super().__init__()
        self._queue = queue_obj
        self._route = route

    def emit(self, record: logging.LogRecord) -> None:
        self._queue.put(_event_from_stdlib_record(record, self._route))


def _child_stdlib_v23a(
    *,
    queue_obj: Any,
    start_event: Any,
    result_path: str,
    run_id: str,
    repeat_index: int,
    worker_index: int,
    start_index: int,
    count: int,
    module_route: bool,
) -> None:
    logger_name = "bench.module" if module_route else "bench"
    route = "bench.module" if module_route else "root"
    bench_logger = logging.getLogger(f"mp_bench_{logger_name}_{os.getpid()}")
    bench_logger.handlers.clear()
    bench_logger.propagate = False
    bench_logger.setLevel(logging.INFO)
    handler = StdlibMPHandler(queue_obj, route)
    bench_logger.addHandler(handler)
    latencies: list[float] = []
    start_event.wait()
    for seq in range(count):
        msg_index = start_index + seq
        msg = _bench_marker(run_id, repeat_index, worker_index, seq, msg_index)
        started = time.perf_counter()
        bench_logger.info(msg)
        latencies.append(time.perf_counter() - started)
    Path(result_path).write_text(json.dumps(latencies), encoding="utf-8")
    bench_logger.handlers.clear()


def _child_loguru_v23a(
    *,
    queue_obj: Any,
    start_event: Any,
    result_path: str,
    run_id: str,
    repeat_index: int,
    worker_index: int,
    start_index: int,
    count: int,
    module_route: bool,
) -> None:
    from loguru import logger

    logger.remove()
    route = "bench.module" if module_route else "root"
    logger_name = "bench.module" if module_route else "bench"

    def sink(message: Any) -> None:
        record = message.record
        queue_obj.put(
            {
                "timestamp": record["time"].strftime("%Y-%m-%d %H:%M:%S.")
                    + f"{record['time'].microsecond // 1000:03d}",
                "level": record["level"].name,
                "logger": logger_name,
                "file": record["file"].name,
                "line": record["line"],
                "function": record["function"],
                "message": record["message"],
                "route": route,
            }
        )

    logger.add(sink, catch=False, level="INFO")
    bound_logger = logger.bind(route=route)
    latencies: list[float] = []
    start_event.wait()
    for seq in range(count):
        msg_index = start_index + seq
        msg = _bench_marker(run_id, repeat_index, worker_index, seq, msg_index)
        started = time.perf_counter()
        bound_logger.info(msg)
        latencies.append(time.perf_counter() - started)
    Path(result_path).write_text(json.dumps(latencies), encoding="utf-8")
    logger.remove()


# ---------------------------------------------------------------------------
# Resilience workers
# ---------------------------------------------------------------------------

def _write_worker_result(path: str, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload), encoding="utf-8")


def _resilience_exit_mode(worker_index: int, scenario: str) -> str:
    if scenario == "rolling_restart_mixed_shutdown":
        return ["normal", "normal", "os_exit", "terminate"][worker_index % 4]
    return "normal"


def _child_dsafelogger_resilience(
    *,
    repo_root: str,
    bootstrap_ctx: Any,
    start_event: Any,
    result_path: str,
    run_id: str,
    repeat_index: int,
    worker_index: int,
    count: int,
    scenario_name: str,
    module_route: bool,
) -> None:
    sys.path.insert(0, str(Path(repo_root) / "src"))
    import dsafelogger.mp as dsmp
    import dsafelogger._mp_attach as _mp_attach_mod

    exit_mode = _resilience_exit_mode(worker_index, scenario_name)
    logger_name = "bench.module" if module_route else "bench"
    attempted = 0
    accepted = 0
    timeout_drop = 0
    overload_shed = 0
    fallback_warning_injected = False
    start_event.wait()
    dsmp.AttachCurrentProcess(bootstrap_ctx)
    try:
        if scenario_name == "ipc_forced_disconnect":
            state = _mp_attach_mod._mp_runtime_state
            if state is not None:
                object.__setattr__(state.root_transport._ctx, "runtime_warning_queue", None)
                state.root_transport._emit_runtime_warning(
                    event="transport_closed_drop",
                    classification="KnownDropped",
                    reason="benchmark forced warning IPC disconnect",
                    context={"worker_index": worker_index, "scenario": scenario_name},
                )
                fallback_warning_injected = True
        logger = dsmp.GetLogger(logger_name)
        limit = count // 2 if exit_mode == "os_exit" else count
        for seq in range(limit):
            msg = _bench_marker(run_id, repeat_index, worker_index, seq, seq)
            logger.info("%s scenario=%s", msg, scenario_name)
            attempted += 1
            accepted += 1
            if attempted % 10 == 0:
                _write_worker_result(result_path, {
                    "worker_index": worker_index,
                    "exit_mode": exit_mode,
                    "attempted": attempted,
                    "accepted": accepted,
                })
            if scenario_name == "rolling_restart_mixed_shutdown":
                time.sleep(0.001)
        state = _mp_attach_mod._mp_runtime_state
        if state is not None:
            transport = state.root_transport
            timeout_drop = int(getattr(transport, "_timeout_drop", 0))
            overload_shed = int(getattr(transport, "_overload_shed", 0))
        _write_worker_result(result_path, {
            "worker_index": worker_index,
            "exit_mode": exit_mode,
            "attempted": attempted,
            "accepted": accepted,
            "timeout_drop": timeout_drop,
            "overload_shed": overload_shed,
            "fallback_warning_injected": fallback_warning_injected,
        })
        if exit_mode == "os_exit":
            os._exit(2)
    finally:
        if exit_mode == "normal":
            dsmp.DetachCurrentProcess()


def _child_stdlib_resilience(
    *,
    queue_obj: Any,
    start_event: Any,
    result_path: str,
    run_id: str,
    repeat_index: int,
    worker_index: int,
    count: int,
    scenario_name: str,
    module_route: bool,
) -> None:
    exit_mode = _resilience_exit_mode(worker_index, scenario_name)
    logger_name = "bench.module" if module_route else "bench"
    route = "bench.module" if module_route else "root"
    bench_logger = logging.getLogger(f"resilience_stdlib_{logger_name}_{os.getpid()}")
    bench_logger.handlers.clear()
    bench_logger.propagate = False
    bench_logger.setLevel(logging.INFO)
    bench_logger.addHandler(StdlibMPHandler(queue_obj, route))
    attempted = 0
    accepted = 0
    start_event.wait()
    limit = count // 2 if exit_mode == "os_exit" else count
    for seq in range(limit):
        msg = _bench_marker(run_id, repeat_index, worker_index, seq, seq)
        bench_logger.info("%s scenario=%s", msg, scenario_name)
        attempted += 1
        accepted += 1
        if attempted % 10 == 0:
            _write_worker_result(result_path, {
                "worker_index": worker_index,
                "exit_mode": exit_mode,
                "attempted": attempted,
                "accepted": accepted,
            })
        if scenario_name == "rolling_restart_mixed_shutdown":
            time.sleep(0.001)
    _write_worker_result(result_path, {
        "worker_index": worker_index,
        "exit_mode": exit_mode,
        "attempted": attempted,
        "accepted": accepted,
    })
    if exit_mode == "os_exit":
        os._exit(2)


def _child_loguru_resilience(
    *,
    queue_obj: Any,
    start_event: Any,
    result_path: str,
    run_id: str,
    repeat_index: int,
    worker_index: int,
    count: int,
    scenario_name: str,
    module_route: bool,
) -> None:
    from loguru import logger

    exit_mode = _resilience_exit_mode(worker_index, scenario_name)
    logger.remove()
    route = "bench.module" if module_route else "root"
    logger_name = "bench.module" if module_route else "bench"

    def sink(message: Any) -> None:
        record = message.record
        queue_obj.put({
            "timestamp": record["time"].strftime("%Y-%m-%d %H:%M:%S.") + f"{record['time'].microsecond // 1000:03d}",
            "level": record["level"].name,
            "logger": logger_name,
            "file": record["file"].name,
            "line": record["line"],
            "function": record["function"],
            "message": record["message"],
            "route": route,
        })

    logger.add(sink, catch=False, level="INFO")
    attempted = 0
    accepted = 0
    start_event.wait()
    limit = count // 2 if exit_mode == "os_exit" else count
    for seq in range(limit):
        msg = _bench_marker(run_id, repeat_index, worker_index, seq, seq)
        logger.info("{} scenario={}", msg, scenario_name)
        attempted += 1
        accepted += 1
        if attempted % 10 == 0:
            _write_worker_result(result_path, {
                "worker_index": worker_index,
                "exit_mode": exit_mode,
                "attempted": attempted,
                "accepted": accepted,
            })
        if scenario_name == "rolling_restart_mixed_shutdown":
            time.sleep(0.001)
    _write_worker_result(result_path, {
        "worker_index": worker_index,
        "exit_mode": exit_mode,
        "attempted": attempted,
        "accepted": accepted,
    })
    if exit_mode == "os_exit":
        os._exit(2)
    logger.remove()


class FailingRequiredHandler(logging.Handler):
    _ds_required = True

    def emit(self, record: logging.LogRecord) -> None:
        raise OSError("simulated temporary sink outage")


class ResilienceAggregator(EventAggregator):
    def __init__(self, queue_obj: Any, log_root: Path, *, structured: bool, module_route: bool, fail_required: bool):
        super().__init__(queue_obj, log_root, structured=structured, module_route=module_route)
        self._fail_required = fail_required
        self.failure_count = 0

    def _write_event(self, event: dict[str, Any]) -> None:
        if self._fail_required:
            self.failure_count += 1
            return
        super()._write_event(event)


# ---------------------------------------------------------------------------
# Run children
# ---------------------------------------------------------------------------

def _run_children_v23a(
    *,
    ctx: Any,
    child_target: Any,
    repo_root: Path | None,
    queue_obj: Any,
    scratch_dir: Path,
    log_root: Path,
    structured: bool,
    pattern: PatternSpec,
    messages: int,
    timeout: int,
    run_id: str,
    repeat_index: int,
) -> tuple[list[float], float]:
    result_paths: list[Path] = []
    processes: list[Any] = []
    start_event = ctx.Event()
    ranges = _split_message_ranges(messages, pattern.process_count)

    for worker_index, (start_index, count) in enumerate(ranges):
        result_path = scratch_dir / f"latencies_{worker_index:02d}.json"
        result_paths.append(result_path)
        common = {
            "start_event": start_event,
            "result_path": str(result_path),
            "run_id": run_id,
            "repeat_index": repeat_index,
            "worker_index": worker_index,
            "start_index": start_index,
            "count": count,
            "module_route": pattern.module_route,
        }
        if child_target is _child_dsafelogger_v23a:
            kwargs = {
                "repo_root": str(repo_root),
                "bootstrap_ctx": queue_obj,
                **common,
            }
        else:
            kwargs = {"queue_obj": queue_obj, **common}

        process = ctx.Process(target=child_target, kwargs=kwargs)
        process.start()
        processes.append(process)

    started_at = time.perf_counter()
    start_event.set()
    for process in processes:
        process.join(timeout)
        if process.is_alive():
            process.kill()
            raise RuntimeError(f"child process timeout: pid={process.pid}")
        if process.exitcode != 0:
            raise RuntimeError(
                f"child process failed: pid={process.pid}, exit={process.exitcode}"
            )

    latencies: list[float] = []
    for result_path in result_paths:
        latencies.extend(json.loads(result_path.read_text(encoding="utf-8")))
    return latencies, time.perf_counter() - started_at


def _run_resilience_children(
    *,
    ctx: Any,
    child_target: Any,
    repo_root: Path | None,
    queue_obj: Any,
    scratch_dir: Path,
    pattern: PatternSpec,
    messages: int,
    timeout: int,
    run_id: str,
    repeat_index: int,
    resilience_scenario: str,
) -> tuple[list[dict[str, Any]], float]:
    result_paths: list[Path] = []
    processes: list[Any] = []
    start_event = ctx.Event()
    ranges = _split_message_ranges(messages, pattern.process_count)

    for worker_index, (_start_index, count) in enumerate(ranges):
        result_path = scratch_dir / f"resilience_worker_{worker_index:02d}.json"
        result_paths.append(result_path)
        common = {
            "start_event": start_event,
            "result_path": str(result_path),
            "run_id": run_id,
            "repeat_index": repeat_index,
            "worker_index": worker_index,
            "count": count,
            "scenario_name": resilience_scenario,
            "module_route": pattern.module_route,
        }
        if child_target is _child_dsafelogger_resilience:
            kwargs = {"repo_root": str(repo_root), "bootstrap_ctx": queue_obj, **common}
        else:
            kwargs = {"queue_obj": queue_obj, **common}
        process = ctx.Process(target=child_target, kwargs=kwargs)
        process.start()
        processes.append(process)

    started_at = time.perf_counter()
    start_event.set()
    if resilience_scenario == "rolling_restart_mixed_shutdown":
        time.sleep(0.2)
        for worker_index, process in enumerate(processes):
            if _resilience_exit_mode(worker_index, resilience_scenario) == "terminate" and process.is_alive():
                process.terminate()

    for process in processes:
        process.join(timeout)
        if process.is_alive():
            process.kill()

    worker_results: list[dict[str, Any]] = []
    for worker_index, result_path in enumerate(result_paths):
        if result_path.exists():
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"worker_index": worker_index, "error": "invalid_result_json"}
        else:
            payload = {"worker_index": worker_index, "attempted": 0, "accepted": 0, "error": "no_result_file"}
        process = processes[worker_index]
        payload["exitcode"] = process.exitcode
        payload["planned_exit_mode"] = _resilience_exit_mode(worker_index, resilience_scenario)
        worker_results.append(payload)
    return worker_results, time.perf_counter() - started_at


def _build_resilience_report(
    *,
    scenario_name: str,
    backend: str,
    worker_results: list[dict[str, Any]],
    delivered_count: int,
    writer_status: dict[str, Any],
    aggregator_failures: int = 0,
) -> ResilienceReport:
    def _sum_counter_map(value: object) -> int:
        if not isinstance(value, dict):
            return 0
        total = 0
        for item in value.values():
            try:
                total += int(item or 0)
            except (TypeError, ValueError):
                continue
        return total

    def _status_int(key: str, default: int) -> int:
        if key not in writer_status:
            return default
        try:
            return int(writer_status[key] or 0)
        except (TypeError, ValueError):
            return default

    attempted = sum(int(item.get("attempted") or 0) for item in worker_results)
    accepted = sum(int(item.get("accepted") or 0) for item in worker_results)
    timeout_drop = sum(int(item.get("timeout_drop") or 0) for item in worker_results)
    overload_shed = sum(int(item.get("overload_shed") or 0) for item in worker_results)
    worker_known_dropped = timeout_drop + overload_shed
    writer_known_dropped = 0

    if backend == "D-SafeLogger":
        attempted = _status_int("attempted", attempted)
        accepted = _status_int("accepted", accepted)
        delivered_for_accounting = _status_int("delivered", delivered_count)
        partial = _status_int("partial_delivered", _status_int("writer_partial_delivered", 0))
        worker_known_dropped = _sum_counter_map(writer_status.get("worker_drop_breakdown"))
        writer_known_dropped = _sum_counter_map(writer_status.get("writer_drop_breakdown"))
        known_dropped = _status_int("known_dropped", worker_known_dropped + writer_known_dropped)
        known_rejected = _status_int(
            "known_rejected",
            _sum_counter_map(writer_status.get("writer_reject_breakdown")),
        )
        observability = [
            "attempted",
            "accepted",
            "delivered",
            "partial_delivered",
            "known_rejected",
            "known_dropped",
            "unexplained_lost",
            "writer_reject_breakdown",
            "worker_drop_breakdown",
            "writer_drop_breakdown",
        ]
    else:
        known_dropped = None
        known_rejected = aggregator_failures if scenario_name == "sink_temporarily_unavailable" else None
        observability = ["attempted", "delivered"]
        accepted = None
        delivered_for_accounting = delivered_count
        partial = 0

    if known_dropped is None or known_rejected is None or accepted is None:
        unexplained = None
        shutdown_result = "unknown"
    else:
        unexplained = _status_int(
            "unexplained_lost",
            max(0, accepted - delivered_for_accounting - partial - known_rejected - writer_known_dropped),
        )
        bench_shutdown_verdict = "clean" if unexplained == 0 else "degraded"
        if scenario_name == "rolling_restart_mixed_shutdown" and any(item.get("planned_exit_mode") != "normal" for item in worker_results):
            bench_shutdown_verdict = "degraded" if unexplained or known_dropped or known_rejected else "clean_with_worker_crash"
        shutdown_result = bench_shutdown_verdict
        if backend == "D-SafeLogger":
            shutdown_report_result = writer_status.get("shutdown_report_result")
            if isinstance(shutdown_report_result, str) and shutdown_report_result:
                writer_status["bench_shutdown_verdict"] = bench_shutdown_verdict
                shutdown_result = shutdown_report_result

    exit_summary: dict[str, int] = {}
    for item in worker_results:
        mode = str(item.get("planned_exit_mode") or item.get("exit_mode") or "unknown")
        exit_summary[mode] = exit_summary.get(mode, 0) + 1

    return ResilienceReport(
        scenario=scenario_name,
        attempted_count=attempted,
        accepted_count=accepted,
        delivered_count=delivered_count,
        known_rejected_count=known_rejected,
        known_dropped_count=known_dropped,
        unexplained_lost_count=unexplained,
        shutdown_result=shutdown_result,
        observability_fields_available=observability,
        worker_exit_summary=exit_summary,
        writer_status=writer_status,
    )


# ---------------------------------------------------------------------------
# Single backend run
# ---------------------------------------------------------------------------

def _run_resilience_backend_worker(args: argparse.Namespace) -> RawRunRecord:
    pattern = PATTERN_MAP[args.pattern]
    structured = args.scenario == "json"
    scratch_dir = Path(args.scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    log_root = scratch_dir / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    python_version = platform.python_version()
    runtime_gil = _runtime_gil_text()
    scenario_name = args.resilience_scenario

    def _make_record(status: str, note: str | None = None, resilience: ResilienceReport | None = None) -> RawRunRecord:
        return RawRunRecord(
            python_label=args.python_label,
            gil_label=args.gil_label,
            python_version=python_version,
            runtime_gil=runtime_gil,
            backend=args.backend,
            scenario=args.scenario,
            pattern=pattern.name,
            process_count=pattern.process_count,
            module_route=pattern.module_route,
            messages=args.messages,
            run_index=args.run_index,
            run_id=args.run_id,
            repeat_index=args.repeat_index,
            profile=args.profile,
            status=status,
            delivered_lines=resilience.delivered_count if resilience else None,
            resilience=resilience,
            note=note,
        )

    if scenario_name not in RESILIENCE_SCENARIOS:
        return _make_record("error", f"unknown resilience scenario: {scenario_name}")

    try:
        writer_status: dict[str, Any] = {}
        aggregator_failures = 0
        if args.backend == "D-SafeLogger":
            repo_root = Path(args.repo_root)
            sys.path.insert(0, str(repo_root / "src"))
            import dsafelogger.mp as dsmp
            import dsafelogger.mp as dsmp_mod

            queue_size = None
            ipc_timeout = 0.5
            runtime_warning_path = scratch_dir / "runtime_warning.jsonl"
            shutdown_report_path = scratch_dir / "shutdown_report.json"
            if scenario_name == "burst_backpressure":
                queue_size = max(8, min(64, args.messages // 16))
                ipc_timeout = 0.001
            bootstrap_ctx = dsmp.ConfigureLogger(
                log_path=str(log_root),
                pg_name="BenchMPResilience",
                console_out=False,
                structured=structured,
                is_async=False,
                worker_model="process",
                mp_context=ctx,
                ipc_log_queue_maxsize=queue_size,
                ipc_client_queue_maxsize=queue_size,
                ipc_log_timeout=ipc_timeout,
                runtime_warning_path=str(runtime_warning_path),
                shutdown_report_path=str(shutdown_report_path),
            )
            runtime = dsmp_mod._mp_writer_runtime
            if scenario_name == "sink_temporarily_unavailable" and runtime is not None:
                for handler in runtime._sink_groups.get("root", []):
                    try:
                        handler.close()
                    except Exception:
                        pass
                runtime._sink_groups["root"] = [FailingRequiredHandler()]
            worker_results, elapsed_sec = _run_resilience_children(
                ctx=ctx,
                child_target=_child_dsafelogger_resilience,
                repo_root=repo_root,
                queue_obj=bootstrap_ctx,
                scratch_dir=scratch_dir,
                pattern=pattern,
                messages=args.messages,
                timeout=args.timeout,
                run_id=args.run_id,
                repeat_index=args.repeat_index,
                resilience_scenario=scenario_name,
            )
            try:
                writer_status = dict(dsmp.GetDeliveryStatus())
            except Exception as exc:
                writer_status = {"delivery_status_error": repr(exc)}
            writer_status["runtime_warning_path"] = str(runtime_warning_path)
            writer_status["shutdown_report_path"] = str(shutdown_report_path)
            try:
                dsmp._mp_shutdown()
            except Exception:
                pass
            writer_status["runtime_warning_exists"] = runtime_warning_path.exists()
            writer_status["shutdown_report_exists"] = shutdown_report_path.exists()
            fallback_files = sorted(
                str(path)
                for path in scratch_dir.glob(f"{runtime_warning_path.name}.*.fallback.jsonl")
            )
            writer_status["runtime_warning_fallback_files"] = fallback_files
            writer_status["runtime_warning_fallback_file_count"] = len(fallback_files)
            if shutdown_report_path.exists():
                try:
                    shutdown_report = json.loads(shutdown_report_path.read_text(encoding="utf-8"))
                    writer_status["shutdown_report_schema_version"] = shutdown_report.get("schema_version")
                    writer_status["shutdown_report_result"] = shutdown_report.get("shutdown_result")
                    writer_status["shutdown_report_worker_crash_observed"] = shutdown_report.get("worker_crash_observed")
                    writer_status["shutdown_report_missing_detach_clients"] = shutdown_report.get("missing_detach_clients")
                    writer_status["shutdown_report_missing_detach_client_ids"] = shutdown_report.get("missing_detach_client_ids")
                    writer_status["shutdown_report_missing_detach_pids"] = shutdown_report.get("missing_detach_pids")
                    writer_status["shutdown_report_warning_queue_drain_incomplete"] = shutdown_report.get(
                        "warning_queue_drain_incomplete"
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    writer_status["shutdown_report_error"] = repr(exc)
        elif args.backend == "stdlib logging":
            queue_obj = ctx.Queue(maxsize=max(8, min(64, args.messages // 16)) if scenario_name == "burst_backpressure" else 0)
            aggregator = ResilienceAggregator(
                queue_obj,
                log_root,
                structured=structured,
                module_route=pattern.module_route,
                fail_required=scenario_name == "sink_temporarily_unavailable",
            )
            aggregator.start()
            worker_results, elapsed_sec = _run_resilience_children(
                ctx=ctx,
                child_target=_child_stdlib_resilience,
                repo_root=None,
                queue_obj=queue_obj,
                scratch_dir=scratch_dir,
                pattern=pattern,
                messages=args.messages,
                timeout=args.timeout,
                run_id=args.run_id,
                repeat_index=args.repeat_index,
                resilience_scenario=scenario_name,
            )
            aggregator.stop()
            aggregator_failures = aggregator.failure_count
        elif args.backend == "loguru":
            queue_obj = ctx.Queue(maxsize=max(8, min(64, args.messages // 16)) if scenario_name == "burst_backpressure" else 0)
            aggregator = ResilienceAggregator(
                queue_obj,
                log_root,
                structured=structured,
                module_route=pattern.module_route,
                fail_required=scenario_name == "sink_temporarily_unavailable",
            )
            aggregator.start()
            worker_results, elapsed_sec = _run_resilience_children(
                ctx=ctx,
                child_target=_child_loguru_resilience,
                repo_root=None,
                queue_obj=queue_obj,
                scratch_dir=scratch_dir,
                pattern=pattern,
                messages=args.messages,
                timeout=args.timeout,
                run_id=args.run_id,
                repeat_index=args.repeat_index,
                resilience_scenario=scenario_name,
            )
            aggregator.stop()
            aggregator_failures = aggregator.failure_count
        else:
            return _make_record("error", f"unsupported backend: {args.backend}")
    except Exception as exc:
        return _make_record("error", str(exc))

    delivered_lines = _count_log_lines(log_root)
    resilience = _build_resilience_report(
        scenario_name=scenario_name,
        backend=args.backend,
        worker_results=worker_results,
        delivered_count=delivered_lines,
        writer_status=writer_status,
        aggregator_failures=aggregator_failures,
    )
    metrics = _compute_metrics([0.0] * max(1, resilience.attempted_count), elapsed_sec) if elapsed_sec > 0 else {}
    return RawRunRecord(
        python_label=args.python_label,
        gil_label=args.gil_label,
        python_version=python_version,
        runtime_gil=runtime_gil,
        backend=args.backend,
        scenario=args.scenario,
        pattern=pattern.name,
        process_count=pattern.process_count,
        module_route=pattern.module_route,
        messages=args.messages,
        run_index=args.run_index,
        run_id=args.run_id,
        repeat_index=args.repeat_index,
        profile=args.profile,
        status="ok" if resilience.shutdown_result != "unknown" else "observability_gap",
        throughput=round(metrics.get("throughput", 0)) if metrics else None,
        delivered_lines=delivered_lines,
        resilience=resilience,
        note=f"resilience_scenario={scenario_name}; shutdown={resilience.shutdown_result}",
    )


def _run_backend_worker(args: argparse.Namespace) -> RawRunRecord:
    if args.profile == "resilience_profile":
        return _run_resilience_backend_worker(args)

    pattern = PATTERN_MAP[args.pattern]
    structured = args.scenario == "json"
    scratch_dir = Path(args.scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    log_root = scratch_dir / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    python_version = platform.python_version()
    runtime_gil = _runtime_gil_text()
    run_id = args.run_id
    repeat_index = args.repeat_index

    def _make_error(msg: str) -> RawRunRecord:
        return RawRunRecord(
            python_label=args.python_label,
            gil_label=args.gil_label,
            python_version=python_version,
            runtime_gil=runtime_gil,
            backend=args.backend,
            scenario=args.scenario,
            pattern=pattern.name,
            process_count=pattern.process_count,
            module_route=pattern.module_route,
            messages=args.messages,
            run_index=args.run_index,
            run_id=run_id,
            repeat_index=repeat_index,
            profile=args.profile,
            status="error",
            note=msg,
        )

    try:
        if args.backend == "D-SafeLogger":
            repo_root = Path(args.repo_root)
            sys.path.insert(0, str(repo_root / "src"))
            import dsafelogger.mp as dsmp

            config_dict = _module_config(log_root) if pattern.module_route else None
            ipc_log_queue_maxsize = None
            ipc_client_queue_maxsize = None
            if args.profile == "integrity_profile":
                ipc_log_queue_maxsize = max(10_000, args.messages * 2)
                ipc_client_queue_maxsize = ipc_log_queue_maxsize
            elif args.profile == "overload_profile":
                ipc_log_queue_maxsize = max(
                    1,
                    min(OVERLOAD_QUEUE_MAXSIZE, args.messages // OVERLOAD_QUEUE_DIVISOR),
                )
                ipc_client_queue_maxsize = ipc_log_queue_maxsize

            bootstrap_ctx = dsmp.ConfigureLogger(
                log_path=str(log_root),
                pg_name="BenchMP",
                console_out=False,
                structured=structured,
                is_async=bool(getattr(args, 'is_async', False)),
                worker_model="process",
                mp_context=ctx,
                config_dict=config_dict,
                ipc_log_queue_maxsize=ipc_log_queue_maxsize,
                ipc_client_queue_maxsize=ipc_client_queue_maxsize,
            )
            try:
                latencies, elapsed_sec = _run_children_v23a(
                    ctx=ctx,
                    child_target=_child_dsafelogger_v23a,
                    repo_root=repo_root,
                    queue_obj=bootstrap_ctx,
                    scratch_dir=scratch_dir,
                    log_root=log_root,
                    structured=structured,
                    pattern=pattern,
                    messages=args.messages,
                    timeout=args.timeout,
                    run_id=run_id,
                    repeat_index=repeat_index,
                )
            finally:
                try:
                    dsmp._mp_shutdown()
                except Exception:
                    pass

        elif args.backend == "stdlib logging":
            queue_obj = ctx.Queue()
            aggregator = EventAggregator(
                queue_obj, log_root, structured=structured, module_route=pattern.module_route
            )
            aggregator.start()
            latencies, elapsed_sec = _run_children_v23a(
                ctx=ctx,
                child_target=_child_stdlib_v23a,
                repo_root=None,
                queue_obj=queue_obj,
                scratch_dir=scratch_dir,
                log_root=log_root,
                structured=structured,
                pattern=pattern,
                messages=args.messages,
                timeout=args.timeout,
                run_id=run_id,
                repeat_index=repeat_index,
            )
            aggregator.stop()

        elif args.backend == "loguru":
            queue_obj = ctx.Queue()
            aggregator = EventAggregator(
                queue_obj, log_root, structured=structured, module_route=pattern.module_route
            )
            aggregator.start()
            latencies, elapsed_sec = _run_children_v23a(
                ctx=ctx,
                child_target=_child_loguru_v23a,
                repo_root=None,
                queue_obj=queue_obj,
                scratch_dir=scratch_dir,
                log_root=log_root,
                structured=structured,
                pattern=pattern,
                messages=args.messages,
                timeout=args.timeout,
                run_id=run_id,
                repeat_index=repeat_index,
            )
            aggregator.stop()

        else:
            return _make_error(f"unsupported backend: {args.backend}")

    except Exception as exc:
        return _make_error(str(exc))

    # Integrity verification (always run, outcome depends on profile)
    integrity = _verify_integrity(
        log_root=log_root,
        run_id=run_id,
        repeat_index=repeat_index,
        pattern=pattern,
        scenario=args.scenario,
        backend=args.backend,
        python_label=args.python_label,
        gil_label=args.gil_label,
        messages=args.messages,
        profile=args.profile,
    )

    delivered_lines = _count_log_lines(log_root)

    # Determine run status
    if args.profile == "integrity_profile" and integrity.is_integrity_failure:
        status = "integrity_failure"
    elif delivered_lines != args.messages and args.profile != "overload_profile":
        status = "error"
    else:
        status = "ok"

    note_parts: list[str] = []
    if integrity.failure_reasons:
        note_parts.append("; ".join(integrity.failure_reasons))
    if delivered_lines != args.messages and args.profile == "overload_profile":
        note_parts.append(
            f"overload_shed: delivered={delivered_lines} expected={args.messages}"
        )

    metrics = _compute_metrics(latencies, elapsed_sec) if latencies else {}

    return RawRunRecord(
        python_label=args.python_label,
        gil_label=args.gil_label,
        python_version=python_version,
        runtime_gil=runtime_gil,
        backend=args.backend,
        scenario=args.scenario,
        pattern=pattern.name,
        process_count=pattern.process_count,
        module_route=pattern.module_route,
        messages=args.messages,
        run_index=args.run_index,
        run_id=run_id,
        repeat_index=repeat_index,
        profile=args.profile,
        is_async=bool(getattr(args, 'is_async', False)),
        status=status,
        throughput=round(metrics["throughput"]) if metrics else None,
        p50_us=round(metrics["p50_us"], 1) if metrics else None,
        p90_us=round(metrics["p90_us"], 1) if metrics else None,
        p99_us=round(metrics["p99_us"], 1) if metrics else None,
        delivered_lines=delivered_lines,
        integrity=integrity,
        note="; ".join(note_parts) if note_parts else None,
    )


# ---------------------------------------------------------------------------
# Invoke worker subprocess
# ---------------------------------------------------------------------------

def _invoke_worker(
    *,
    script_path: Path,
    repo_root: Path,
    target_python: str,
    python_label: str,
    gil_label: str,
    backend: str,
    pattern: str,
    scenario: str,
    messages: int,
    run_index: int,
    repeat_index: int,
    run_id: str,
    profile: str,
    resilience_scenario: str,
    scratch_dir: Path,
    timeout: int,
    is_async: bool = False,
) -> RawRunRecord:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root / "src") + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    env["PYTHON_GIL"] = GIL_ENV_MAP[gil_label]

    cmd = [
        target_python,
        str(script_path),
        "--worker-run",
        "--repo-root", str(repo_root),
        "--python-label", python_label,
        "--gil-label", gil_label,
        "--backend", backend,
        "--pattern", pattern,
        "--scenario", scenario,
        "--messages", str(messages),
        "--run-index", str(run_index),
        "--repeat-index", str(repeat_index),
        "--run-id", run_id,
        "--profile", profile,
        "--resilience-scenario", resilience_scenario,
        "--scratch-dir", str(scratch_dir),
        "--timeout", str(timeout),
    ]
    if is_async:
        cmd.append("--is-async")
    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout + 30,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        return RawRunRecord(
            python_label=python_label,
            gil_label=gil_label,
            python_version="unknown",
            runtime_gil="unknown",
            backend=backend,
            scenario=scenario,
            pattern=pattern,
            process_count=PATTERN_MAP[pattern].process_count,
            module_route=PATTERN_MAP[pattern].module_route,
            messages=messages,
            run_index=run_index,
            run_id=run_id,
            repeat_index=repeat_index,
            profile=profile,
            is_async=is_async,
            status="error",
            note=(completed.stderr.strip() or completed.stdout.strip() or "worker failed")[-1000:],
        )
    data = json.loads(completed.stdout)
    # Deserialize integrity report if present
    integrity_data = data.pop("integrity", None)
    resilience_data = data.pop("resilience", None)
    record = RawRunRecord(**data)
    if integrity_data is not None:
        record.integrity = IntegrityReport(**integrity_data)
    if resilience_data is not None:
        record.resilience = ResilienceReport(**resilience_data)
    return record


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def _summarize(records: list[RawRunRecord]) -> list[SummaryRow]:
    grouped: dict[tuple, list[RawRunRecord]] = {}
    for record in records:
        key = (
            record.python_label, record.gil_label,
            record.backend, record.scenario, record.pattern, record.profile,
            record.is_async,
            record.resilience.scenario if record.resilience else "",
        )
        grouped.setdefault(key, []).append(record)

    rows: list[SummaryRow] = []
    for group_records in grouped.values():
        successful = [r for r in group_records if r.status in ("ok", "integrity_failure", "observability_gap")]
        first = group_records[0]
        if not successful:
            note = "; ".join(
                f"run {r.run_index}: {r.status}{': ' + r.note if r.note else ''}"
                for r in group_records
            )
            rows.append(SummaryRow(
                python_label=first.python_label,
                gil_label=first.gil_label,
                python_version=first.python_version,
                runtime_gil=first.runtime_gil,
                backend=first.backend,
                scenario=first.scenario,
                pattern=first.pattern,
                process_count=first.process_count,
                module_route=first.module_route,
                messages=first.messages,
                profile=first.profile,
                status="error",
                successful_runs=0,
                total_runs=len(group_records),
                is_async=first.is_async,
                note=note,
            ))
            continue

        throughputs = [r.throughput for r in successful if r.throughput is not None]
        p50_values = [r.p50_us for r in successful if r.p50_us is not None]
        p90_values = [r.p90_us for r in successful if r.p90_us is not None]
        p99_values = [r.p99_us for r in successful if r.p99_us is not None]
        delivered_values = [r.delivered_lines for r in successful if r.delivered_lines is not None]
        integrity_failures = sum(
            1 for r in successful if r.integrity and r.integrity.is_integrity_failure
        )
        resilience_reports = [r.resilience for r in successful if r.resilience is not None]

        failed_runs = [r for r in group_records if r.status not in ("ok", "integrity_failure", "observability_gap")]
        note_parts: list[str] = []
        if failed_runs:
            note_parts.append("; ".join(
                f"run {r.run_index}: {r.status}{': ' + r.note if r.note else ''}"
                for r in failed_runs
            ))
        if integrity_failures:
            note_parts.append(f"integrity_failures={integrity_failures}/{len(successful)}")

        ok_count = sum(1 for r in successful if r.status == "ok")
        observability_gap_count = sum(1 for r in successful if r.status == "observability_gap")
        overall_status = "ok" if ok_count == len(group_records) else (
            "observability_gap" if observability_gap_count else "integrity_failure" if integrity_failures else "partial"
        )

        rows.append(SummaryRow(
            python_label=first.python_label,
            gil_label=first.gil_label,
            python_version=first.python_version,
            runtime_gil=first.runtime_gil,
            backend=first.backend,
            scenario=first.scenario,
            pattern=first.pattern,
            process_count=first.process_count,
            module_route=first.module_route,
            messages=first.messages,
            profile=first.profile,
            status=overall_status,
            successful_runs=len(successful),
            total_runs=len(group_records),
            is_async=first.is_async,
            throughput_avg=round(statistics.mean(throughputs)) if throughputs else None,
            throughput_min=min(throughputs) if throughputs else None,
            throughput_max=max(throughputs) if throughputs else None,
            p50_us=round(statistics.median(p50_values), 1) if p50_values else None,
            p90_us=round(statistics.median(p90_values), 1) if p90_values else None,
            p99_us=round(statistics.median(p99_values), 1) if p99_values else None,
            delivered_lines=delivered_values[0] if delivered_values else None,
            integrity_failures=integrity_failures,
            resilience_scenario=resilience_reports[0].scenario if resilience_reports else "",
            attempted_count=sum(r.attempted_count for r in resilience_reports) if resilience_reports else None,
            accepted_count=(
                sum(r.accepted_count for r in resilience_reports if r.accepted_count is not None)
                if resilience_reports and all(r.accepted_count is not None for r in resilience_reports)
                else None
            ),
            known_rejected_count=(
                sum(r.known_rejected_count for r in resilience_reports if r.known_rejected_count is not None)
                if resilience_reports and all(r.known_rejected_count is not None for r in resilience_reports)
                else None
            ),
            known_dropped_count=(
                sum(r.known_dropped_count for r in resilience_reports if r.known_dropped_count is not None)
                if resilience_reports and all(r.known_dropped_count is not None for r in resilience_reports)
                else None
            ),
            unexplained_lost_count=(
                sum(r.unexplained_lost_count for r in resilience_reports if r.unexplained_lost_count is not None)
                if resilience_reports and all(r.unexplained_lost_count is not None for r in resilience_reports)
                else None
            ),
            shutdown_result=(
                "mixed" if resilience_reports and len({r.shutdown_result for r in resilience_reports}) > 1
                else resilience_reports[0].shutdown_result if resilience_reports else ""
            ),
            note="; ".join(note_parts) if note_parts else None,
        ))

    rows.sort(key=lambda r: (r.python_label, r.gil_label, r.scenario, r.pattern, r.backend))
    return rows


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _results_markdown(summary: dict[str, Any]) -> str:
    profile = summary["configuration"]["profile"]
    lines = [
        "# Multiprocess Comparison Benchmark — v23a",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Profile: **{profile}**",
        f"- Messages per run: {summary['configuration']['messages']:,}",
        f"- Repeats: {summary['configuration']['repeat']}",
        f"- Backends: {', '.join(BACKENDS)}",
        f"- Patterns: {', '.join(p.name for p in PATTERNS)}",
        "",
    ]
    # Environment section
    env = summary.get("environment", {})
    if env:
        lines += [
            "## Environment",
            "",
            f"- OS: {env.get('os', {}).get('system', '?')} {env.get('os', {}).get('release', '?')}",
            f"- Python: {env.get('python', {}).get('version', '?')} "
            f"({env.get('python', {}).get('executable', '?')})",
            f"- GIL: {env.get('python', {}).get('runtime_gil', '?')}",
            f"- CPU logical count: {env.get('cpu', {}).get('count_logical', '?')}",
            f"- scratch_root: {env.get('scratch_root', '?')}",
            "",
        ]
    lines += [
        "## Pattern Legend",
        "",
    ]
    for pattern in PATTERNS:
        lines.append(f"- `{pattern.name}`: {pattern.description}")
    lines += ["", "## Results", ""]

    if profile == "resilience_profile":
        for python_label in ["3.13", "3.14"]:
            lines.append(f"### Python {python_label}")
            lines.append("")
            for gil_label in ["enabled", "disabled"]:
                lines.append(f"#### GIL {gil_label}")
                lines.append("")
                lines.append(
                    "| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | "
                    "KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |"
                )
                lines.append(
                    "|----------|---------|--------|------|----------:|---------:|----------:|"
                    "--------------:|-------------:|----------------:|----------|---------------|-------|"
                )
                for resilience_scenario in RESILIENCE_SCENARIOS:
                    for backend in BACKENDS:
                        row = next(
                            (
                                item for item in summary["summary_rows"]
                                if item["python_label"] == python_label
                                and item["gil_label"] == gil_label
                                and item["backend"] == backend
                                and item.get("resilience_scenario") == resilience_scenario
                            ),
                            None,
                        )
                        if row is None:
                            lines.append(
                                f"| {resilience_scenario} | {backend} | missing | 0/0 | — | — | — | — | — | — | — | — | no data |"
                            )
                            continue
                        raw_for_row = [
                            item for item in summary.get("raw_runs", [])
                            if item.get("python_label") == python_label
                            and item.get("gil_label") == gil_label
                            and item.get("backend") == backend
                            and (item.get("resilience") or {}).get("scenario") == resilience_scenario
                        ]
                        observability = "—"
                        if raw_for_row:
                            fields = (raw_for_row[0].get("resilience") or {}).get("observability_fields_available") or []
                            observability = ", ".join(fields)
                        note = (row.get("note") or "").replace("\n", " ")
                        def _cell(value: Any) -> str:
                            return "—" if value is None else str(value)
                        lines.append(
                            f"| {resilience_scenario} | {backend} | {row['status']} | {row['successful_runs']}/{row['total_runs']} | "
                            f"{_cell(row.get('attempted_count'))} | {_cell(row.get('accepted_count'))} | {_cell(row.get('delivered_lines'))} | "
                            f"{_cell(row.get('known_rejected_count'))} | {_cell(row.get('known_dropped_count'))} | "
                            f"{_cell(row.get('unexplained_lost_count'))} | {_cell(row.get('shutdown_result'))} | {observability} | {note} |"
                        )
                lines.append("")
        return "\n".join(lines)

    for python_label in ["3.13", "3.14"]:
        lines.append(f"### Python {python_label}")
        lines.append("")
        for gil_label in ["enabled", "disabled"]:
            lines.append(f"#### GIL {gil_label}")
            lines.append("")
            for scenario in SCENARIOS:
                lines.append(f"##### {scenario}")
                lines.append("")
                lines.append(
                    "| Pattern | Backend | Procs | Status | Runs | "
                    "Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | "
                    "Delivered | IntegrityFail | Notes |"
                )
                lines.append(
                    "|---------|---------|------:|--------|------|"
                    "--------------------------|--------:|--------:|--------:|"
                    "----------:|-------------:|-------|"
                )
                for pattern in PATTERNS:
                    for backend in BACKENDS:
                        row = next(
                            (
                                item for item in summary["summary_rows"]
                                if item["python_label"] == python_label
                                and item["gil_label"] == gil_label
                                and item["scenario"] == scenario
                                and item["pattern"] == pattern.name
                                and item["backend"] == backend
                            ),
                            None,
                        )
                        if row is None:
                            lines.append(
                                f"| {pattern.name} | {backend} | {pattern.process_count}"
                                " | missing | 0/0 | — | — | — | — | — | — | no data |"
                            )
                            continue
                        tp = "—"
                        if row["throughput_avg"] is not None:
                            tp = (
                                f"{row['throughput_avg']:,} "
                                f"({row['throughput_min']:,}-{row['throughput_max']:,})"
                            )
                        note = (row.get("note") or "").replace("\n", " ")
                        lines.append(
                            f"| {row['pattern']} | {row['backend']} | {row['process_count']}"
                            f" | {row['status']} | {row['successful_runs']}/{row['total_runs']}"
                            f" | {tp}"
                            f" | {row['p50_us'] if row['p50_us'] is not None else '—'}"
                            f" | {row['p90_us'] if row['p90_us'] is not None else '—'}"
                            f" | {row['p99_us'] if row['p99_us'] is not None else '—'}"
                            f" | {row['delivered_lines'] if row['delivered_lines'] is not None else '—'}"
                            f" | {row['integrity_failures']}"
                            f" | {note} |"
                        )
                lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Matrix runner
# ---------------------------------------------------------------------------

def _run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    if args.session:
        session = args.session
    else:
        profile_prefix = {
            "integrity_profile": "benchmarks_multi_integ",
            "performance_profile": "benchmarks_multi_perf",
            "overload_profile": "benchmarks_multi_overload",
            "resilience_profile": "benchmarks_multi_resilience",
        }.get(args.profile, "benchmarks_multi")
        session = datetime.now(timezone.utc).strftime(f"{profile_prefix}_%Y%m%d_%H%M%S")
    repo_root = Path(args.repo_root)
    results_dir = repo_root / "benchmarks" / "results" / session
    results_dir.mkdir(parents=True, exist_ok=False)
    scratch_root = Path(args.scratch_root) / session
    scratch_root.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()
    python_targets = {"3.13": args.python313, "3.14": args.python314}

    run_id = _generate_run_id()
    raw_runs: list[RawRunRecord] = []

    # P0-2 related: force include 3.13/enabled/json/root_p4/D-SafeLogger
    priority_combo = ("3.13", "enabled", "json", "root_p4", "D-SafeLogger")
    profile_scenarios = ["json"] if args.profile == "resilience_profile" else SCENARIOS
    profile_patterns = [PATTERN_MAP["root_p4"]] if args.profile == "resilience_profile" else PATTERNS
    resilience_scenarios = RESILIENCE_SCENARIOS if args.profile == "resilience_profile" else [""]
    if args.profile == "resilience_profile" and args.resilience_scenario:
        resilience_scenarios = [args.resilience_scenario]

    for python_label in ["3.13", "3.14"]:
        for gil_label in ["enabled", "disabled"]:
            for scenario in profile_scenarios:
                for pattern in profile_patterns:
                    for backend in BACKENDS:
                        for resilience_scenario in resilience_scenarios:
                            for run_index in range(1, args.repeat + 1):
                                resilience_part = resilience_scenario or "normal"
                                scratch_dir = (
                                    scratch_root
                                    / f"py{python_label.replace('.', '')}_gil_{gil_label}"
                                    / scenario / pattern.name
                                    / resilience_part
                                    / backend.replace(" ", "_")
                                    / f"run_{run_index:02d}"
                                )
                                is_priority = (
                                    python_label, gil_label, scenario,
                                    pattern.name, backend,
                                ) == priority_combo
                                label_suffix = " [P0-2 priority]" if is_priority else ""
                                res_text = f" | resilience={resilience_scenario}" if resilience_scenario else ""
                                print(
                                    f"[{python_label}/{gil_label}] {scenario} | "
                                    f"{pattern.name} | {backend}{res_text} | "
                                    f"run {run_index}/{args.repeat} | "
                                    f"profile={args.profile}{label_suffix}",
                                    file=sys.stderr,
                                )
                                record = _invoke_worker(
                                    script_path=script_path,
                                    repo_root=repo_root,
                                    target_python=python_targets[python_label],
                                    python_label=python_label,
                                    gil_label=gil_label,
                                    backend=backend,
                                    pattern=pattern.name,
                                    scenario=scenario,
                                    messages=args.messages,
                                    run_index=run_index,
                                    repeat_index=run_index,
                                    run_id=run_id,
                                    profile=args.profile,
                                    resilience_scenario=resilience_scenario,
                                    scratch_dir=scratch_dir,
                                    timeout=args.timeout,
                                    is_async=bool(getattr(args, 'is_async', False)),
                                )
                                raw_runs.append(record)
                                if record.status in ("ok", "integrity_failure", "observability_gap"):
                                    integ = record.integrity
                                    integ_summary = ""
                                    if integ:
                                        integ_summary = (
                                            f" | missing={integ.missing_count}"
                                            f" dup={integ.duplicate_count}"
                                            f" fail={'YES' if integ.is_integrity_failure else 'no'}"
                                        )
                                    resil_summary = ""
                                    if record.resilience:
                                        resil_summary = (
                                            f" | attempted={record.resilience.attempted_count}"
                                            f" delivered={record.resilience.delivered_count}"
                                            f" unexplained={record.resilience.unexplained_lost_count}"
                                            f" shutdown={record.resilience.shutdown_result}"
                                        )
                                    print(
                                        f"  {record.status}: "
                                        f"{(record.throughput or 0):,} msg/s | "
                                        f"p50={record.p50_us or '?'}µs"
                                        f"{integ_summary}{resil_summary}",
                                        file=sys.stderr,
                                    )
                                else:
                                    print(
                                        f"  {record.status}: {record.note or ''}",
                                        file=sys.stderr,
                                    )
    env = _collect_environment(
        python_label="matrix",
        gil_label="matrix",
        messages=args.messages,
        repeat=args.repeat,
        profile=args.profile,
        patterns=[p.name for p in PATTERNS],
        scenarios=profile_scenarios,
        backends=BACKENDS,
        scratch_root=scratch_root,
    )

    def _serialize_record(r: RawRunRecord) -> dict[str, Any]:
        d = asdict(r)
        # integrity field is nested dataclass, already converted by asdict
        return d

    summary = {
        "session": session,
        "generated_at_utc": _utc_now(),
        "run_id": run_id,
        "configuration": {
            "messages": args.messages,
            "repeat": args.repeat,
            "profile": args.profile,
            "resilience_scenarios": resilience_scenarios if args.profile == "resilience_profile" else [],
            "is_async": bool(getattr(args, 'is_async', False)),
            "python313": args.python313,
            "python314": args.python314,
            "repo_root": str(repo_root),
        },
        "environment": env,
        "raw_runs": [_serialize_record(r) for r in raw_runs],
        "summary_rows": [asdict(row) for row in _summarize(raw_runs)],
    }
    (results_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (results_dir / "summary.md").write_text(
        _results_markdown(summary), encoding="utf-8"
    )
    return summary


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run multiprocess comparison benchmark - v23a"
    )
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES_INTEGRITY)
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--session")
    parser.add_argument("--python313", default=DEFAULT_PYTHON_313)
    parser.add_argument("--python314", default=DEFAULT_PYTHON_314)
    parser.add_argument("--scratch-root", default=str(DEFAULT_SCRATCH_ROOT))
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default="integrity_profile",
        help=(
            "integrity_profile: verify all messages delivered (use small --messages);"
            " performance_profile: measure throughput/latency;"
            " overload_profile: intentionally overflow D-SafeLogger queue;"
            " resilience_profile: operational failure-mode observability"
        ),
    )
    parser.add_argument(
        "--resilience-scenario",
        choices=["", *RESILIENCE_SCENARIOS],
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--is-async", action="store_true", dest="is_async",
        help="Use is_async=True for D-SafeLogger (process-local buffer queue per transport)",
    )
    # Worker-mode args (used when invoked as subprocess)
    parser.add_argument("--worker-run", action="store_true")
    parser.add_argument("--python-label", default="")
    parser.add_argument("--gil-label", default="")
    parser.add_argument("--backend", choices=BACKENDS)
    parser.add_argument("--pattern", choices=sorted(PATTERN_MAP.keys()))
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--run-index", type=int, default=1)
    parser.add_argument("--repeat-index", type=int, default=1)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--scratch-dir", default="")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.worker_run:
        if not all([args.python_label, args.gil_label, args.backend,
                    args.pattern, args.scenario, args.scratch_dir]):
            raise ValueError("worker mode requires python/gil/backend/pattern/scenario/scratch-dir")
        if not args.run_id:
            raise ValueError("worker mode requires --run-id")
        record = _run_backend_worker(args)
        d = asdict(record)
        print(json.dumps(d))
        return

    summary = _run_matrix(args)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
