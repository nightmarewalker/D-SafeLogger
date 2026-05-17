"""Benchmark runner for the full 3.13/3.14 x GIL on/off matrix.

This script has three execution modes:

1. Matrix mode (default)
   - Orchestrates Python 3.13 / 3.14 and GIL enabled / disabled runs
   - Uses the free-threaded executables and toggles ``PYTHON_GIL=1/0``
   - Saves raw per-environment JSON plus a combined summary JSON
   - Saves a session-local ``summary.md`` for the generated result set

2. Runtime mode (``--runtime-run``)
   - Runs all selected backend/mode/workload/scenario combinations inside the
     current interpreter / current GIL state
   - Spawns fresh worker subprocesses for each measured run
   - Returns JSON to stdout

3. Worker mode (``--worker-target``)
   - Runs a single backend/mode/workload/scenario measurement
   - Returns one raw run JSON document to stdout
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import logging.handlers
import math
import os
import platform
import queue
import shutil
import statistics
import subprocess
import sys
import sysconfig
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks._benchmark_report import render_single_session_markdown


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"
DEFAULT_SCRATCH_ROOT = Path(r"C:\TempX\D-SafeLogger-bench")
DEFAULT_MESSAGES = 100_000
DEFAULT_REPEAT = 3
DEFAULT_THREADS = 8
DEFAULT_WORKER_TIMEOUT_SEC = 600
DEFAULT_PYTHON_313 = r"C:\Python\313\python3.13t.exe"
DEFAULT_PYTHON_314 = r"C:\Python\314\python3.14t.exe"
GIL_ENV_MAP = {
    "enabled": "1",
    "disabled": "0",
}
BACKEND_ORDER = [
    ("D-SafeLogger", "sync"),
    ("D-SafeLogger", "async"),
    ("stdlib logging", "sync"),
    ("stdlib logging", "async"),
    ("loguru", "sync"),
    ("loguru", "async"),
    ("structlog", "sync"),
    ("structlog", "async"),
]


@dataclass
class RawRunRecord:
    python_label: str
    gil_label: str
    workload: str
    scenario: str
    backend: str
    mode: str
    messages: int
    threads: int
    run_index: int
    status: str
    throughput: int | None = None
    p50_us: float | None = None
    p90_us: float | None = None
    p99_us: float | None = None
    note: str | None = None
    scratch_dir: str | None = None


@dataclass
class SummaryRow:
    python_label: str
    gil_label: str
    workload: str
    scenario: str
    backend: str
    mode: str
    messages: int
    threads: int
    status: str
    successful_runs: int
    total_runs: int
    throughput_avg: int | None = None
    throughput_min: int | None = None
    throughput_max: int | None = None
    p50_us: float | None = None
    p90_us: float | None = None
    p99_us: float | None = None
    note: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _runtime_gil_enabled() -> bool | None:
    fn = getattr(sys, "_is_gil_enabled", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            return None
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        return None
    return True


def _build_free_threaded() -> bool:
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


def _runtime_metadata(
    *,
    python_label: str,
    gil_label: str,
    target_python: str,
) -> dict[str, Any]:
    return {
        "python_label": python_label,
        "gil_label": gil_label,
        "target_python": target_python,
        "runtime_executable": sys.executable,
        "python_version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "build_free_threaded": _build_free_threaded(),
        "runtime_gil_enabled": _runtime_gil_enabled(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "generated_at_utc": _utc_now(),
    }


def _sanitize_component(value: str) -> str:
    text = value.strip()
    text = text.replace(" ", "_")
    for ch in '\\/:*?"<>|':
        text = text.replace(ch, "_")
    return text


def _throughput_range_text(row: SummaryRow) -> str:
    if row.throughput_avg is None or row.throughput_min is None or row.throughput_max is None:
        return "—"
    return f"{row.throughput_avg:,} ({row.throughput_min:,}-{row.throughput_max:,})"


def _format_metric(value: float | int | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:.1f}"


def _percentile_value(sorted_latencies: list[float], fraction: float) -> float:
    if not sorted_latencies:
        raise ValueError("latencies must not be empty")
    rank = max(1, math.ceil(len(sorted_latencies) * fraction))
    return sorted_latencies[rank - 1]


def _compute_metrics(latencies: list[float], elapsed_sec: float) -> dict[str, float]:
    if not latencies:
        raise ValueError("latencies must not be empty")
    if elapsed_sec <= 0:
        raise ValueError("elapsed_sec must be > 0")
    sorted_latencies = sorted(latencies)
    return {
        "throughput": len(latencies) / elapsed_sec,
        "p50_us": statistics.median(sorted_latencies) * 1e6,
        "p90_us": _percentile_value(sorted_latencies, 0.90) * 1e6,
        "p99_us": _percentile_value(sorted_latencies, 0.99) * 1e6,
    }


def _split_message_ranges(total_messages: int, thread_count: int) -> list[tuple[int, int]]:
    base_count = total_messages // thread_count
    extra_count = total_messages % thread_count
    ranges: list[tuple[int, int]] = []
    start_index = 0
    for thread_index in range(thread_count):
        count = base_count + (1 if thread_index < extra_count else 0)
        ranges.append((start_index, count))
        start_index += count
    return ranges


def _raise_thread_errors(error_texts: list[str]) -> None:
    if error_texts:
        raise RuntimeError(error_texts[0])


def _run_single_thread_sync(n: int, log_fn: Callable[[int], None]) -> dict[str, float]:
    latencies: list[float] = []
    started_at = time.perf_counter()
    for i in range(n):
        t0 = time.perf_counter()
        log_fn(i)
        latencies.append(time.perf_counter() - t0)
    elapsed_sec = time.perf_counter() - started_at
    return _compute_metrics(latencies, elapsed_sec)


def _run_single_thread_async(
    n: int,
    log_fn: Callable[[int], Awaitable[None]],
) -> dict[str, float]:
    async def runner() -> dict[str, float]:
        latencies: list[float] = []
        started_at = time.perf_counter()
        for i in range(n):
            t0 = time.perf_counter()
            await log_fn(i)
            latencies.append(time.perf_counter() - t0)
        elapsed_sec = time.perf_counter() - started_at
        return _compute_metrics(latencies, elapsed_sec)

    return asyncio.run(runner())


def _run_multi_thread_sync(
    n: int,
    thread_count: int,
    log_fn: Callable[[int], None],
) -> dict[str, float]:
    ranges = _split_message_ranges(n, thread_count)
    start_barrier = threading.Barrier(thread_count + 1)
    start_event = threading.Event()
    latency_buckets: list[list[float]] = [[] for _ in ranges]
    error_texts: list[str] = []
    worker_threads: list[threading.Thread] = []

    def worker(thread_index: int, start_index: int, count: int) -> None:
        local_latencies: list[float] = []
        try:
            start_barrier.wait()
            start_event.wait()
            for offset in range(count):
                message_index = start_index + offset
                t0 = time.perf_counter()
                log_fn(message_index)
                local_latencies.append(time.perf_counter() - t0)
        except Exception:
            error_texts.append(traceback.format_exc())
        finally:
            latency_buckets[thread_index] = local_latencies

    for thread_index, (start_index, count) in enumerate(ranges):
        worker_thread = threading.Thread(
            target=worker,
            args=(thread_index, start_index, count),
            name=f"bench-sync-{thread_index}",
        )
        worker_threads.append(worker_thread)
        worker_thread.start()

    start_barrier.wait()
    started_at = time.perf_counter()
    start_event.set()

    for worker_thread in worker_threads:
        worker_thread.join()

    elapsed_sec = time.perf_counter() - started_at
    _raise_thread_errors(error_texts)
    latencies = [lat for bucket in latency_buckets for lat in bucket]
    return _compute_metrics(latencies, elapsed_sec)


def _run_multi_thread_async(
    n: int,
    thread_count: int,
    log_fn: Callable[[int], Awaitable[None]],
) -> dict[str, float]:
    ranges = _split_message_ranges(n, thread_count)
    start_barrier = threading.Barrier(thread_count + 1)
    start_event = threading.Event()
    latency_buckets: list[list[float]] = [[] for _ in ranges]
    error_texts: list[str] = []
    worker_threads: list[threading.Thread] = []

    def worker(thread_index: int, start_index: int, count: int) -> None:
        async def runner() -> list[float]:
            local_latencies: list[float] = []
            for offset in range(count):
                message_index = start_index + offset
                t0 = time.perf_counter()
                await log_fn(message_index)
                local_latencies.append(time.perf_counter() - t0)
            return local_latencies

        try:
            start_barrier.wait()
            start_event.wait()
            latency_buckets[thread_index] = asyncio.run(runner())
        except Exception:
            error_texts.append(traceback.format_exc())

    for thread_index, (start_index, count) in enumerate(ranges):
        worker_thread = threading.Thread(
            target=worker,
            args=(thread_index, start_index, count),
            name=f"bench-async-{thread_index}",
        )
        worker_threads.append(worker_thread)
        worker_thread.start()

    start_barrier.wait()
    started_at = time.perf_counter()
    start_event.set()

    for worker_thread in worker_threads:
        worker_thread.join()

    elapsed_sec = time.perf_counter() - started_at
    _raise_thread_errors(error_texts)
    latencies = [lat for bucket in latency_buckets for lat in bucket]
    return _compute_metrics(latencies, elapsed_sec)


def _reset_dsafelogger() -> None:
    import dsafelogger

    if hasattr(dsafelogger, "_queue_listener") and dsafelogger._queue_listener is not None:
        try:
            dsafelogger._queue_listener.stop()
        except Exception:
            pass
        dsafelogger._queue_listener = None
    dsafelogger._configure_state = "unconfigured"
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
        root_logger.removeHandler(handler)
    logging.setLoggerClass(logging.Logger)


def _bench_dsafelogger(
    n: int,
    log_dir: Path,
    *,
    mode: str,
    structured: bool,
    thread_count: int,
) -> dict[str, float]:
    _reset_dsafelogger()
    from dsafelogger import ConfigureLogger, GetLogger

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="Bench",
        console_out=False,
        is_async=mode == "async",
        structured=structured,
    )
    logger = GetLogger("bench")

    try:
        if thread_count == 1:
            return _run_single_thread_sync(n, lambda i: logger.info("Benchmark message %d", i))
        return _run_multi_thread_sync(
            n, thread_count, lambda i: logger.info("Benchmark message %d", i)
        )
    finally:
        _reset_dsafelogger()


def _make_stdlib_json_formatter() -> logging.Formatter:
    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S")
                + f".{int(record.msecs):03d}",
                "level": record.levelname,
                "logger": record.name,
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
                "message": record.getMessage(),
            }
            return json.dumps(payload, ensure_ascii=False)

    return JsonFormatter()


def _bench_stdlib(
    n: int,
    log_dir: Path,
    *,
    mode: str,
    structured: bool,
    thread_count: int,
) -> dict[str, float]:
    _reset_dsafelogger()

    logger_name = f"stdlib_{mode}_{time.time_ns()}"
    stdlib_logger = logging.getLogger(logger_name)
    stdlib_logger.setLevel(logging.INFO)
    stdlib_logger.propagate = False
    for handler in stdlib_logger.handlers[:]:
        stdlib_logger.removeHandler(handler)

    file_handler = logging.FileHandler(
        log_dir / f"stdlib_{mode}.log",
        mode="w",
        encoding="utf-8",
    )
    if structured:
        file_handler.setFormatter(_make_stdlib_json_formatter())
    else:
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s.%(msecs)03d [%(levelname)s][%(filename)s:%(lineno)d:%(funcName)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    queue_handler: logging.Handler | None = None
    listener: logging.handlers.QueueListener | None = None

    try:
        if mode == "async":
            q: queue.Queue[Any] = queue.Queue(-1)
            queue_handler = logging.handlers.QueueHandler(q)
            stdlib_logger.addHandler(queue_handler)
            listener = logging.handlers.QueueListener(q, file_handler, respect_handler_level=True)
            listener.start()
        else:
            stdlib_logger.addHandler(file_handler)

        if thread_count == 1:
            return _run_single_thread_sync(
                n, lambda i: stdlib_logger.info("Benchmark message %d", i)
            )
        return _run_multi_thread_sync(
            n, thread_count, lambda i: stdlib_logger.info("Benchmark message %d", i)
        )
    finally:
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        if queue_handler is not None:
            stdlib_logger.removeHandler(queue_handler)
            try:
                queue_handler.close()
            except Exception:
                pass
        if file_handler in stdlib_logger.handlers:
            stdlib_logger.removeHandler(file_handler)
        try:
            file_handler.close()
        except Exception:
            pass


def _bench_loguru(
    n: int,
    log_dir: Path,
    *,
    mode: str,
    structured: bool,
    thread_count: int,
) -> dict[str, float] | dict[str, str]:
    _reset_dsafelogger()
    try:
        from loguru import logger as loguru_logger
    except ImportError:
        return {"status": "unsupported", "note": "loguru is not installed"}

    loguru_logger.remove()
    sink_path = log_dir / f"loguru_{mode}.log"
    add_kwargs: dict[str, Any] = {
        "enqueue": mode == "async",
        "backtrace": False,
        "diagnose": False,
        "encoding": "utf-8",
    }
    if structured:
        add_kwargs["serialize"] = True
    else:
        add_kwargs["format"] = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} [{level}][{file}:{line}:{function}] {message}"
        )

    sink_id = loguru_logger.add(sink_path, **add_kwargs)

    try:
        if thread_count == 1:
            return _run_single_thread_sync(
                n, lambda i: loguru_logger.info("Benchmark message {}", i)
            )
        return _run_multi_thread_sync(
            n,
            thread_count,
            lambda i: loguru_logger.info("Benchmark message {}", i),
        )
    finally:
        try:
            loguru_logger.remove(sink_id)
        except Exception:
            pass


def _structlog_add_logger_name(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("logger", "bench")
    return event_dict


def _structlog_rename_event(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


class _StructlogTextRenderer:
    def __call__(self, _: Any, __: str, event_dict: dict[str, Any]) -> str:
        timestamp = str(event_dict.pop("timestamp", ""))
        level = str(event_dict.pop("level", "")).upper()
        filename = str(event_dict.pop("filename", "?"))
        lineno = event_dict.pop("lineno", "?")
        func_name = str(event_dict.pop("func_name", "?"))
        message = str(event_dict.pop("message", ""))
        return f"{timestamp} [{level}][{filename}:{lineno}:{func_name}] {message}"


def _configure_structlog_logger(log_file: Any, *, structured: bool) -> Any:
    import structlog

    callsite_processor = structlog.processors.CallsiteParameterAdder(
        {
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.LINENO,
            structlog.processors.CallsiteParameter.FUNC_NAME,
        }
    )
    processors: list[Any] = [
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
        structlog.processors.add_log_level,
        callsite_processor,
        _structlog_add_logger_name,
        _structlog_rename_event,
    ]
    if structured:
        processors.append(structlog.processors.JSONRenderer(serializer=json.dumps))
    else:
        processors.append(_StructlogTextRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(file=log_file),
        cache_logger_on_first_use=False,
    )
    return structlog.get_logger("bench")


def _bench_structlog(
    n: int,
    log_dir: Path,
    *,
    mode: str,
    structured: bool,
    thread_count: int,
) -> dict[str, float] | dict[str, str]:
    _reset_dsafelogger()
    try:
        import structlog
    except ImportError:
        return {"status": "unsupported", "note": "structlog is not installed"}

    log_file = open(log_dir / f"structlog_{mode}.log", "w", encoding="utf-8")
    struct_logger = _configure_structlog_logger(log_file, structured=structured)

    try:
        if mode == "async":
            if not hasattr(struct_logger, "ainfo"):
                return {
                    "status": "unsupported",
                    "note": "this structlog build does not expose ainfo()",
                }

            async def async_log(message_index: int) -> None:
                await struct_logger.ainfo("Benchmark message", index=message_index)

            if thread_count == 1:
                return _run_single_thread_async(n, async_log)
            return _run_multi_thread_async(n, thread_count, async_log)

        if thread_count == 1:
            return _run_single_thread_sync(
                n, lambda i: struct_logger.info("Benchmark message", index=i)
            )
        return _run_multi_thread_sync(
            n,
            thread_count,
            lambda i: struct_logger.info("Benchmark message", index=i),
        )
    finally:
        try:
            log_file.close()
        except Exception:
            pass
        structlog.reset_defaults()


BACKEND_SPECS = [
    {
        "target": "dsafelogger_sync",
        "backend": "D-SafeLogger",
        "mode": "sync",
    },
    {
        "target": "dsafelogger_async",
        "backend": "D-SafeLogger",
        "mode": "async",
    },
    {
        "target": "stdlib_sync",
        "backend": "stdlib logging",
        "mode": "sync",
    },
    {
        "target": "stdlib_async",
        "backend": "stdlib logging",
        "mode": "async",
    },
    {
        "target": "loguru_sync",
        "backend": "loguru",
        "mode": "sync",
    },
    {
        "target": "loguru_async",
        "backend": "loguru",
        "mode": "async",
    },
    {
        "target": "structlog_sync",
        "backend": "structlog",
        "mode": "sync",
    },
    {
        "target": "structlog_async",
        "backend": "structlog",
        "mode": "async",
    },
]


WORKER_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "dsafelogger_sync": lambda n, d, s, t: _bench_dsafelogger(
        n,
        d,
        mode="sync",
        structured=s,
        thread_count=t,
    ),
    "dsafelogger_async": lambda n, d, s, t: _bench_dsafelogger(
        n,
        d,
        mode="async",
        structured=s,
        thread_count=t,
    ),
    "stdlib_sync": lambda n, d, s, t: _bench_stdlib(
        n,
        d,
        mode="sync",
        structured=s,
        thread_count=t,
    ),
    "stdlib_async": lambda n, d, s, t: _bench_stdlib(
        n,
        d,
        mode="async",
        structured=s,
        thread_count=t,
    ),
    "loguru_sync": lambda n, d, s, t: _bench_loguru(
        n,
        d,
        mode="sync",
        structured=s,
        thread_count=t,
    ),
    "loguru_async": lambda n, d, s, t: _bench_loguru(
        n,
        d,
        mode="async",
        structured=s,
        thread_count=t,
    ),
    "structlog_sync": lambda n, d, s, t: _bench_structlog(
        n,
        d,
        mode="sync",
        structured=s,
        thread_count=t,
    ),
    "structlog_async": lambda n, d, s, t: _bench_structlog(
        n,
        d,
        mode="async",
        structured=s,
        thread_count=t,
    ),
}


def _worker_once(
    *,
    python_label: str,
    gil_label: str,
    target: str,
    scenario: str,
    workload: str,
    messages: int,
    threads: int,
    run_index: int,
    scratch_dir: Path,
) -> RawRunRecord:
    structured = scenario == "json"
    thread_count = 1 if workload == "single" else threads
    scratch_dir.mkdir(parents=True, exist_ok=True)

    spec = next(item for item in BACKEND_SPECS if item["target"] == target)
    try:
        worker_fn = WORKER_FUNCTIONS[target]
        raw_result = worker_fn(messages, scratch_dir, structured, thread_count)
        status = raw_result.get("status", "ok")
        if status != "ok":
            return RawRunRecord(
                python_label=python_label,
                gil_label=gil_label,
                workload=workload,
                scenario=scenario,
                backend=spec["backend"],
                mode=spec["mode"],
                messages=messages,
                threads=thread_count,
                run_index=run_index,
                status=status,
                note=raw_result.get("note"),
                scratch_dir=str(scratch_dir),
            )

        return RawRunRecord(
            python_label=python_label,
            gil_label=gil_label,
            workload=workload,
            scenario=scenario,
            backend=spec["backend"],
            mode=spec["mode"],
            messages=messages,
            threads=thread_count,
            run_index=run_index,
            status="ok",
            throughput=round(raw_result["throughput"]),
            p50_us=round(raw_result["p50_us"], 1),
            p90_us=round(raw_result["p90_us"], 1),
            p99_us=round(raw_result["p99_us"], 1),
            scratch_dir=str(scratch_dir),
        )
    except Exception:
        return RawRunRecord(
            python_label=python_label,
            gil_label=gil_label,
            workload=workload,
            scenario=scenario,
            backend=spec["backend"],
            mode=spec["mode"],
            messages=messages,
            threads=thread_count,
            run_index=run_index,
            status="error",
            note=traceback.format_exc()[-1000:],
            scratch_dir=str(scratch_dir),
        )


def _invoke_worker_process(
    *,
    python_label: str,
    gil_label: str,
    target: str,
    scenario: str,
    workload: str,
    messages: int,
    threads: int,
    run_index: int,
    scratch_dir: Path,
    timeout_sec: int,
) -> RawRunRecord:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker-target",
        target,
        "--python-label",
        python_label,
        "--gil-label",
        gil_label,
        "--scenario",
        scenario,
        "--workload",
        workload,
        "--messages",
        str(messages),
        "--threads",
        str(threads),
        "--run-index",
        str(run_index),
        "--scratch-dir",
        str(scratch_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        spec = next(item for item in BACKEND_SPECS if item["target"] == target)
        return RawRunRecord(
            python_label=python_label,
            gil_label=gil_label,
            workload=workload,
            scenario=scenario,
            backend=spec["backend"],
            mode=spec["mode"],
            messages=messages,
            threads=1 if workload == "single" else threads,
            run_index=run_index,
            status="timeout",
            note=f"timed out after {timeout_sec}s",
            scratch_dir=str(scratch_dir),
        )

    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"worker exited with code {completed.returncode}"
        )
        spec = next(item for item in BACKEND_SPECS if item["target"] == target)
        return RawRunRecord(
            python_label=python_label,
            gil_label=gil_label,
            workload=workload,
            scenario=scenario,
            backend=spec["backend"],
            mode=spec["mode"],
            messages=messages,
            threads=1 if workload == "single" else threads,
            run_index=run_index,
            status="error",
            note=detail[-1000:],
            scratch_dir=str(scratch_dir),
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        spec = next(item for item in BACKEND_SPECS if item["target"] == target)
        return RawRunRecord(
            python_label=python_label,
            gil_label=gil_label,
            workload=workload,
            scenario=scenario,
            backend=spec["backend"],
            mode=spec["mode"],
            messages=messages,
            threads=1 if workload == "single" else threads,
            run_index=run_index,
            status="error",
            note=f"invalid worker JSON: {completed.stdout[-1000:]}",
            scratch_dir=str(scratch_dir),
        )

    return RawRunRecord(**payload)


def _summary_from_runs(raw_runs: list[RawRunRecord]) -> list[SummaryRow]:
    grouped: dict[tuple[str, str, str, str, str, str], list[RawRunRecord]] = {}
    for record in raw_runs:
        key = (
            record.python_label,
            record.gil_label,
            record.workload,
            record.scenario,
            record.backend,
            record.mode,
        )
        grouped.setdefault(key, []).append(record)

    rows: list[SummaryRow] = []
    for key, records in grouped.items():
        successful = [record for record in records if record.status == "ok"]
        status = "ok" if len(successful) == len(records) else "partial"
        if not successful:
            statuses = sorted({record.status for record in records})
            status = statuses[0] if len(statuses) == 1 else "error"
            note = "; ".join(
                f"run {record.run_index}: {record.status}{': ' + record.note if record.note else ''}"
                for record in records
            )
            rows.append(
                SummaryRow(
                    python_label=records[0].python_label,
                    gil_label=records[0].gil_label,
                    workload=records[0].workload,
                    scenario=records[0].scenario,
                    backend=records[0].backend,
                    mode=records[0].mode,
                    messages=records[0].messages,
                    threads=records[0].threads,
                    status=status,
                    successful_runs=0,
                    total_runs=len(records),
                    note=note,
                )
            )
            continue

        throughputs = [record.throughput for record in successful if record.throughput is not None]
        p50_values = [record.p50_us for record in successful if record.p50_us is not None]
        p90_values = [record.p90_us for record in successful if record.p90_us is not None]
        p99_values = [record.p99_us for record in successful if record.p99_us is not None]
        note = None
        if len(successful) != len(records):
            note = "; ".join(
                f"run {record.run_index}: {record.status}{': ' + record.note if record.note else ''}"
                for record in records
                if record.status != "ok"
            )

        rows.append(
            SummaryRow(
                python_label=records[0].python_label,
                gil_label=records[0].gil_label,
                workload=records[0].workload,
                scenario=records[0].scenario,
                backend=records[0].backend,
                mode=records[0].mode,
                messages=records[0].messages,
                threads=records[0].threads,
                status=status,
                successful_runs=len(successful),
                total_runs=len(records),
                throughput_avg=round(statistics.mean(throughputs)) if throughputs else None,
                throughput_min=min(throughputs) if throughputs else None,
                throughput_max=max(throughputs) if throughputs else None,
                p50_us=round(statistics.median(p50_values), 1) if p50_values else None,
                p90_us=round(statistics.median(p90_values), 1) if p90_values else None,
                p99_us=round(statistics.median(p99_values), 1) if p99_values else None,
                note=note,
            )
        )

    rows.sort(
        key=lambda row: (
            row.python_label,
            row.gil_label,
            row.workload,
            row.scenario,
            BACKEND_ORDER.index((row.backend, row.mode)),
        )
    )
    return rows


def _selected_values(choice: str, all_values: list[str]) -> list[str]:
    return all_values if choice == "all" else [choice]


def _run_runtime_matrix(args: argparse.Namespace) -> dict[str, Any]:
    workloads = _selected_values(args.workload, ["single", "multi"])
    scenarios = _selected_values(args.scenario, ["text", "json"])
    scratch_root = Path(args.scratch_root)

    raw_runs: list[RawRunRecord] = []
    for workload in workloads:
        for scenario in scenarios:
            for spec in BACKEND_SPECS:
                label = f"{spec['backend']} {spec['mode']} | {workload} | {scenario}"
                print(
                    f"[runtime {args.python_label} / GIL {args.gil_label}] {label}", file=sys.stderr
                )
                for run_index in range(1, args.repeat + 1):
                    scratch_dir = (
                        scratch_root
                        / f"py{_sanitize_component(args.python_label)}_gil_{_sanitize_component(args.gil_label)}"
                        / _sanitize_component(spec["backend"])
                        / spec["mode"]
                        / workload
                        / scenario
                        / f"run_{run_index:02d}"
                    )
                    if scratch_dir.exists():
                        shutil.rmtree(scratch_dir)
                    result = _invoke_worker_process(
                        python_label=args.python_label,
                        gil_label=args.gil_label,
                        target=spec["target"],
                        scenario=scenario,
                        workload=workload,
                        messages=args.messages,
                        threads=args.threads,
                        run_index=run_index,
                        scratch_dir=scratch_dir,
                        timeout_sec=args.worker_timeout,
                    )
                    raw_runs.append(result)
                    if result.status == "ok":
                        print(
                            f"  run {run_index}: {result.throughput:,} msg/s | "
                            f"p50={result.p50_us:.1f}us p90={result.p90_us:.1f}us p99={result.p99_us:.1f}us",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"  run {run_index}: {result.status}"
                            f"{': ' + result.note if result.note else ''}",
                            file=sys.stderr,
                        )

    summary_rows = _summary_from_runs(raw_runs)
    return {
        "runtime": _runtime_metadata(
            python_label=args.python_label,
            gil_label=args.gil_label,
            target_python=args.target_python,
        ),
        "configuration": {
            "messages": args.messages,
            "repeat": args.repeat,
            "threads": args.threads,
            "worker_timeout_sec": args.worker_timeout,
            "workloads": workloads,
            "scenarios": scenarios,
            "scratch_root": str(scratch_root),
        },
        "raw_runs": [asdict(item) for item in raw_runs],
        "summary_rows": [asdict(item) for item in summary_rows],
    }


def _invoke_runtime_process(
    *,
    python_label: str,
    gil_label: str,
    target_python: str,
    messages: int,
    repeat: int,
    threads: int,
    worker_timeout: int,
    workload: str,
    scenario: str,
    scratch_root: Path,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHON_GIL"] = GIL_ENV_MAP[gil_label]

    command = [
        "uv",
        "run",
        "--isolated",
        "--python",
        target_python,
        "--group",
        "benchmark",
        "--no-dev",
        "python",
        "benchmarks/run_benchmark.py",
        "--runtime-run",
        "--python-label",
        python_label,
        "--gil-label",
        gil_label,
        "--target-python",
        target_python,
        "--messages",
        str(messages),
        "--repeat",
        str(repeat),
        "--threads",
        str(threads),
        "--worker-timeout",
        str(worker_timeout),
        "--workload",
        workload,
        "--scenario",
        scenario,
        "--scratch-root",
        str(scratch_root),
    ]

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"command failed: {completed.returncode}"
        )
        raise RuntimeError(detail[-2000:])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid runtime JSON: {completed.stdout[-2000:]}") from exc


def _combined_summary_payload(
    *,
    session: str,
    messages: int,
    repeat: int,
    threads: int,
    worker_timeout: int,
    scratch_root: Path,
    python_versions: list[str],
    gil_states: list[str],
    workloads: list[str],
    scenarios: list[str],
    env_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    combined_rows: list[dict[str, Any]] = []
    environments: list[dict[str, Any]] = []
    raw_files: dict[str, str] = {}

    for env_output in env_outputs:
        environments.append(env_output["runtime"])
        combined_rows.extend(env_output["summary_rows"])

    return {
        "session": session,
        "generated_at_utc": _utc_now(),
        "configuration": {
            "messages": messages,
            "repeat": repeat,
            "threads": threads,
            "worker_timeout_sec": worker_timeout,
            "scratch_root": str(scratch_root),
            "python_versions": python_versions,
            "gil_states": gil_states,
            "workloads": workloads,
            "scenarios": scenarios,
        },
        "environments": environments,
        "summary_rows": combined_rows,
        "raw_files": raw_files,
    }


def _run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    session = args.session or datetime.now(timezone.utc).strftime("benchmark_%Y%m%d_%H%M%S")
    results_dir = RESULTS_ROOT / session
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=False)

    scratch_root = Path(args.scratch_root) / session
    scratch_root.mkdir(parents=True, exist_ok=True)

    python_versions = _selected_values(args.python_version, ["3.13", "3.14"])
    gil_states = _selected_values(args.gil, ["enabled", "disabled"])
    workloads = _selected_values(args.workload, ["single", "multi"])
    scenarios = _selected_values(args.scenario, ["text", "json"])
    env_outputs: list[dict[str, Any]] = []
    raw_rel_paths: dict[str, str] = {}

    python_target_map = {
        "3.13": args.python313,
        "3.14": args.python314,
    }

    for python_label in python_versions:
        for gil_label in gil_states:
            target_python = python_target_map[python_label]
            env_key = f"py{python_label.replace('.', '')}_gil_{gil_label}"
            print(
                f"[matrix] Python {python_label} / GIL {gil_label} via {target_python}",
                file=sys.stderr,
            )
            env_output = _invoke_runtime_process(
                python_label=python_label,
                gil_label=gil_label,
                target_python=target_python,
                messages=args.messages,
                repeat=args.repeat,
                threads=args.threads,
                worker_timeout=args.worker_timeout,
                workload=args.workload,
                scenario=args.scenario,
                scratch_root=scratch_root,
            )
            env_outputs.append(env_output)
            raw_path = raw_dir / f"{env_key}.json"
            raw_path.write_text(json.dumps(env_output, indent=2), encoding="utf-8")
            raw_rel_paths[env_key] = raw_path.relative_to(REPO_ROOT).as_posix()

    summary = _combined_summary_payload(
        session=session,
        messages=args.messages,
        repeat=args.repeat,
        threads=args.threads,
        worker_timeout=args.worker_timeout,
        scratch_root=scratch_root,
        python_versions=python_versions,
        gil_states=gil_states,
        workloads=workloads,
        scenarios=scenarios,
        env_outputs=env_outputs,
    )
    summary["raw_files"] = raw_rel_paths
    summary_path = results_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    session_markdown_path = results_dir / "summary.md"
    session_markdown_path.write_text(
        render_single_session_markdown(summary, raw_rel_paths),
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the D-SafeLogger benchmark matrix")
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES)
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument("--worker-timeout", type=int, default=DEFAULT_WORKER_TIMEOUT_SEC)
    parser.add_argument("--workload", choices=["single", "multi", "all"], default="all")
    parser.add_argument("--scenario", choices=["text", "json", "all"], default="all")
    parser.add_argument("--python-version", choices=["3.13", "3.14", "all"], default="all")
    parser.add_argument("--gil", choices=["enabled", "disabled", "all"], default="all")
    parser.add_argument("--scratch-root", default=str(DEFAULT_SCRATCH_ROOT))
    parser.add_argument("--session")
    parser.add_argument("--python313", default=DEFAULT_PYTHON_313)
    parser.add_argument("--python314", default=DEFAULT_PYTHON_314)
    parser.add_argument("--json", action="store_true", help="Print matrix summary JSON to stdout")

    parser.add_argument("--runtime-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--python-label", default="")
    parser.add_argument("--gil-label", default="")
    parser.add_argument("--target-python", default="")

    parser.add_argument("--worker-target", choices=sorted(WORKER_FUNCTIONS.keys()))
    parser.add_argument("--run-index", type=int, default=1)
    parser.add_argument("--scratch-dir", default="")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.messages < 1:
        raise ValueError("--messages must be >= 1")
    if args.repeat < 1:
        raise ValueError("--repeat must be >= 1")
    if args.threads < 1:
        raise ValueError("--threads must be >= 1")
    if args.worker_timeout < 1:
        raise ValueError("--worker-timeout must be >= 1")

    if args.worker_target:
        if not args.python_label or not args.gil_label:
            raise ValueError("--worker-target requires --python-label and --gil-label")
        if not args.scratch_dir:
            raise ValueError("--worker-target requires --scratch-dir")
        result = _worker_once(
            python_label=args.python_label,
            gil_label=args.gil_label,
            target=args.worker_target,
            scenario=args.scenario,
            workload=args.workload,
            messages=args.messages,
            threads=args.threads,
            run_index=args.run_index,
            scratch_dir=Path(args.scratch_dir),
        )
        print(json.dumps(asdict(result)))
        return

    if args.runtime_run:
        if not args.python_label or not args.gil_label or not args.target_python:
            raise ValueError(
                "--runtime-run requires --python-label, --gil-label, and --target-python"
            )
        payload = _run_runtime_matrix(args)
        print(json.dumps(payload))
        return

    summary = _run_matrix(args)
    if args.json:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
