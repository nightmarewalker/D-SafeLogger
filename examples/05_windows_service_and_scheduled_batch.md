# Windows Service and Scheduled Batch Logging

D-SafeLogger's append-only routing is useful for long-running Windows services
and scheduled batch jobs because the active log file is not renamed or truncated
by D-SafeLogger during routing.

This guide does not install a real Windows service and does not require pywin32,
NSSM, Task Scheduler APIs, or Service Control Manager access. It simulates the
two common shapes: a service-style loop and a scheduled batch run.

## The Problem

Rename-based rotation can fail when another process still has the active log
file open. This is especially visible on Windows, where active file handles
commonly block rename or delete operations.

D-SafeLogger avoids that rotation model. At a routing boundary, it opens the
next destination file and continues writing there.

## Append-Only Routing Model

For size-based routing:

The small `max_bytes` values in this guide are demonstration values so routing is easy to observe.
Production deployments typically use values in the megabyte range.

```python
ConfigureLogger(
    log_path="./logs/windows-job",
    pg_name="WinBatch",
    routing_mode="size",
    max_bytes=512,
)
```

The files are named like `WinBatch_00.log`, `WinBatch_01.log`, and so on. The
active file is not renamed into an archive name.

## Service-Style Setup

A service usually has a long-lived process and repeated work items. Configure
logging once when the process starts, then keep normal `logger.info()` calls in
the service loop.

## Scheduled Batch Setup

A scheduled batch job usually starts, processes a bounded set of items, and
exits. The same logging configuration works for that case; shutdown closes the
current sink cleanly.

## Emergency Environment Overrides

Use environment variables for operational overrides when you cannot rebuild or
edit the deployment package. For example, `D_LOG_LEVEL=DEBUG` can raise runtime
verbosity before `ConfigureLogger()` runs.

## Complete Runnable Example

The tested scenario for this guide is maintained in
`tests/examples/test_05_windows_service_and_scheduled_batch.py`.

```python
"""windows_service_and_scheduled_batch.py"""

from pathlib import Path

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown


def run_service_iteration(logger, item: int) -> None:
    logger.info("service heartbeat", extra={"item": item})


def run_scheduled_batch(logger) -> None:
    for item in range(8):
        logger.info("processed scheduled item", extra={"item": item})


def main() -> None:
    log_dir = Path("./logs/windows-job")
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="WinBatch",
        console_out=False,
        routing_mode="size",
        max_bytes=160,
        suffix_digits=2,
    )

    logger = GetLogger("windows.job")
    for item in range(4):
        run_service_iteration(logger, item)
    run_scheduled_batch(logger)

    SafeShutdown()
    print(f"routed files: {sorted(p.name for p in log_dir.glob('WinBatch_*.log'))}")


if __name__ == "__main__":
    main()
```

## How to Run

```bash
python windows_service_and_scheduled_batch.py
```

For repository validation, run the maintained scenario test:

```bash
uv run pytest tests/examples/test_05_windows_service_and_scheduled_batch.py -q
```

## What to Check

- multiple `WinBatch_*.log` files are created when the size boundary is crossed;
- there is no rename-based `WinBatch.log -> WinBatch.log.1` pattern;
- the example runs on non-Windows too, while the operational motivation is
  Windows file-lock safety.

## What's Next

- [Web API Logging](06_web_api_logging.md)
- [Long-Running Service Logging](07_long_running_service.md)
