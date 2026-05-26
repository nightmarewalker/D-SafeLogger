# D-SafeLogger

[![CI](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml/badge.svg)](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/d-safelogger.svg?cacheSeconds=3600)](https://pypi.org/project/d-safelogger/)
[![Python](https://img.shields.io/pypi/pyversions/d-safelogger.svg?cacheSeconds=3600)](https://pypi.org/project/d-safelogger/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#highlights)

Languages: [English](README.md) | [日本語](README_ja.md)

D-SafeLogger is a zero-dependency, stdlib logging-compatible logger built on Python's standard `logging` module.

It extends the standard logging path instead of replacing it, so existing application code and third-party library logs can stay on the stdlib logging path. It is intended for Python applications that need local file logging to start small in development and become explicit, inspectable, and operationally controlled for services, scheduled jobs, audit-oriented logs, and multiprocess workers.

## Highlights

1. **Stdlib `logging` compatible.** Existing `logger.info()` call sites and third-party libraries using `logging.getLogger()` participate without modification.

2. **Append-only routing, no rename.** D-SafeLogger opens the next destination file instead of renaming or truncating the active log. This avoids the Windows file-lock failure mode of rename-based rotation and the POSIX case where a successful rename can leave the writer attached to the previous file descriptor.

3. **Zero runtime dependencies.** The runtime package uses only the Python standard library. No extra runtime dependency chain is added to your application.

4. **Start in three lines, add policy through configuration.** A minimal setup is three lines. The same call sites can stay in place while configuration adds 9 routing strategies (`daily`, `hourly`, `size`, and more), JSON Lines, SHA-256 sidecars and manifests, sensitive-keyword masking, diagnostic mode, and code / INI-dict / environment deployment layers.

5. **Robust multiprocess file logging.** A parent-side Writer owns file writes, so workers do not open shared log files directly. Rejected, dropped, or unaccounted-for records are surfaced explicitly instead of becoming unexplained missing lines.

## When to Use It

Use D-SafeLogger when you want to keep standard `logging.getLogger()` call sites while adding:

- append-only local file routing,
- environment-driven operational overrides,
- optional SHA-256 sidecars and manifests,
- Writer-owned multiprocess file output,
- classified delivery-state accounting.

You probably do not need it if your application only writes to stdout/stderr and an external collector owns routing, retention, aggregation, and durability.

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

`pg_name` is the application name used as the log file prefix (`MyApp.log` here; with daily routing this becomes `MyApp_20260403.log`).

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

## Why D-SafeLogger?

D-SafeLogger extends the standard logging path rather than replacing it: you keep using `logging.getLogger()` and existing `logger.info()` call sites, and the library adds safe local-file output on top.

That matters when an application already has stdlib logging calls, or depends on libraries that emit through `logging.getLogger()`. D-SafeLogger lets those records enter the same routing, formatting, context, integrity, async, and multiprocess Writer path without forcing a new application-wide logging API.

If you already use `structlog` as a structured-logging frontend, D-SafeLogger coexists rather than replaces it. `structlog` builds the event dictionary; D-SafeLogger handles file output, routing, sidecars, masking, and operational control. See [Structlog Coexistence](examples/16_structlog_coexistence.md) for two integration patterns.

## Why Routing Instead of External Rotation?

External rotation typically renames or truncates an active log file, creates a replacement, and asks the application to reopen its sink. That is plumbing for a design that mutates the active file after the fact, not the core of writing log records.

On Windows, active-file rename can fail because the writer still holds the file. On POSIX systems, the rename can succeed while the writer keeps writing through the old file descriptor. The filesystem call returned success, but the logger never actually moved to the new file.

D-SafeLogger avoids that dependency by choosing the destination at write time. It opens the next destination at the routing boundary instead of mutating the active file and relying on a signal/reopen handshake.

## What "Safe" Means

"Safe" is not a promise that every record survives every possible failure. It is a design stance for reducing avoidable logging failures and making observable failures explainable.

| Dimension | Meaning |
|---|---|
| Startup safety | Invalid settings, inconsistent options, and unwritable destinations fail during setup before the application starts doing real work. |
| File safety | Routed log files are treated as append-only artifacts with an explicit lifecycle: active writing, closed routed file, optional SHA-256 sidecar, optional manifest, and downstream transfer or archive. Integrity support is for closed-file verification, not access control. |
| Record and context safety | Context is snapshotted on the producer side at hand-off; diagnostics and Writer-side formatting use the sensitive-keyword set established at configure time. |
| Operational control | Runtime overrides are intentionally explicit and operator-owned. Log levels, routing, hashing, and timeout behavior can be changed without rebuilding, while diagnostic local-variable expansion is limited to environment-variable opt-in and cannot be enabled by an unowned INI file. |
| Concurrency and multiprocess safety | Cross-thread and cross-process logging paths use bounded queues, explicit timeouts, rejection/drop paths, and shutdown drain limits. The design favors hard ceilings over indefinite waiting. |
| Delivery visibility | Abnormal delivery outcomes remain visible through `mp.GetDeliveryStatus()`, runtime warning JSON Lines, and shutdown report JSON. Even `UnexplainedLost` is preserved as an explicit state, so abnormal runs do not collapse into “the file is just shorter than expected.” |

Append-only routing avoids external rename/truncate of active log files. It does not make every destination filesystem equally safe. NFS, SMB/CIFS, FUSE mounts, cloud-synced folders, container bind mounts, and in-memory filesystems can have different rename, unlink, cache, durability, or lifetime semantics. For audit-oriented deployments, prefer writing active logs to a durable local filesystem and transferring closed routed files to archive or network storage.

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

**Delivery-state accounting** refers to per-record classification (`KnownRejected`, `KnownDropped`, `UnexplainedLost`, plus `partial_delivered`) exposed through `mp.GetDeliveryStatus()`, runtime warning JSON Lines, and shutdown report JSON. See [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md), [`docs/design/v23k_supplements/delivery_status_schema.md`](docs/design/v23k_supplements/delivery_status_schema.md), and [BENCHMARK.md](BENCHMARK.md).

## Multiprocess Logging

`dsafelogger.mp` is for applications where multiple worker processes need to send logs to shared destinations without each worker independently opening the same files.

In this mode, a parent-side Writer owns the file sinks. Workers attach to the Writer and submit log records through IPC. This centralizes file ownership and exposes delivery-state counters such as attempted, accepted, delivered, partial-delivered, known-rejected, known-dropped, and unexplained-lost.

The public API is designed for three common worker patterns: `multiprocessing.Process`, `multiprocessing.Pool`, and `concurrent.futures.ProcessPoolExecutor`. The same Writer session can be bootstrapped into each pattern through explicit attach calls or the `GetWorkerInitializer()` helper used by pools and executors.

The Writer shutdown path is bounded: it attempts to drain and join within a timeout, records runtime warnings when configured, writes a shutdown report when configured, and avoids hanging the host process indefinitely.

For setup code, the `multiprocessing` context rules, pool initializer, `ProcessPoolExecutor` integration, Windows spawn caveats, custom log levels, attach/detach lifecycle, environment-variable knobs, and shutdown handling, see [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md).

Public API in `dsafelogger.mp`: `ConfigureLogger`, `AttachCurrentProcess`, `DetachCurrentProcess`, `GetLogger`, `GetWorkerInitializer`, `GetDeliveryStatus`, `DeliveryStatus`, `ReopenLogFiles`.

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

See [Configuration Guide](examples/02_configuration_guide.md) for INI files, dict configuration, module-specific routing, and precedence rules. For routing-mode selection, purge/archive retention, and long-running file lifecycle examples, see [Long-Running Service](examples/07_long_running_service.md).

## Tutorials / Examples

Suggested reading paths:

- **Getting started:** 01, 02, 03
- **Stdlib and ecosystem integration:** 03, 04, 15, 16, 18, 19, 20
- **Runtime ownership and GUI:** 17, 21, 23
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
| 9 | [Diagnostic Debugging](examples/09_debugging_production.md) | Diagnostic mode for development, staging, and production troubleshooting, with local-variable snapshots and masking |
| 10 | [Incident Response Bundle](examples/10_incident_response_bundle.md) | Gather structured logs, diagnostics, hashes, and manifests |
| 11 | [Async & High Throughput](examples/11_async_performance.md) | Queue-backed async logging |
| 12 | [Multiprocess Logging](examples/12_multiprocess_logging.md) | Worker logging through a parent-side Writer |
| 13 | [External Rotation and Reopen](examples/13_external_rotation_reopen.md) | Reopening files after external rotation |
| 14 | [CLI Operations](examples/14_cli_operations.md) | `dsafelogger` command usage |
| 15 | [OpenTelemetry Logging](examples/15_opentelemetry_logging.md) | Trace correlation with stdlib instrumentation |
| 16 | [Structlog Coexistence](examples/16_structlog_coexistence.md) | Using structlog alongside D-SafeLogger |
| 17 | [Container and Collector Coexistence](examples/17_container_collector_coexistence.md) | Write local JSONL while external collectors ship logs |
| 18 | [Console Progress Coexistence](examples/18_console_progress_coexistence.md) | tqdm/Rich progress with durable file logging |
| 19 | [Sentry Coexistence](examples/19_sentry_coexistence.md) | Local evidence alongside remote error tracking |
| 20 | [Testing and Warnings](examples/20_testing_and_warnings.md) | pytest caplog and warnings.warn() routing |
| 21 | [Web Runtime Ownership](examples/21_web_runtime_ownership.md) | Logger ownership with web frameworks |
| 22 | [Cloud Logging Coexistence](examples/22_cloud_logging_coexistence.md) | Local durable evidence alongside cloud logging platforms |
| 23 | [GUI Logging (Qt)](examples/23_gui_logging_qt.md) | PySide6 log panel with durable file logging |

## Benchmarks

D-SafeLogger is competitive in the selected single-process async benchmark runs. In multiprocess benchmarks, raw throughput is not the differentiator; parent-side file output and classified delivery-state accounting are.

The benchmark suite also includes multiprocess resilience profiles, such as sink-unavailable, burst backpressure, worker crash, warning-IPC fallback, mixed worker behavior, and shutdown behavior. These runs are not throughput claims; they check whether attempted records can be accounted for as delivered, partial-delivered, known-rejected, known-dropped, or unexplained-lost.

See [BENCHMARK.md](BENCHMARK.md) for the selected runs, methodology, and the explicit "what to claim / what not to claim" boundaries, and [`benchmarks/summary/`](benchmarks/summary/) for the published summaries.

## Testing / Quality

The release gate runs the full dev test suite across Windows, macOS, and Linux on Python 3.11-3.14. CI also runs Ubuntu free-threaded CPython `3.13t` and `3.14t` compatibility jobs with `PYTHON_GIL=0`. Publication checks verify source typing, typing smoke tests, packaged `pyright --verifytypes`, generated API docs, public design documents, benchmark summaries, and package build output.

See [TESTING.md](TESTING.md) for details.

## Compatibility / Non-goals

### Public API naming

D-SafeLogger public functions intentionally use PascalCase instead of PEP 8
snake_case.

Python's stdlib `logging` module already has long-standing underscore-free
mixedCase APIs such as `getLogger()`, `basicConfig()`, `setLoggerClass()`, and
`setLogRecordFactory()`. D-SafeLogger is a stdlib `logging`-compatible library,
so it preserves normal stdlib call sites such as `logging.getLogger()` and
`logger.info()`. Its own setup/control API uses PascalCase names:
`ConfigureLogger()`, `GetLogger()`, `RegisterLevel()`, `ReopenLogFiles()`, and
`SafeShutdown()`.

Using the same camelCase would make D-SafeLogger's setup calls visually
indistinguishable from the stdlib logging API they sit alongside. PascalCase
preserves the underscore-free convention of the logging domain while keeping the
two API layers apart.

### Migration to 0.4.0 and later

`register_level()` is renamed to `RegisterLevel()` in 0.4.0 and later as an
intentional public API normalization. Update imports such as
`from dsafelogger import register_level` to `from dsafelogger import RegisterLevel`.

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

- [Architecture Analysis White Paper](docs/design/D-SafeLogger_v23k_WhitePaper_en.md)
- [Basic Design Specification](docs/design/D_SafeLogger_Specification_v23k_full_en.md)
- [API Reference](docs/api/index.md)

Japanese design documents are also available under [`docs/design/`](docs/design/).

## License

Apache License 2.0. See [LICENSE](LICENSE).

© D-SafeLogger contributors
