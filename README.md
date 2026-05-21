# D-SafeLogger

[![CI](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml/badge.svg)](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/d-safelogger.svg?cacheSeconds=3600)](https://pypi.org/project/d-safelogger/)
[![Python](https://img.shields.io/pypi/pyversions/d-safelogger.svg?cacheSeconds=3600)](https://pypi.org/project/d-safelogger/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#main-features)

Languages: [English](README.md) | [日本語](README_ja.md)

## Overview

D-SafeLogger is a zero-dependency, stdlib logging-compatible logger built on Python's standard `logging` module.

It extends the standard logging path instead of replacing it. Existing `logging.getLogger()` and `logger.info()` call sites can participate without modification, while D-SafeLogger adds append-only file routing, structured JSON Lines output, contextual logging, SHA-256 sidecars, environment-based operational overrides, and Writer-owned multiprocess logging.

Append-only routing means D-SafeLogger opens the next destination file instead of renaming or truncating the active log file. This avoids the common Windows file-lock failure mode of rename-based rotation. It also sidesteps the POSIX failure mode where a rename succeeds at the filesystem layer while existing file descriptors keep writing to the previous file.

The "Safe" in the name refers to operational safety: fail-fast setup, append-only file handling, producer-side context snapshots, bounded queues, explicit timeouts, and classified delivery-state accounting.

## Installation

```bash
pip install d-safelogger
```

The distribution name is `d-safelogger`; the import name is `dsafelogger`.

D-SafeLogger requires Python 3.11 or newer.

## Quick Start

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path="./logs", pg_name="MyApp")

logger = GetLogger(__name__)
logger.info("Application started")
```

`pg_name` is the application name used as the prefix of routed log file names, for example `MyApp_20260403.log`.

Typical text output:

```text
2026-04-03 09:15:22.738 [INF][app.py:6:<module>] Application started
```

To emit JSON Lines instead, set `structured=True` at configure time:

```python
ConfigureLogger(log_path="./logs", pg_name="MyApp", structured=True)
logger = GetLogger(__name__)
logger.info("Application started")
```

```jsonl
{"timestamp":"2026-04-03 09:15:22.738","level":"INF","logger":"__main__","message":"Application started"}
```

For multiprocess setup, see [Multiprocess Logging](#multiprocess-logging). For INI configuration, request context, integrity sidecars, async logging, and CLI usage, see [Tutorials / Examples](#tutorials--examples).

Configuration is fail-fast. D-SafeLogger rejects feature combinations that cannot take effect, such as cyclic routing with hash/archive retention, `routing_mode='none'` with D-SafeLogger-owned retention, or `structured=True` with custom formatter strings.

## When to Use It

Use D-SafeLogger when you want to keep standard `logging.getLogger()` call sites while adding:

- append-only local file routing,
- environment-driven operational overrides,
- optional SHA-256 sidecars and manifests,
- Writer-owned multiprocess file output,
- classified delivery-state accounting.

You probably do not need it if your application only writes to stdout/stderr and an external collector owns routing, retention, aggregation, and durability.

## Why D-SafeLogger?

D-SafeLogger extends the standard logging path rather than replacing it: you keep using `logging.getLogger()` and existing `logger.info()` call sites, and the library adds safe local-file output on top: rename-free append-only routing, fail-fast configuration, SHA-256 sidecars, sensitive-data masking, environment-driven operational control, and a parent-side multiprocess Writer.

If you already use `structlog` as a structured-logging frontend, D-SafeLogger coexists rather than replaces. `structlog` builds the event dictionary; D-SafeLogger handles file output, routing, sidecars, masking, and operational control. See [Structlog Coexistence](examples/16_structlog_coexistence.md) for two integration patterns.

## Why Routing Instead of External Rotation?

External rotation typically renames or truncates an active log file, creates a replacement, and asks the application to reopen its sink. That is plumbing for a design that mutates the active file after the fact, not the core of writing log records.

On POSIX systems, the rename can succeed even while the writer keeps writing through the old file descriptor. The filesystem call returned success, but the logger never actually moved to the new file.

D-SafeLogger avoids that dependency by choosing the destination at write time. It opens the next destination at the routing boundary instead of mutating the active file and relying on a signal/reopen handshake.

## What "Safe" Means

The "Safe" in the name is a design stance that runs across several dimensions of everyday operation, not only failure handling:

- **Startup safety:** invalid settings, inconsistent options, and unwritable destinations fail during setup. D-SafeLogger stops a broken logging configuration before the application starts doing real work, instead of silently degrading later.
- **File safety:** the routing layer opens the next destination instead of renaming or truncating the active log file, which avoids the common Windows failure mode where active log files cannot be renamed. It also avoids the POSIX case where a successful rename leaves the writer appending to the previous file. Routed files can be paired with SHA-256 sidecars and an optional manifest, so log content is verifiable after the fact.
- **Record and context safety:** request IDs, user IDs, job IDs, and other context are snapshotted on the producer side at hand-off, so listeners and Writers do not depend on live `contextvars`. Diagnostic local-variable snapshots and Writer-side formatting use the sensitive-keyword set established at configure time.
- **Operational control:** environment variables provide explicit runtime overrides for diagnostics, routing, hashing, log levels, and queue/timeout behavior without rebuilding or editing application code.
- **Concurrency and multiprocess safety:** multiprocess workers do not open the shared log files themselves. A parent-side Writer owns the sinks and accepts records over IPC, with bounded queues and explicit timeouts that keep the host process from unbounded waits.
- **Failure observability:** when records cannot be delivered, the runtime classifies the outcome where it can: `KnownRejected`, `KnownDropped`, or `UnexplainedLost`. Counters and shutdown summaries make abnormal scenarios describable rather than silent.
- **Filesystem scope:** append-only routing avoids external rename/truncate of active log files. It does not make every destination filesystem equally safe. NFS, SMB/CIFS, FUSE mounts, cloud-synced folders, container bind mounts, and in-memory filesystems can have different rename, unlink, cache, durability, or lifetime semantics. For audit-oriented deployments, prefer writing active logs to a durable local filesystem and transferring closed routed files to archive or network storage.

## Feature Comparison

This table is not an overall ranking. It shows which concerns each project treats as part of its built-in design.

Legend:

- **◎** primary strength / design centerpiece
- **○** supported out of the box
- **△** officially supported through configuration or adapters, with limited scope
- **—** not provided as a library feature
- **※n** see note for scope or conditions

| Capability | stdlib `logging` | loguru | structlog | D-SafeLogger |
|---|:---:|:---:|:---:|:---:|
| Stdlib `logging` API compatibility | ◎ | △※2 | △※3 | ◎ |
| Existing `logger.info()` / `getLogger()` call sites preserved | ◎ | △※2 | △※3 | ◎ |
| Third-party libraries using `logging.getLogger()` participate | ◎ | △※2 | △※3 | ◎ |
| Zero external runtime dependencies | ◎ | — | — | ◎ |
| Centralized setup replacing handler/formatter wiring | △※1 | ◎ | △※3 | ◎ |
| Text file logging | ○ | ○ | △※3 | ○ |
| Structured JSON Lines | —※1 | ○ | ◎ | ○ |
| Context propagation | △※1 | ○ | ◎ | ○ |
| Fail-fast configuration validation | △※4 | △※4 | △※4 | ◎ |
| Append-only file routing without rename/truncate | —※5 | —※6 | —※3 | ◎ |
| Purge / archive maintenance for routed files | —※5 | ○※6 | —※3 | ○ |
| SHA-256 sidecars / manifest output | — | — | —※3 | ◎ |
| Code / INI-dict / environment configuration layers | △※1 | △※7 | △※7 | ○ |
| Environment-only diagnostic mode | — | —※8 | — | ◎ |
| Async hand-off with context snapshot | △※1 | ○※9 | △※3 | ○ |
| Multiprocess file output via parent-side Writer | —※10 | —※9 | —※3 | ◎ |
| Delivery-state accounting (multiprocess) | — | — | — | ◎ |

Notes:

- **※1** stdlib `logging` provides primitives such as handlers, filters, formatters, `dictConfig`, `QueueHandler`, and `QueueListener`; JSON formatting, context policy, layered environment handling, and end-to-end validation require application composition or custom classes.
- **※2** loguru can coexist with stdlib logging through documented handler patterns, but it is primarily a replacement-style logger API rather than native stdlib API compatibility.
- **※3** structlog is primarily a structured-logging frontend. It integrates with stdlib logging and selected output backends, but file lifecycle, retention, integrity sidecars, and multiprocess sink ownership are backend or application responsibilities.
- **※4** these projects validate parts of their own configuration, but D-SafeLogger treats merged configuration, writable destinations, and safety invariants as a startup contract.
- **※5** stdlib rotation handlers are not append-only rerouting facilities; rename-free routing and routed-file maintenance require custom handlers or external operational tooling. On POSIX systems, a successful rename can still leave the writer attached to the previous file descriptor, so filesystem-level rotation success does not guarantee that new records are going to the new file.
- **※6** loguru provides built-in rotation, retention, and compression, but not D-SafeLogger-style append-only rerouting that avoids renaming or truncating the active file. D-SafeLogger avoids the pattern where an active file is changed first and correctness depends on a later reopen.
- **※7** loguru and structlog support code-based configuration and selected defaults; D-SafeLogger's explicit code / INI-dict / environment precedence model is a separate built-in configuration layer.
- **※8** loguru provides rich exception diagnostics, but D-SafeLogger's diagnostic mode is intentionally environment-only as a safety boundary.
- **※9** loguru's `enqueue=True` provides queued, multiprocessing-safe logging, but it is not a parent-side Writer ownership model and does not expose D-SafeLogger-style delivery-state accounting.
- **※10** stdlib logging can be assembled into a listener/queue architecture, but this is not a packaged parent-side Writer API.

**Delivery-state accounting** refers to per-record classification (`KnownRejected`, `KnownDropped`, `UnexplainedLost`) exposed through counters and shutdown summaries. See [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md) and [BENCHMARK.md](BENCHMARK.md).

## Main Features

- **Zero runtime dependencies:** the package uses only the Python standard library at runtime.
- **Stdlib logging compatibility:** existing `logger.info()` calls and libraries that use `logging.getLogger()` participate in the same logging setup.
- **Centralized setup:** replace common `basicConfig()`, `dictConfig()`, formatter, handler, and rotating-file boilerplate with `ConfigureLogger()`.
- **Fail-fast initialization:** invalid configuration and unwritable log destinations fail during setup instead of degrading silently.
- **Append-only file routing:** the routing layer opens the next destination instead of renaming or truncating the active log file. This avoids the common Windows failure mode where active log files cannot be renamed, and it avoids the POSIX case where a writer may continue writing to the previous file after a successful rename.
- **Retention for routed files:** routed files can be kept by `backup_count`; older files can be deleted by the purge worker or ZIP-archived with `archive_mode=True`.
- **Classified delivery state:** loss, reject, and drop events are not treated as invisible file gaps. When records cannot be delivered, the runtime classifies the outcome as known-rejected, known-dropped, or unexplained-lost where applicable.
- **Bounded logging path:** D-SafeLogger uses bounded queues, explicit timeouts, and explicit rejection paths to avoid unbounded logging-side waits in the host process.
- **Structured JSON Lines:** emit log records as JSON fields for log collectors and observability pipelines.
- **Contextual logging:** attach request IDs, user IDs, job IDs, or other context with thread-safe and async-safe propagation. Producer-side context snapshots are taken at hand-off so listeners and Writers do not look up live `contextvars`.
- **Integrity sidecars:** generate SHA-256 sidecars and optional manifest entries for routed log files. This is tamper-evidence for closed files, not an access-control or compliance system.
- **Operational overrides:** change log level, module routing, console output, color, hashing, config file path, and queue/timeout parameters through environment variables, typically to raise diagnostics in production without code changes.
- **Environment-only diagnostic mode:** opt in via `D_LOG_DIAGNOSE=1` for `f_locals` expansion of selected frames; deliberately not exposed through INI or arguments, so it cannot be enabled by an unowned configuration file.
- **Async transport:** opt in to queue-backed logging when application threads should avoid direct sink writes.
- **Custom log levels:** `register_level()` to add named levels alongside the built-in five before `ConfigureLogger()`.
- **External rotation reopen:** `ReopenLogFiles()` and its multiprocess equivalent reopen sinks after external log rotators such as `logrotate`.
- **Delivery-state visibility (multiprocess):** worker logging exposes per-record delivery-state counters and shutdown summaries, so abnormal shutdowns, sink unavailability, and worker crashes are described rather than silent.

## Multiprocess Logging

`dsafelogger.mp` is for applications where multiple worker processes need to send logs to shared destinations without each worker independently opening the same files.

In this mode, a parent-side Writer owns the file sinks. Workers attach to the Writer and submit log records through IPC. This centralizes file ownership and exposes delivery-state counters such as accepted, delivered, rejected, dropped, and unexplained-lost.

The Writer shutdown path is bounded: it attempts to drain and join within a timeout, emits a visible warning if drain is incomplete, and avoids hanging the host process indefinitely.

For setup code, the `multiprocessing` context rules, pool initializer, `ProcessPoolExecutor` integration, Windows spawn caveats, custom log levels, attach/detach lifecycle, environment-variable knobs, and shutdown handling, see [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md).

Public API in `dsafelogger.mp`: `ConfigureLogger`, `AttachCurrentProcess`, `DetachCurrentProcess`, `GetLogger`, `GetWorkerInitializer`, `ReopenLogFiles`.

## Configuration

D-SafeLogger combines three configuration layers:

| Layer | Purpose |
|---|---|
| Code | Application defaults passed to `ConfigureLogger()` |
| INI or dict | Deployment configuration without changing application code |
| Environment variables | Operational and emergency overrides |

Common environment overrides, using the default `D_LOG_*` prefix; the prefix is configurable through `ConfigureLogger(env_prefix=...)`:

- Single-process: `D_LOG_LEVEL`, `D_LOG_MODULES`, `D_LOG_CONFIG`, `D_LOG_DIAGNOSE`, `D_LOG_CONSOLE`, `D_LOG_COLOR`, `D_LOG_HASH`, `D_LOG_MANIFEST`, plus the industry-standard `NO_COLOR`, which is not affected by `env_prefix`.
- Multiprocess (`dsafelogger.mp`): `D_LOG_IPC_LOG_TIMEOUT`, `D_LOG_IPC_LOG_QUEUE_MAXSIZE`, `D_LOG_IPC_CLIENT_QUEUE_MAXSIZE`, `D_LOG_WRITER_FLUSH_BATCH`. These tune backpressure behavior and are normally left at defaults.

See [Configuration Guide](examples/02_configuration_guide.md) for INI files, dict configuration, module-specific routing, and precedence rules.

## Tutorials / Examples

Suggested reading paths:

- **Getting started:** 01, 02, 03
- **Stdlib and ecosystem integration:** 03, 04, 15, 16
- **Windows and service operations:** 05, 07, 13, 14
- **Application patterns:** 06, 10, 11, 17
- **Audit and incident response:** 08, 09, 10
- **Multiprocess logging:** 12

| # | Guide | Topic |
|---|---|---|
| 1 | [Quick Start](examples/01_quick_start.md) | Install, configure, and write the first log |
| 2 | [Configuration Guide](examples/02_configuration_guide.md) | Code, INI/dict, and environment configuration |
| 3 | [Migrating from stdlib](examples/03_migration_from_stdlib.md) | Migration from standard-library logging |
| 4 | [Stdlib Ecosystem Coexistence](examples/04_stdlib_ecosystem_coexistence.md) | Collect logs from existing stdlib-based libraries |
| 5 | [Windows Service and Scheduled Batch](examples/05_windows_service_and_scheduled_batch.md) | Append-only files for Windows services and scheduled jobs |
| 6 | [Web API Logging](examples/06_web_api_logging.md) | Request-correlated structured logs |
| 7 | [Long-Running Service](examples/07_long_running_service.md) | Routing, retention, and archival |
| 8 | [Compliance & Audit Logging](examples/08_compliance_audit.md) | SHA-256 integrity files and audit logs |
| 9 | [Debugging in Production](examples/09_debugging_production.md) | Diagnostic mode and masking |
| 10 | [Incident Response Bundle](examples/10_incident_response_bundle.md) | Gather structured logs, diagnostics, hashes, and manifests |
| 11 | [Async & High Throughput](examples/11_async_performance.md) | Queue-backed async logging |
| 12 | [Multiprocess Logging](examples/12_multiprocess_logging.md) | Worker logging through a parent-side Writer |
| 13 | [External Rotation and Reopen](examples/13_external_rotation_reopen.md) | Reopening files after external rotation |
| 14 | [CLI Operations](examples/14_cli_operations.md) | `dsafelogger` command usage |
| 15 | [OpenTelemetry Logging](examples/15_opentelemetry_logging.md) | Trace correlation with stdlib instrumentation |
| 16 | [Structlog Coexistence](examples/16_structlog_coexistence.md) | Using structlog alongside D-SafeLogger |
| 17 | [Container and Collector Coexistence](examples/17_container_collector_coexistence.md) | Write local JSONL while external collectors ship logs |

## Benchmarks

D-SafeLogger is competitive in the selected single-process async benchmark runs. In multiprocess benchmarks, raw throughput is not the differentiator; parent-side file output and classified delivery-state accounting are.

The benchmark suite also includes multiprocess resilience profiles, such as sink-unavailable, burst backpressure, worker crash, mixed worker behavior, and shutdown behavior. These runs are not throughput claims; they check whether attempted records can be accounted for as delivered, known-rejected, known-dropped, or unexplained-lost.

See [BENCHMARK.md](BENCHMARK.md) for the selected runs, methodology, and the explicit "what to claim / what not to claim" boundaries, and [`benchmarks/summary/`](benchmarks/summary/) for the published summaries.

## Testing / Quality

The release gate runs the full dev test suite across Windows, macOS, and Linux on Python 3.11-3.14. CI also runs Ubuntu free-threaded CPython `3.13t` and `3.14t` compatibility jobs with `PYTHON_GIL=0`. Publication checks also verify generated API docs, public design documents, benchmark summaries, and package build output.

See [TESTING.md](TESTING.md) for details.

## Compatibility / Non-goals

- Python: 3.11 or newer.
- OS: Windows, macOS, and Linux.
- Runtime dependencies: none.
- Typing: includes `py.typed`; CI checks `mypy`, `pyright`, typing smoke tests, and 100% public type completeness with `pyright --verifytypes`. See [TESTING.md](TESTING.md).
- API docs: [`docs/api/`](docs/api/).
- Design docs: [`docs/design/`](docs/design/).
- Distribution name is `d-safelogger` (with hyphen); import name is `dsafelogger` (no separator).

D-SafeLogger is not a log shipper, metrics pipeline, distributed tracing backend, or access-control system. Use tools such as Fluent Bit, Vector, Filebeat, OpenTelemetry Collector, or a tracing backend for those roles.

For vulnerability reporting, see [SECURITY.md](SECURITY.md).

## Design Documents

For deeper architectural rationale and specification details, see:

- [Architecture Analysis White Paper](docs/design/D-SafeLogger_v23j_WhitePaper_en.md)
- [Basic Design Specification](docs/design/D_SafeLogger_Specification_v23j_full_en.md)
- [API Reference](docs/api/index.md)

Japanese design documents are also available under [`docs/design/`](docs/design/).

## License

Apache License 2.0. See [LICENSE](LICENSE).

© D-SafeLogger contributors
