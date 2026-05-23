<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2026 D-SafeLogger contributors
-->

# D-SafeLogger v23k Architecture Analysis White Paper

> An objective articulation and evaluation of the specification, design philosophy, performance, and ecosystem position of a logging platform compatible with Python's standard-library `logging` module.

---

## Document Information
| Item | Contents |
|---|---|
| Document version | 1.0 |
| Publication date | 2026-05-09 |
| Target library | **D-SafeLogger v23k** |
| pyproject version | `0.2.1` |
| import name | `dsafelogger` |
| distribution name | `d-safelogger` |
| License | Apache License 2.0 |
| Supported Python | `>=3.11` (including CPython 3.13 / 3.14 free-threaded build) |
| Supported OS | Windows / macOS / Linux |
| Runtime dependencies | **None** (standard library only) |
| Primary source review date | 2026-05-09 |
---

## Executive Summary

This white paper covers the current architecture of **D-SafeLogger v23k**, a logging platform built on Python's standard-library `logging` module. It organizes and evaluates the library's specification, design philosophy, feature set, performance, and ecosystem position.

### Product Positioning

D-SafeLogger is **a production-oriented logging platform that extends stdlib `logging` without replacing it, while adding no runtime external dependencies**. It uses `logging.setLoggerClass()` as a drop-in extension point, so existing `logging.getLogger()` / `logger.info()` call sites do not need to change. Third-party libraries built on stdlib `logging`, such as SQLAlchemy and Django, can participate in D-SafeLogger's configuration flow without modification.

### Main Architectural Axes

| Axis | Design details |
|---|---|
| **3-tier configuration pipeline** | Strict merge order with fail-fast validation: environment variables > INI/dict > arguments |
| **Capture / Transport / Sink 3 layers** | Stable responsibility boundaries across single-process and multiprocess operation |
| **Append-Only Routing** | Opens the next destination at the routing boundary without renaming or truncating the active log file. Avoids both Windows active-file rename failures and POSIX-style stale-FD failure modes (9 routing modes) |
| **Official multiprocess API (`dsafelogger.mp`)** | parent-side Writer + worker attach/detach + control plane ACK |
| **Classified delivery-state counters** | `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` / `partial_delivered` / `overload_shed` + six `writer_reject` subcategories |
| **Integrity Verification** | SHA-256 sidecar files (`sha256sum -c` compatible) + manifest |
| **Vendor-Agnostic Core** | No vendor imports such as OpenTelemetry |
| **No-Copy Snapshot** | O(1) reference hand-off based on `MappingProxyType` |
| **Four absolute guardrail constants** | 3.0s / 5.0s / 10.0s / queue maxsize warning 100000 |
| **PEP 703 free-threaded support** | The specification declares explicit locking that does not rely on the GIL |

### Public Benchmark Observations

Confirmed values from the public benchmark materials (`BENCHMARK.md` and the sessions selected by `benchmarks/summary/manifest.json`):

- **Single-process async** (Python 3.14 / GIL=on): text **51,554 msg/s, p50 16.7 µs** / JSON **52,081 msg/s, p50 16.7 µs**
- **Single-process cell winners**: throughput ranked first in **8/16** cells, p50 ranked first in **12/16** cells
- **Multiprocess integrity**: missing=0 / duplicates=0 / JSON parse failure=0 / route mismatch=0 across 3 backends × 96 raw runs
- **Multiprocess resilience**: D-SafeLogger classifies and explains delivery state for 12/12 rows under the benchmark definition; stdlib / loguru are marked as `observability_gap`

### Ecosystem Position

From the primary source comparison (as of 2026-05-09) of the 8 major projects (stdlib `logging` / Loguru / structlog / picologging / Eliot / Logbook / logfire / OpenTelemetry SDK), no Python library was observed that simultaneously satisfies the following combinations within the scope of this primary source investigation:

> **"stdlib extension × pure Python × zero runtime dependencies × append-only routing × integrity verification × parent-side multiprocess Writer × classified delivery-state counters × explicit free-threaded support × 3-tier configuration pipeline"**

This positions D-SafeLogger as a clearly differentiated option for specific operational requirements: Windows server operations, audit and compliance, multiprocess audit trails, supply-chain-security-sensitive deployments, free-threaded migration planning, and conservative stdlib-oriented environments.

### Scope of This Document

This white paper is written within the following scope:

1. **Target architecture**: The scope is the current architecture as of v23k. Improvement proposals, issue management, and future roadmap items are out of scope; this document is not a substitute for an issue tracker or roadmap.
2. **Competitive information**: Facts confirmed from public primary sources are prioritized. Unverified items are not asserted.
3. **OSS-release positioning**: This document does not predict adoption, popularity, or market response. It is limited to design positioning that can be confirmed from public materials.
4. **Reference policy**: Public design documents under `docs/design/` are used as primary design sources. Private planning materials are excluded from references.

---

## Table of Contents
### [Chapter 1 Design Philosophy and Concept](#chapter-1-design-philosophy-and-concept)
- 1.1 What is D-SafeLogger?
- 1.2 Design philosophy
- 1.3 Architectural advantages
- 1.4 Features and differentiation
- 1.5 Design characteristics
- 1.6 Positioning based on primary sources
- 1.7 Summary of this chapter
### [Chapter 2 Specifications and Design](#chapter-2-specifications-and-design)
- 2.1 Overall architecture
- 2.2 Public API structure
- 2.3 3-tier configuration management pipeline
- 2.4 Capture layer
- 2.5 Transport layer
- 2.6 Sink layer
- 2.7 File integrity verification
- 2.8 Multiprocess support (`dsafelogger.mp`)
- 2.9 Overload Policy and Survival-first Policy
- 2.10 Concurrency safety and free-threaded support
- 2.11 Design characteristics at the specification level
- 2.12 Summary of specifications and design
- 2.13 Summary of this chapter
### [Chapter 3 Usability](#chapter-3-usability)
- 3.1 Public API surface
- 3.2 Scaling from minimal code
- 3.3 Operating the three-layer configuration pipeline
- 3.4 INI/dict settings
- 3.5 Seventeen example scenarios
- 3.6 CLI tool `dsafelogger`
- 3.7 Migration from stdlib `logging`
- 3.8 Multiprocess usage
- 3.9 Coexistence with third-party libraries
- 3.10 Documentation structure
- 3.11 Zero-dependency consistency with design document §5.6
- 3.12 Design characteristics for usability
- 3.13 Usability summary
- 3.14 Summary of this chapter
### [Chapter 4 Security](#chapter-4-security)
- 4.1 Six axes of Safe and the role of security
- 4.2 Supply Chain Security (Zero Dependency)
- 4.3 Startup safety / fail-fast behavior
- 4.4 Sensitive information masking
- 4.5 File integrity verification
- 4.6 Concurrency and multiprocess safety
- 4.7 Failure Observability
- 4.8 Blocking logging-related abuse paths
- 4.9 Boundaries with third-party libraries
- 4.10 Design characteristics for security
- 4.11 Security aspect summary
- 4.12 Summary of this chapter
### [Chapter 5 Detailed Analysis by Function](#chapter-5-detailed-analysis-by-function)
- 5.0 Chapter structure
- 5.1 Append-Only Routing Functions
- 5.2 Generation management (purge/archive) and self-healability
- 5.3 Coexistence with external rotation and `ReopenLogFiles()`
- 5.4 File Integrity Verification (SHA-256/Manifest)
- 5.5 Structured logging and per-sink Formatter configuration
- 5.6 Contextualize (contextualize / FrozenContext)
- 5.7 Custom Log Level (register_level)
- 5.8 Console color output
- 5.9 async transport (QueueTransport)
- 5.10 5-state life cycle
- 5.11 `dsafelogger.mp` Writer runtime
- 5.12 `dsafelogger.mp` log plane / control plane
- 5.13 `dsafelogger.mp` Delivery status counters
- 5.14 `dsafelogger.mp` bounded shutdown and flush strategy
- 5.15 TrackedQueue (v23h)
- 5.16 Operational control using environment variables
- 5.17 INI/dict configuration refinement
- 5.18 CLI tool `dsafelogger`
- 5.19 free-threaded support
- 5.20 diagnose (variable automatic expansion)
- 5.21 sens_kws masking
- 5.22 Summary by function
- 5.23 Summary of this chapter
### [Chapter 6 Competitive Project Comparison](#chapter-6-competitive-project-comparison)
- 6.1 Scope and policy of this chapter
- 6.2 Checking the primary source of comparison projects
- 6.3 Axis 1: Runtime external dependencies
- 6.4 Axis 2: Relationship with stdlib `logging`
- 6.5 Axis 3: File output/routing
- 6.6 Axis 4: Structured Log Context Management
- 6.7 Axis 5: Multiprocess support
- 6.8 Axis 6: Integrity Verification/Audit Function
- 6.9 Axis 7: Free-threaded Python (PEP 703) compatible
- 6.10 Axis 8: Observability of delivery status
- 6.11 Axis 9: Configuration Management Pipeline
- 6.12 Latest status summary by library
- 6.13 Composition of competitive ecosystem
- 6.14 Competitive comparison summary
- 6.15 Summary of this chapter
### [Chapter 7 Positioning at OSS Release](#chapter-7-positioning-at-oss-release)
- 7.1 Scope and policy of this chapter
- 7.2 Segment 1: Supply-chain-security-focused users
- 7.3 Segment 2: Windows server operations
- 7.4 Segment 3: Audit and compliance
- 7.5 Segment 4: Free-threaded migration evaluation
- 7.6 Segment 5: stdlib-conservative users
- 7.7 Segment 6: Multiprocess audit
- 7.8 Overlaps and intersections between segments
- 7.9 Domestic vs. overseas ecosystem differences
- 7.10 Technical structure of OSS distribution
- 7.11 Positioning summary
- 7.12 Summary of positioning at OSS release
- 7.13 Summary of this chapter
### [Chapter 8 Overall Evaluation](#chapter-8-overall-evaluation)
- 8.1 Scope of this chapter
- 8.2 Aggregation of observed facts
- 8.3 Synthesis of architectural value
- 8.4 Consistency of design attitude
- 8.5 Ecosystem position
- 8.6 Benchmark observation summary
- 8.7 Documentation and operational structure
- 8.8 Objective positioning
- 8.9 Summary of this chapter
- 8.10 Limitations of this report
### [Appendix A. Reference Policy](#appendix-a-reference-policy)
### [Appendix B. Primary Source List (as of 2026-05-09)](#appendix-b-primary-source-list-as-of-2026-05-09)
### [Appendix C. Glossary](#appendix-c-glossary)
### [Appendix D. Document Preparation](#appendix-d-document-preparation)
---

## Legend
Notations and abbreviations used in this white paper:
| Notation | Meaning |
|---|---|
| `§N.M` | Section reference within this white paper (for example, §2.8 covers multiprocess support) |
| Design document §N | `docs/design/D_SafeLogger_Specification_v23k_full.md` chapter |
| Detailed design document §N | Chapter `docs/design/D-SafeLogger_DetailedDesign_v23k.md` |
| ◎ | primary strength / center of design |
| ○ | supported out of the box |
| △ | officially supported through configuration or adapters, with limited scope |
| — | Not provided as a library feature |
| ※n | note for scope or conditions |
| out | Outside the scope of responsibility (intentionally outside the scope, not not provided) |
---

## Chapter 1 Design Philosophy and Concept
### 1.1 What is D-SafeLogger?
#### 1.1.1 One sentence definition
D-SafeLogger is a logging platform built on the Python standard library `logging` and designed for production operations with zero runtime external dependencies.
- import name: `dsafelogger`
- distribution name: `d-safelogger`
- License: Apache License 2.0
- Target Python: 3.11 or higher (including **free-threaded build** of CPython 3.13 or higher)
- Target OS: Windows / macOS / Linux
- Runtime dependencies: None (Python standard library only)
- Type information: Includes `py.typed`; CI verifies `mypy`, `pyright`, a typing smoke test, and a 100% public type-completeness gate with `pyright --verifytypes`
#### 1.1.2 Positioning
Official design document §1 defines the position of this module as follows.
> This module is a lightweight, fast, and highly functional logging platform that is commonly used by all projects in the various Python ecosystems (D-Settings, DPySide, D-MessageRouter, etc.) provided by `D`. **The premise is that it will be released as a standalone OSS, but the top priority will be to operate it as a common platform for the "D Ecosystem" rather than to widely disseminate it**.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §1)
This means that library design decisions prioritize ``robustness and operational consistency as a foundation within the D ecosystem'' over ``widespread popularity.'' Its positioning is different from general-purpose front-end libraries (Loguru / structlog, etc.) in that the priority order of design decisions is made clear from the time of publication.
In addition, the design document lists the following as absolute conditions for this library.
- **Maintaining the standard logging calling model** is an absolute condition.
- In addition to meeting these requirements, it provides **diagnosis and operational control capabilities in a different direction than third-party libraries**.
- **Provides robustness to avoid active log file rename failures that often occur in Windows environments**.
- Achieve all of the above with **zero external dependencies**.
The product name prefix ``Safe'' is explicitly defined in §1 of the design document as a symbol of safety and robustness.
#### 1.1.3 Six Axes of “Safe” in the Public Narrative
The `README.md` Overview section organizes Safe into six operational dimensions.
| Axis | Public narrative summary (README) |
|---|---|
| **Startup safety** | Invalid settings, inconsistent options, and non-writable destinations cause **setup to fail** instead of letting the application enter production with broken logging. |
| **File safety** | The routing layer does not rename or truncate the active log file. It switches output by opening the next append-only destination, avoiding common Windows rename failures and POSIX-style stale-FD failure modes while enabling post-mortem verification with SHA-256 sidecars and manifests. |
| **Record / context safety** | Request ID, user ID, job ID, and similar context are **snapshotted** at producer-side hand-off. Listeners and writers do not depend on live `contextvars`; diagnostic snapshots and Writer-side formatting use the sensitive-keyword set established at configure time. |
| **Operational control** | Diagnostics, routing, hashing, log level, queue/timeout can be overwritten with environment variables without rebuilding or editing. |
| **Concurrency / multiprocess safety** | Multiprocess workers **do not open shared log files directly**. The parent-side Writer owns the sink and accepts records via IPC. Bounded queues and explicit timeouts prevent the host process from waiting indefinitely. |
| **Failure observability** | Delivery failures are **classified** as `KnownRejected` / `KnownDropped` / `UnexplainedLost`, making log loss describable as counters and shutdown summaries instead of invisible gaps in a file. |
These six axes are directly linked to individual functional designs in subsequent chapters (§4 Security, §5 Functional details).
---

### 1.2 Design philosophy
The public design document §1 clearly states the five principles that govern the design decisions of this project.
#### 1.2.1 Reroute, don't rotate
D-SafeLogger avoids renaming or truncating the active log file. It switches destinations at the routing boundary while keeping file output append-only.

Standard rotating-file designs are built around mutating the active file. On Windows, that mutation may fail immediately because active log files can be held with sharing modes that prevent rename or delete operations.

On POSIX systems, the opposite failure mode is common: the rename may succeed while existing file descriptors remain attached to the old file. That behavior is useful for many filesystem operations, but it does not mean that new records are going to the new file. A rotator may rename `app.log` to `app.log.1` and create a new `app.log`, while the writer continues appending through the old descriptor.

D-SafeLogger avoids depending on either behavior. It treats the active file as a writer-owned sink, opens the next destination at the routing boundary, and sends subsequent records there. Closed files then become archive, retention, sidecar, and manifest artifacts.

#### 1.2.1.1 External rotation is coordination, not logging

External log rotation is often treated as a standard Unix operational pattern: rename the active file, create a replacement, signal the application, and let the application reopen its sink.

That is coordination around an after-the-fact change to the active file. It is not the core of writing log records.

The core logging operation is simpler: for each record, decide the intended destination and append the record there. If the logging layer can choose the correct destination at write time, there is no need to mutate the active file, signal the application after an external rename, or depend on a later reopen.

D-SafeLogger's append-only routing follows this model. It does not make external rename/reopen coordination more elaborate; it removes that dependency from the logging write path.

#### 1.2.2 Fail before it breaks
**Prefer explicit counters / warnings / bounded shutdown over vague deficiencies.**
- If the setting is inconsistent, cannot be written to, or has an invalid type, an exception will be thrown (Fail-Fast) when starting `ConfigureLogger()`.
- Multiprocess delivery failures are now counted in the classification counter instead of **silent drop**.
- During normal termination, keep `daemon=True` as the final guard and explicitly manage the order of queue drain → bounded worker join → handler close.
#### 1.2.3 Start quick, ship as-is
Keep the minimum settings small on `ConfigureLogger()` and `GetLogger()`.
- There are two functions at the entrance to the public API. Minimum code is 3 lines.
- The same set of settings scales from scratch to production (see §1.4 INI/dict/env below).
#### 1.2.4 Zero external runtime dependencies
Structurally eliminate runtime dependencies. **Limit development/bench dependencies to dedicated dependency groups**.
- `pyproject.toml`'s zero dependence structurally guarantees "supply-chain risk gating".
- `dev` / `benchmark` / `optional_integration` dependency group is **not required during installation**.
#### 1.2.5 Be honest about multiprocess behavior
`dsafelogger.mp` **does not claim full persistence under any failure**. The value is in making delivery status observable.
- The counters and shutdown summary of `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` / `partial` externalize log loss during abnormalities as an **explainable state**.
- This attitude is also consistent with the "What Not To Claim" clause of `BENCHMARK.md` (Do not claim that multiprocess logging makes record loss impossible).
---

### 1.3 Architectural advantages
Official design document §2 lists 19 advantages of the entire v23k architecture. The observable facts can be classified as follows.
#### 1.3.1 “Independent” structure
| Item | Design specification |
|---|---|
| Zero Dependency | Consists only of standard libraries. Zero supply chain risk |
| Vendor-Agnostic Principle (v20) | Do not include any vendor-specific imports (such as OpenTelemetry) or data references in the core module (`src/dsafelogger/`). Vendor integration such as OTel is provided as a sample of Formatter insertion, `contextualize()` injection, and `examples/` |
| Free-threaded Python Ready | Protect shared states such as `_configure_state` / `_active_pipeline` / `_active_workers` / `_custom_levels` with **explicit lock**. `list` / `dict` implementation-dependent atomicity independent |
#### 1.3.2 “Non-destructive” I/O
| Item | Design specification |
|---|---|
| Append-Only Routing | Append-Only model that dynamically determines the output destination file name without renaming or truncating the active log file. **Structurally avoids `PermissionError` caused by Windows-specific file lock contention and POSIX-style stale-FD failure modes** while suppressing file operations to O(1) |
| Fire-and-Forget Asynchronous Purge | Generation management (deleting and archiving old files) is performed in a separate thread that is disposable only when switching output destinations. Even if a failure occurs due to Windows locking, etc., **Automatically retry on next switch** (self-healing) |
| File integrity verification | Generates SHA-256 hashes in a separate thread when switching. `sha256sum -c` Tampering detection, transfer verification, and file loss detection using compatible sidecar and manifest |
#### 1.3.3 Initialization that “does not degrade silently”
| Item | Design specification |
|---|---|
| Fail-Fast Initialization Verification | Test whether directories can be created, permissions, and disk space at startup. Invalid INI value **immediate exception without silent fallback** |
| Environment variable only setting to ensure safety (`diagnose`) | `f_locals` automatic expansion function at the time of exception can be enabled **only from environment variables**. Cannot be set from INI or arguments (sanctuary). Structurally eliminates the accident of forgetting to return the code |
| Enhanced concurrency safety (v21) | Execute entire `_do_configure()` of `ConfigureLogger` with `_lifecycle_lock` preserved. `GetLogger` detects `'configuring'` status and waits for structure. Safely prevent concurrent state reads during initialization |
#### 1.3.4 Observability that “makes it explainable”
| Item | Design specification |
|---|---|
| Async Mode | `Transport` Unified control of synchronous and asynchronous I/O via abstraction (`DirectTransport` / `QueueTransport`). The producer side takes a snapshot of the context/diagnosis information when necessary, and the semantics do not collapse even if the thread boundary is crossed. hand-off |
| Internal 3-layer pipeline Capture / Transport / Sink | 3-layer model: Capture (log generation), Transport (transfer), and Sink (output). Capture layer is responsible for logging compatibility, and Sink/Writer side is responsible for routing / hash / manifest / reopen / purge |
| Safe Shutdown | During normal termination, explicitly manage the order of queue drain → bounded worker join → handler close. `daemon=True` is limited to backstop at abnormal termination |
| Classified delivery status (multiprocess) | Externalize counters and shutdown summary of `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` |
#### 1.3.5 “Extend but don’t replace” standards compatibility
| Item | Design specification |
|---|---|
| Drop-in Replacement | `logging.setLoggerClass()` returns a unique class that inherits the standard `logging.Logger`. **Seamlessly injectable without hacks** into standard logging compatible libraries such as SQLAlchemy and Django** |
| Separation of concerns | Clear separation between initial settings (Configure) and usage (GetLogger) |
| Three-tier configuration management pipeline | Environment variables > INI/dict > Strict merging of arguments. INI/dict allows module-specific levels, output destinations, and routing to be described as sections |
| Per-sink Formatter configuration (v20) | Separate **Formatter** instances can be specified for file output and console output with `file_fmt` / `console_fmt`, while preserving backward compatibility with the previous overall `fmt` default |
| Non-destructive level display resolution (v21) | Level abbreviation conversion and ANSI coloring are resolved using a display proxy. `record.levelname` is not changed. Same semantics for all styles of `%` / `{}` / `$` |
#### 1.3.6 “Local” extensions
| Item | Design specification |
|---|---|
| JSONL Structured Log | Switch to JSON per line while preserving Append-Only architecture |
| Contextualize | Utilize `contextvars` to automatically assign identifiers to all logs within a specific scope. Independent isolation between threads and asyncio tasks |
| Custom log level | `register_level()` allows you to insert a custom level at any numerical position in addition to the standard 5 levels. Bulk registration of 3-letter abbreviations, ANSI colors, and convenient methods can be completed with a single call before `ConfigureLogger`. **Built-in 5 stages are inviolable** |
| Color palette settings | ANSI colors can be changed using the `color_{abbreviation}` key in the `[global]` section. For 2nd layer (INI/dict) only |
| No-Copy Snapshot (v20) | Optimized async mode snapshot / hand-off to O(1) reference passing with immutability guarantee by `contextvars.ContextVar[MappingProxyType]`. Mutable values are rejected with Fail-Fast |
| Full Transport integration of module-specific path (v21) | Apply `is_async=True` semantics consistently not only to root route but also to module-specific path route |
---

### 1.4 Features and differentiation
#### 1.4.1 Design axis of “extend” and “replace”
The public narrative (README "Why D-SafeLogger?" section) contrasts the direction of this library as follows:
> D-SafeLogger extends the standard logging path rather than replacing it: you keep using `logging.getLogger()` and existing `logger.info()` call sites, and the library adds safe local-file output on top — append-only routing, fail-fast configuration, SHA-256 sidecars, sensitive-data masking, environment-driven operational control, and a parent-side multiprocess Writer.
> (Quoted from section `README.md` "Why D-SafeLogger?")
The differentiation derived from this is the following three points:
1. **No differentiation at API level, only differentiation at design level**: Existing `logging.getLogger()` / `logger.info()` call sites will work as is.
2. **Additional functions are below the file output boundary**: append-only routing, SHA-256 sidecar, masking, environment variable override, and parent side Writer all operate ``below the entrance of stdlib `logging` Handler/Formatter''.
3. **Existing logging ecosystem can participate**: Loggers obtained by SQLAlchemy / Django etc. with `logging.getLogger()` will automatically follow the configuration flow of this library.
#### 1.4.2 Coexistence with structlog (not replacement)
The README explicitly defines the relationship with structlog as ``coexistence, not replacement.''
> If you already use `structlog` as a structured-logging frontend, D-SafeLogger coexists rather than replaces. `structlog` builds the event dictionary; D-SafeLogger handles file output, routing, sidecars, masking, and operational control.
> (Quoted from section `README.md` "Why D-SafeLogger?")
This is an expression of a design attitude that treats the ``front end (event structuring)'' and the ``back end (file output, consistency, and operational control)'' as different responsibilities. Two integration patterns are provided for `examples/16_structlog_coexistence.md`.
#### 1.4.3 Differences in design axis from Loguru / structlog system
The design axes of each library can be observed from the Feature Comparison table (`stdlib logging` / `loguru` / `structlog` / D-SafeLogger) published in the public README.
| Design axis | Location of each library (from README table) |
|---|---|
| **stdlib `logging` API compatible** | stdlib ◎ / loguru △※2 / structlog △※3 / D-SafeLogger ◎ |
| **Keep existing `logger.info()` call site** | stdlib ◎ / loguru △※2 / structlog △※3 / D-SafeLogger ◎ |
| **Participation of third party library `logging.getLogger()`** | stdlib ◎ / loguru △※2 / structlog △※3 / D-SafeLogger ◎ |
| **Zero runtime external dependencies** | stdlib ◎ / loguru — / structlog — / D-SafeLogger ◎ |
| **Centralized configuration (handler/formatter wiring replacement)** | stdlib △※1 / loguru ◎ / structlog △※3 / D-SafeLogger ◎ |
| **No rename/truncate append-only file routing** | stdlib —※5 / loguru —※6 / structlog —※3 / D-SafeLogger ◎ |
| **SHA-256 sidecar / manifest** | stdlib — / loguru — / structlog —※3 / D-SafeLogger ◎ |
| **fail-fast configuration validation** | stdlib △※4 / loguru △※4 / structlog △※4 / D-SafeLogger ◎ |
| **Multiprocess output through parent-side Writer** | stdlib —※10 / loguru —※9 / structlog —※3 / D-SafeLogger ◎ |
| **Delivery status accounting (multiprocess)** | stdlib — / loguru — / structlog — / D-SafeLogger ◎ |
> Legend: ◎ = primary strength / core of the design, ○ = supported out of the box, △ = officially supported through configuration or adapters with limited scope, — = not provided as a library feature, ※n = note for scope or conditions

Notes for this table follow the public README's Feature Comparison notes. In particular, `—※n` does not mean "impossible with arbitrary application code"; it means the capability is outside that library's own built-in responsibility. Loguru's rotation / retention / compression and `enqueue=True` are recognized as built-in strengths, but they are not equivalent to append-only rerouting, parent-side Writer ownership, or delivery-state accounting. structlog is treated as a structured-logging frontend; file lifecycle, integrity sidecars, and multiprocess sink semantics are backend or application responsibilities.
The following combinations can be interpreted as differentiation axes:
- **stdlib compatibility ◎ × Zero external dependencies ◎** Compatibility: Except for stdlib itself, only D-SafeLogger has ◎ in both tables.
- **append-only routing ◎ / SHA-256 sidecar ◎ / fail-fast configuration validation ◎ / parent side multiprocess Writer ◎ / Delivery status accounting ◎** **5 axes at the same time ◎**: In the README table, the other 3 libraries do not treat this combination as built-in design centerpieces.
These are the consequences of the design axis of ``rather than redesigning logging like Loguru / structlog, maintain logging and strengthen it below the output boundary.''
#### 1.4.4 Non-goals
The "Compatibility / Non-goals" section of the README identifies unintended areas of this library.
> D-SafeLogger is not a log shipper, metrics pipeline, distributed tracing backend, or access-control system. Use tools such as Fluent Bit, Vector, Filebeat, OpenTelemetry Collector, or a tracing backend for those roles.
> (quoted from `README.md` "Compatibility / Non-goals" section)
This is a boundary line that explicitly separates the scope of responsibility of "logging infrastructure within the application process" from the entire observability stack.
---

### 1.5 Design characteristics
From the public design documents and public narratives, we observe the following attitudes that underlie design decisions. These will be reused as evaluation criteria for individual functions in subsequent chapters of this report.
#### 1.5.1 “Accident patterns should not be established structurally”
A typical example is the provision that limits `diagnose` to environment variables only (Design document §4.4).
- There is no way to write `diagnose=True` in the code → The accident pattern of "writing it in the code and forgetting to put it back" **does not hold in normal usage routes**.
- INI is also excluded because it has the risk of being affected by version control → "git commit mixes into production" accident pattern is also blocked.
- Production activation is limited to explicit manipulation of the infrastructure layer (environment variables).
Similar postures are also observed:
- Execution of `_do_configure()` under `_lifecycle_lock` (§2 Enhanced concurrency safety) → Structurally eliminates reading of semi-completed state during initialization.
- TypeError/ValueError on mutable value `contextualize()` → **Reliably detect unintended side effects on shared snapshots during development**.
- Fail-Fast when initialization of `ConfigureLogger` fails → Eliminate the failure pattern of "settings appear to be moving even though they are not reflected."
#### 1.5.2 “Do not create unobservable loss”
The `KnownRejected` / `KnownDropped` / `UnexplainedLost` classification (§1.2.5, §1.3.4) of multiprocess delivery is a representative example.
- The design goal is not to "not cause delivery failures," but to "make delivery failures **explainable**."
- This is consistent with the "What Not To Claim" section of `BENCHMARK.md`: "Does not claim that multiprocess logging makes record loss impossible" and "Does not claim that sink outage / worker crash / hard process termination becomes impossible."
#### 1.5.3 "Do not break standard semantics"
Nondestructive level display resolution (§1.3.5, revised v21) is a typical example.
- Do not modify `record.levelname` to display level abbreviations.
- Does not depend on temporary replacement by `copy.copy(record)` or try/finally.
- Solve with display proxy/local mapping and preserve the semantics of shared `LogRecord`.
- Guaranteed the same semantics for all styles of `%` / `{}` / `$` allowed by `logging.Formatter`.
This is an attitude that structurally guarantees that ``other libraries and other code built on top of stdlib `logging` will not have their prerequisites violated due to the existence of this library.''
#### 1.5.4 "Extension is closed before ConfigureLogger"
The provisions of `register_level()` (§2, §1.3.6) are an example of this.
- Registration of custom log level can be completed with a single call **before `ConfigureLogger()`**.
- Since it is determined before the evaluation of the 3-layer configuration management pipeline (env > INI > arguments), the order of level name resolution is determined **uniquely in the initialization flow**.
- Built-in 5 levels are protected as inviolable.
This is a way of placing the restriction that ``extension points are provided, but dynamic changes are not allowed beyond initialization boundaries.''
---

### 1.6 Positioning based on primary sources
From the materials reviewed in this chapter, the design goals as of v23k can be summarized as follows.
1. **It is positioned as an "extension of stdlib `logging`" and not a "redesign"**: For a configuration in which drop-in extension, preservation of existing call sites, and co-participation of a third-party logging library are all compatible at the same time, only D-SafeLogger and stdlib `logging` are compatible in the README Feature Comparison table.
2. **Zero dependence is defined as an ``absolute condition'' rather than a ``feature''**: §1 of the design document specifies ``achieved with zero external dependencies'' as an absolute condition, and §2 embodies the Vendor-Agnostic principle by excluding vendor imports such as OTel from the core module. This is not a judgment for individual functions, but is used as a consistency constraint for the entire library.
3. **``Safe'' is not a single concept but is developed as a six-axis operational dimension**: The Overview section of the README clearly identifies six axes: startup safety / file safety / record・context safety / operational control / concurrency・multiprocess safety / failure observability, and each axis corresponds to the subsequent individual function design.
4. **The 19 items in §2 of the design document can be organized into 6 groups: "Do not depend on / Do not break / Do not deteriorate silently / Make it explainable / Expand but do not replace / Complete locally"**: The 19 advantages that appear to be scattered on the surface can be derived from a consistent design attitude as shown in §1.3.1 to §1.3.6.
5. **Multiprocess feature claims are placed on observability rather than raw throughput**: Both `BENCHMARK.md` and Design Document §2 describe the value of `dsafelogger.mp` as the observability of Writer-owned sinks and classified delivery states, and raw throughput does not claim precedence.
6. **Extension is closed before the initialization boundary**: The series of regulations that limit `register_level()` to before `ConfigureLogger`, limit `diagnose` to environment variables, and fail-fast verify INI settings are consistent design decisions that structurally do not allow dynamic changes that cross the initialization boundary.
7. **Relationship with structlog/Loguru is not a competition but separation of duties**: The README "Why D-SafeLogger?" section and the Feature Comparison table position the combination of stdlib compatibility × zero external dependencies × append-only routing × SHA-256 sidecar × parent side multiprocess Writer as a unique axis of D-SafeLogger, and the structlog structured front end Loguru The design axes do not intersect with the DX optimization.
---

### 1.7 Summary of this chapter
The design philosophy of D-SafeLogger v23k can be summarized into three points:
1. **"Extend, don't replace"**: Strengthen safety below the file output boundary while maintaining stdlib `logging`'s API, call sites, and third-party integration.
2. **"Zero dependencies. There is a sanctuary."**: External runtime dependencies and vendor-specific imports are excluded from the core, and settings that cause accidents such as `diagnose` are structurally isolated.
3. **"Do not make failure impossible. Make it explainable."**: Externalize delivery failures, shutdown errors, and initialization inconsistencies through counters/exceptions/shutdown summaries instead of letting them deteriorate silently.
These ideas will be implemented as a concrete architecture (3-layer configuration pipeline, Capture/Transport/Sink, Append-Only routing, `dsafelogger.mp` Writer) in the next chapter, ``2. Specifications and Design.''
---

> **Main references for this chapter**: `docs/design/D_SafeLogger_Specification_v23k_full.md` §1, §2 / `README.md` Overview, "Why D-SafeLogger?", Feature Comparison, Compatibility/Non-goals section / `README_ja.md` Same section / `LICENSE` / `pyproject.toml`
> This document is intended to explain and evaluate the current v23k architecture, and does not include improvement proposals, issue management, or future roadmaps.
## Chapter 2 Specifications and Design
### 2.1 Overall architecture
#### 2.1.1 Physical module configuration
The module configuration of v23k defined in detailed design document §1 is as follows (package name `dsafelogger`).
```text
dsafelogger/
  __init__.py # single-process public API (ConfigureLogger, GetLogger, register_level, ReopenLogFiles)
  _logger.py # DSafeLogger class (logging.Logger extension)
  _handler.py # AppendOnlyFileHandler
  _async.py # DSafeQueueHandler / DSafeQueueListener / safe shutdown
  _formatter.py # DSafeFormatter, DiagnosticFormatter, StructuredFormatter
  _writer_formatter.py # formatter spec used in Writer runtime Solved helper
  _color.py # ColorStreamHandler, ANSI color mapping, Windows VT100 enabled
  _routing.py # RoutingStrategy group (file name determination logic)
  _sink.py # FileSink / ConsoleSink / SinkGroup (core abstraction of writer-side sink graph)
  _purge.py # PurgeWorker (delete) / ArchiveWorker (ZIP compression)
  _transport.py # single-process Transport abstract (DirectTransport / QueueTransport)
  _pipeline.py # single-process ResolvedConfig / PipelineBuilder / Pipeline
  _context.py # contextvars-based context management (FrozenContext)
  _levels.py # Custom log level registration/management
  _integrity.py # Integrity verification (compute_sha256, write_sidecar, append_manifest, HashWorker)
  _env_parser.py # Environment variable parser
  _ini_loader.py # INI file loader
  _constants.py # Constant definition
  _validator.py # Fail-Fast permission/disk space validation
  _cli.py # dsafelogger CLI entry point
  mp/
    __init__.py # multiprocess public API
  _mp_protocol.py # BootstrapContext / LogEvent / ControlRequest / ControlAck
  _mp_attach.py # AttachCurrentProcess / DetachCurrentProcess / GetWorkerInitializer
  _mp_runtime.py # Writer runtime / active client registry / shutdown / reopen / counters
  _mp_control.py # control plane request/ack helpers
  _mp_queue.py # TrackedQueue (for log plane)
```

Each module has a private prefix starting with `_`, and has a structure that localizes the public API entrance to two files, `__init__.py` and `mp/__init__.py`.
#### 2.1.2 Internal 3-layer pipeline: Capture / Transport / Sink
According to the specifications in §11.3 and §2 of the design document, the internal architecture of this library is clearly separated into three layers: Capture (log generation), Transport (transfer), and Sink (output).
| layers | single-process | multiprocess |
|---|---|---|
| **Capture** | `DSafeLogger` / `logging.setLoggerClass()` / `contextualize()` / `diagnose` snapshot / route resolution | Same as left (client side) |
| **Transport** | `DirectTransport` / `QueueTransport` | client side process-local async queue (if necessary) + hand-off to log plane `multiprocessing.Queue` |
| **Sink / Runtime** | `FileSink` / `ConsoleSink` / routing / hash / manifest / reopen | Consolidated in Writer runtime: routing / file open/close / hash / manifest / archive / purge / reopen / shutdown / control plane |
Design document §11.3 specifies the following boundary provisions:
> Even in the multiprocess version, `logging` compatibility is the responsibility of the Capture layer, and the Writer must not re-execute the Capture semantics of `LogRecord` (logger hierarchy evaluation, `propagate` judgment, level judgment, `f_locals` collection). The Writer side simply receives `LogEvent` and dispatches it to the sink group according to the route.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.3)
This is a clear statement of the design attitude that ``the only difference between single-process and multiprocess is the Transport boundary, and the Capture/Sink responsibility boundary remains unchanged.''
#### 2.1.3 v23 Writer invariants
Design document §12.1 has 9 fixed invariant conditions that will not be broken in the v23 series.
| Item | Invariant |
|---|---|
| Writer ownership | file sink / routing / hash / manifest / archive / purge / reopen is centrally owned by Writer |
| Writer drain | Writer log plane is based on **single serial drain** |
| Writer write | write to file maintains **O_APPEND or equivalent append-only operation** |
| Writer parallelization | Not included in v23 series improvements |
| file write | Do not perform parallel writes to the same log family / route / file |
| append-only routing | Maintain a routing policy that does not rely on rename/truncate |
| Capture / Transport / Sink | Maintain three-layer separation and avoid mixing responsibilities |
| logging compatible | Maintain Drop-in Replacement by `logging.setLoggerClass()` |
| Zero dependency | Use only standard libraries without adding external dependencies |
| fail-safe | Avoid silent loss / silent hang / silent fallback |
The design document also specifies in § 12.2 what the v23 series will not do: Writer parallelization / flush contract weakening / append-only semantic changes / benchmark-driven unsafe optimization / breaking changes to public JSON schemas / silent drop / fallback. **The boundary line in the direction of improvement itself is declared as a specification**.
---

### 2.2 Public API structure
Design document §10 lists public APIs. The single-process version (`dsafelogger`) and multiprocess version (`dsafelogger.mp`) **separate the entrance namespace** and share only the function names `ConfigureLogger` / `GetLogger` / `ReopenLogFiles`.
#### 2.2.1 single-process API (`dsafelogger`)
| API | Type | Main contract |
|---|---|---|
| `ConfigureLogger(default_level, log_path, pg_name, env_prefix, config_file, config_dict, is_async, backup_count, archive_mode, routing_mode, interval, max_bytes, max_lines, max_count, suffix_digits, console_out, structured, fmt, file_fmt, console_fmt, datefmt, enable_hash, manifest_path, sens_kws, sens_kws_replace) -> None` | Once at startup | 5 state idempotent management. `unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`. Allow auto-fire (`GetLogger()` implicit initialization when preceding) |
| `GetLogger(name='') -> logging.Logger` | Any time | Wrap standard `logging.getLogger()`. Root logger acquisition is `name=''`. Allow default initialization by **auto-fire** when uninitialized |
| `register_level(name, value, abbreviation, color='') -> None` | 0+ times before startup | Call **before** `ConfigureLogger()`. `shutting_down` Inside is `RuntimeError` |
| `ReopenLogFiles() -> None` | Any time | `ValueError` if sink other than `routing_mode='none'` is active. external rotation coexistence only |
#### 2.2.2 multiprocess API (`dsafelogger.mp`)
| API | Type | Main contract |
|---|---|---|
| `ConfigureLogger(...) -> object` | Once at startup | In addition to the single-process argument, has `worker_model='process'\|'pool'\|'executor'`, `mp_context`, `ipc_log_timeout=0.5`, `ipc_log_queue_maxsize`, `ipc_client_queue_maxsize`, `writer_flush_batch`. **Returns opaque and picklable `ctx`** |
| `AttachCurrentProcess(ctx) -> None` | When each worker starts | `ctx` validation → `ATTACH` request → `protocol_version` / `registry_hash` collation → process-local application of `logging.setLoggerClass()` |
| `DetachCurrentProcess() -> None` | At shutdown | `DETACH` control request sent → process-local state discarded after successful ACK |
| `GetLogger(name='') -> logging.Logger` | Any time | **Do not auto-fire**. `RuntimeError` when not attached (Fail-Fast detection of forgetting to attach) |
| `GetWorkerInitializer(ctx) -> tuple[Callable, tuple]` | Pool/Executor cooperation | Can be passed directly to `Pool(initializer=..., initargs=...)` / `ProcessPoolExecutor(initializer=..., initargs=...)` |
| `ReopenLogFiles() -> None` | Any time | **Synchronous API** using control plane. ACK timeout is an internal constant `CONTROL_PLANE_ACK_TIMEOUT_SEC=5.0` |
#### 2.2.3 Single / multiprocess differences
Design documents §10 and §11.18 specify the following differences:
| Perspective | single-process | multiprocess |
|---|---|---|
| auto-fire | Allowed | **Prohibited** (Fail-Fast detection of forgetting to attach) |
| `GetLogger()` When not initialized | Initialized with default arguments | `RuntimeError` |
| `ConfigureLogger()` 2nd time | No-Op or old Pipeline stop + reinitialization depending on the state | **`RuntimeError`** (Double startup within the same process is prohibited) |
| `ReopenLogFiles()` | Reopen file handle synchronously | Control request to control plane → Wait for ACK |
| `worker_model` / `mp_context` | No concept | Explicit as public argument |
---

### 2.3 Three-tier configuration management pipeline
Design document §3 defines. Separate the origin of settings into the following three layers and define a strict merging order in which upper layers always overwrite lower layers.
```text
Layer 1: Environment variables (top priority/emergency override)
  ↓ Overwrite
Layer 2: INI file or dictionary (production baseline)
  ↓ Overwrite
3rd layer: ConfigureLogger argument (default/simple usage)
```

#### 2.3.1 Role of each layer
| Layer | Role | Entrance |
|---|---|---|
| Third layer | Arguments (default/for small scripts) | `ConfigureLogger(default_level=..., log_path=..., ...)` |
| Second layer | INI file or `config_dict` (operational baseline) | `config_file='./config/logging.ini'` or `config_dict={'global': {...}, 'dsafelogger:mod': {...}}` |
| First layer | Environment variables (emergency override) | `D_LOG_LEVEL=WARNING` etc. (prefix can be changed with `env_prefix`) |
#### 2.3.2 Specific example of merge evaluation
Example of design document §3.3:
```python
# 3rd layer: arguments
ConfigureLogger(default_level='DEBUG', log_path='./logs', routing_mode='daily')
```

```ini
; Second layer: INI
[global]
default_level = INFO
backup_count = 30
```

```bash
# Layer 1: Environment variables
D_LOG_LEVEL=WARNING
```

Merge result:
- `default_level` = `WARNING` (environment variables are final)
- `log_path` = `./logs` (Not listed in INI, arguments are maintained)
- `routing_mode` = `daily` (Not listed in INI, arguments are maintained)
- `backup_count` = `30` (INI overrides default value of argument)
#### 2.3.3 Environment variables (first layer) items
All environment variables in design document §4:
| Environment variable | Purpose | Valid values |
|---|---|---|
| `{prefix}_LEVEL` | Global default level | `DEBUG` ~ `CRITICAL` + registered custom level name |
| `{prefix}_MODULES` | Level/output destination by module | `MOD:LEVEL[,...]` or `MOD:LEVEL:PATH[,...]` |
| `{prefix}_DIAGNOSE` | Diagnostic mode | Valid only for `"1"` |
| `{prefix}_CONSOLE` | Forced console output control | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_COLOR` | Color output forced control | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_CONFIG` | INI file path override | file path |
| `{prefix}_HASH` | Enable hash generation | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_MANIFEST` | Manifest file path override | File path |
| `{prefix}_IPC_LOG_TIMEOUT` | MP version log plane transmission wait time | Positive floating point seconds |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` | MP version log plane queue capacity | Positive integer |
| `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` | MP version process-local async queue capacity | Positive integer |
| `{prefix}_WRITER_FLUSH_BATCH` | MP version Writer flush batch size | Positive integer |
| `NO_COLOR` | Forced disable color output | If set (industry standard, `env_prefix` not affected) |
The design documents specify the following “sanctuaries”:
- **`diagnose` is only an environment variable**: Cannot be set from INI or arguments. Design document §4.4 clearly states the reasons: ``There is no way to write `diagnose=True` in the code'' and ``INI is also excluded due to version control risks.''
- **`sens_kws` / `sens_kws_replace` also does not support setting from environment variables**: Design judgment and explanation to prevent unintended changes to sensitive keywords in §3.4.
- **`file_fmt` / `console_fmt` are also not supported by environment variables**: Formatter instances cannot be expressed by environment variables.
#### 2.3.4 INI / `config_dict` (2nd layer)
The provisions of the design document §5:
- INI: Initialized with `configparser.ConfigParser(interpolation=None)` (no need to escape `%`). Define `[global]` and `[dsafelogger:module_name]` sections.
- `config_dict`: `dict[str, dict[str, str]]` type. In order to pass through the completely same type conversion/validation pipeline as INI, **all values ​​are specified as strings** (`int`/`bool`, direct specification is `TypeError`, Fail-Fast).
- `config_file` and `config_dict` are **exclusive** (`ValueError` when both are specified).
- The keys of the `[global]` section map one-to-one to `ConfigureLogger` arguments. The `color_{abbreviation}` key is only for the second layer (not supported by environment variables/arguments).
- Unknown key: stderr warning + ignore (not fail-fast)
- Unknown section: stderr warning + ignored
- Type conversion failure for known key: **Fail-Fast** (`ValueError`)
- `[dsafelogger:]` (module name empty): `ValueError`
#### 2.3.5 Design Decision: Strict Merging of Multilayer Pipelines
Design document §3 uses a merge order in which ``ConfigureLogger INI always takes precedence over arguments, and environment variables take precedence over INI'' in combination with the **principle of not allowing silent fallback**.
- Developers who want to operate with argument values ​​do not place INI.
- Operators who want to change behavior during operation should place INI.
- Operators who want to change in an emergency place environment variables.
- At every layer, a line is drawn that says ``Fail-Fast for incorrect types'' and ``Warning only for unknown keys.''
This is the result of a design approach in which "setting changes are uniquely determined (it is possible to trace who made the changes)".
---

### 2.4 Capture layer
#### 2.4.1 `DSafeLogger`
Detailed design document §2 stipulates. `DSafeLogger` is a class that inherits `logging.Logger` and adds `contextualize()` methods.
```python
class DSafeLogger(logging.Logger):
    def contextualize(self, **kwargs) -> AbstractContextManager:
        ...
```

- The standard `logging.Logger` API is completely maintained (standard handlers such as `caplog` fixtures of `pytest` and `SMTPHandler` function as they are).
- Call `logging.setLoggerClass(DSafeLogger)` inside `ConfigureLogger()` so that subsequent calls to `logging.getLogger()` return `DSafeLogger` instances.
- In the multiprocess version, `AttachCurrentProcess()` also reapplies `setLoggerClass()` to process-local (also works in combination with process-local thread / transport regeneration even in child after fork inheritance).
#### 2.4.2 5 state initialization flow
State transitions defined by Design Document §9.2:
| Current | Event | Transition destination |
|------|---------|---------|
| `unconfigured` | `ConfigureLogger()` | `configuring` |
| `unconfigured` | `GetLogger()` Preceding | `configuring` (auto-fire) |
| `configuring` | Successful completion | `explicit` or `auto` |
| `configuring` | Exception occurred | `unconfigured` (rollback) |
| `configuring` | Same thread reentrant | No-Op return |
| `auto` | `ConfigureLogger()` | `configuring` (old Pipeline stop → reinitialization) |
| `auto` | `_shutdown()` | `shutting_down` |
| `explicit` | `ConfigureLogger()` | **No-Op return** |
| `explicit` | `_shutdown()` | `shutting_down` |
| `shutting_down` | Completed | `unconfigured` |
| `shutting_down` | `ConfigureLogger()` | No-Op |
`_lifecycle_lock` is implemented by `RLock`. Reentrancy of the same thread is a No-Op, and another thread re-evaluates the state after waiting for lock acquire. When an exception occurs, `try/finally` ensures that `configuring` does not remain.
#### 2.4.3 Formatter group
4 systems stipulated by detailed design document §4:
| Class | Role |
|---|---|
| `DSafeFormatter` | Text output (default format). Compatible with all styles of `%` / `{}` / `$` |
| `StructuredFormatter` | JSON Lines output. `contextualize()` Information to top level field |
| `DiagnosticFormatter` | Text output when `diagnose=True`. Expand `f_locals` |
| `DiagnosticStructuredFormatter` | `diagnose=True` and `structured=True`. `f_locals` to JSON `locals` field |
Default format string:
```text
%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s
```

- Date and time format: `%Y-%m-%d %H:%M:%S`
- Level abbreviations: `DBG` / `INF` / `WAR` / `ERR` / `CRI` (and `register_level()` registered custom level)
#### 2.4.4 Non-destructive handling of LogRecord
Design document §9.7 and detailed design document §4 are specified as mandatory implementation patterns.
> The same instance of `logging.LogRecord` is shared among all handlers. If Formatter or Handler directly rewrites attributes such as `record.levelname` or `record.msg`, destructive side effects will propagate to subsequent handlers.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §9.7)
The implementation pattern is resolved by "display proxy".
```python
class DisplayRecordProxy:
    def __init__(self, original: logging.LogRecord, overrides: dict[str, object]):
        self.__dict__ = original.__dict__.copy()
        self.__dict__.update(overrides)


class DSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        display_level = self.LEVEL_MAP.get(record.levelname, record.levelname)
        display_record = DisplayRecordProxy(record, {'levelname': display_level})
        return super().format(display_record)
```

The following provisions have been added in the design document §2 v21 revision.
- Do not change `record.levelname`.
- Does not depend on temporary replacement by `copy.copy(record)` or try/finally.
- ANSI coloring is also resolved using the same proxy route.
#### 2.4.5 Level name abbreviation mapping
Design document §9.8 defines.
- Abbreviation conversion is performed using local mapping that is completed within the scope of Formatter's responsibilities.
- Do not use global level name override with `logging.addLevelName()` (to avoid process-global side effects; maintain test independence of third-party libraries).
- However, `logging.addLevelName(value, name)` is called inside `register_level()`. This is a numerical value → name mapping necessary for normal operation of `logger.log(value, msg)` / `isEnabledFor(value)`, and is different from abbreviation conversion.
- `LEVEL_MAP` / `COLOR_MAP` is not a class variable but an **instance variable**, and constructs an integrated map of the built-in 5 levels and custom level when Formatter is initialized.
#### 2.4.6 Custom Log Level
`register_level()` as specified by design document §9.9:
| Terms | Contents |
|---|---|
| Calling order | `register_level()` (any number of times) → `ConfigureLogger()` (1 time) → `GetLogger()` (any number of times) |
| Subsequent calls | `register_level()` after `ConfigureLogger()` is `RuntimeError`. `shutting_down` Inside too `RuntimeError` |
| Built-in protection | Value 10/20/30/40/50, name DEBUG/INFO/WARNING/ERROR/CRITICAL, abbreviation DBG/INF/WAR/ERR/CRI override `ValueError` |
| Useful methods | `register_level('TRACE', value=5, ...)` → Dynamically add `logger.trace()` method to `DSafeLogger` class. Skip if it conflicts with an existing method name |
| Alignment with 3-tier pipeline | Custom level names now available in all layers of arguments/INI/environment variables |
| spawn re-import | re-registering the same definition (name/value/abbreviation/color exact match) is an idempotent no-op. Unmatched re-registration is `RuntimeError` |
---

### 2.5 Transport layer
#### 2.5.1 `DirectTransport` / `QueueTransport`
Detailed design document §15a stipulates. The Transport layer is an abstraction that connects Capture and Sink.
| Transport | Application | Operation |
|---|---|---|
| `DirectTransport` | `is_async=False` | Pass the LogRecord generated on the Capture side to the Sink synchronously |
| `QueueTransport` | `is_async=True` | Performs context/diagnose snapshot on Capture side and hand-off to listener thread via queue |
#### 2.5.2 Async hand-off semantics
Design documents §9.3 and §11.17:
- At `is_async=True`, on the producer thread side:
  - Snapshot `contextualize()` information to private attribute (`_ds_context`) of `LogRecord`
  - Convert `f_locals` to a masked, repr-converted snapshot only when `diagnose=True` and `exc_info` are present (`_ds_diag_frames`)
- The consumer thread side does not refer to live `contextvars`, and preferentially uses the producer side snapshot.
- When used with `is_async=True` in the multiprocess version, it becomes double queuing of **process-local async queue + multiprocess log queue + Writer dispatch**. Usually `is_async=False` is sufficient.
#### 2.5.3 No-Copy Snapshot (FrozenContext)
Design document §9.5 and §2 v20 revised:
- Adopted `contextvars.ContextVar[MappingProxyType]` (changed from `ContextVar[dict]` in v20).
- Thanks to the immutability of `MappingProxyType`, snapshot acquisition and consumer side reference in async mode are realized in **O(1) reference passing**.
- However, generating a new MappingProxyType at the `contextualize()` entrance takes O(n). Only hand-off is O(1).
- **Fail-Fast** for mutable values: If the value of `contextualize(**kwargs)` is a mutable type such as list / dict / set, sends `TypeError` or `ValueError`. This ensures that unintended side effects due to O(1) reference passing are detected during development.
- **MappingProxyType restrictions**: Only top-level key operations are protected. If the value is mutable, changes to the contents cannot be prevented (as specified in the specification).
#### 2.5.4 Complete override of `DSafeQueueHandler.prepare()`
Design document §9.3:
- The queue hand-off of D-SafeLogger is a **complete override** that does not use stdlib `QueueHandler.prepare()` as is, nor does it call `super().prepare()`.
- This separates stdlib differences between Python 3.11 / 3.13 / 3.14 from semantics.
#### 2.5.5 Transport full integration of module-specific path
Design document §2 v21 revised:
- Apply `is_async=True` semantics consistently to module-specific paths as well as root routes.
- `Pipeline` holds `module_transports: dict[str, Transport]` and structurally stops all Transports at `stop()`.
---

### 2.6 Sink layer
#### 2.6.1 `AppendOnlyFileHandler`
Detailed design document §6 stipulates. Inherits `logging.FileHandler` and is responsible for writing files using the Append-Only model.
- Receive the "next file name to write" from `RoutingStrategy`.
- The switching decision is queried every time just before emit.
- When switching, the old stream is `close` and the new file is `open` (do not rename).
- `_ds_required: bool = True` (class attribute, v23h). Target of delivered determination as required sink.
- To avoid duplication of `_lock`, independent `self._lock` will be abolished in v21 and unified to `acquire()` / `release()` API of parent class `logging.Handler` (double lock overhead eliminated).
- In the multiprocess route, it is set to `stream_flush_on_emit=False`, and Writer has unified control over batch / per-message.
#### 2.6.2 `RoutingStrategy`
Detailed design document §5 and design document §7.3 stipulate. There is a Strategy class corresponding to each mode.
| Mode | Suffix | Usage |
|---|---|---|
| `none` | None (`{pg_name}.log`) | Single file addition. external rotation coexistence target |
| `daily` | `YYYYMMDD` | Switch when changing date |
| `hourly` | `YYYYMMDD_HH` | Switch every hour |
| `min_interval` | `YYYYMMDD_HHMM` | Specified minute interval (only integers that are evenly divisible by 60) |
| `startup_interval` | `YYYYMMDD_HHMMSS` | Start time base. `interval` also accepts character string specifications (`'12h'` / `'1d'`) |
| `size` | Sequential number (`suffix_digits` digits) | Switch by size threshold |
| `count` | Sequential number | Switch by line number threshold |
| `cyclic_weekday` | `sun` / `mon` / `tue` ... | Day of the week cycle (not subject to generation management, overwritten) |
| `cyclic_month` | `01` ~ `12` | Monthly cycle (same as above) |
The operation branches depending on whether `max_count` of `size` / `count` is specified:
- `max_count` specified → cyclic overwrite mode (not subject to generation management).
- `max_count` Not specified → Upper limit reached error mode. It monotonically increases up to the maximum value of `suffix_digits` (`.999` if it is 3 digits), and at the limit it sends `OverflowError` and stops the application. `backup_count > 0` or `archive_mode=True` contradicts the design intent and causes `ConfigureLogger()` to fail fast with `ValueError`.
#### 2.6.3 `ColorStreamHandler`
Detailed design document §12 stipulates.
- `_ds_required = False` (best-effort sink).
- ANSI color codes are assigned to abbreviated display level values.
- Do not modify `record.levelname` directly (comply with §9.7 Non-destructive handling).
- For Windows, enable VT100 with `os.system("")` during initialization.
- `COLOR_MAP` also integrates `register_level()` registered custom level color as an instance variable.
- Color control priority (§4.5):
  1. `NO_COLOR` Settings → Forced Disable
  2. `{prefix}_COLOR` setting → Follow that value
  3. Both not set → Automatic judgment with `sys.stderr.isatty()`
#### 2.6.4 `FileSink` / `ConsoleSink` / `SinkGroup`
Detailed design documents §1 and §15a:
- The central abstraction of the writer-side sink graph.
- In single-process, `_pipeline.py` assembles `SinkGroup`.
- In multiprocess, the Writer runtime constructs an equivalent structure.
- `_build_writer_sink_groups` (`mp/__init__.py`) in the multiprocess route sets `stream_flush_on_emit=False`, and Writer has unified control over flush (§11.27 v23g).
#### 2.6.5 Sink classification (required / best-effort)
Design document §12.3 (v23h):
| handler | `_ds_required` | Meaning |
|---|---|---|
| `AppendOnlyFileHandler` | `True` (default) | required sink. delivered Judgment target |
| `ColorStreamHandler` | `False` | best-effort sink. delivered Non-judgment and failures are recorded separately |
| User-specific `logging.Handler` derivation | No attribute → treated as `True` | Custom handler is default required |
per-record accounting rules:
- All required handlers succeeded → `delivered` (counter not incremented)
- All required handlers fail → increment `_reject_counter += 1`, `writer_sink_reject` or `writer_policy_reject`
- Only some required handlers succeeded → `_writer_partial_delivered += 1` (terminal state is `partial_delivered`)
- best-effort handler failure → `_writer_best_effort_failures += 1` only (no aggregation to reject_counter)
#### 2.6.6 Asynchronous Purge Archive
Detailed design document §7 and design document §7.5:
- Generation management (`backup_count > 0`) is executed in a separate thread (`PurgeWorker` / `ArchiveWorker`) only when switching files (Fire-and-Forget).
- `archive_mode=False` → old file `unlink`. In the case of `enable_hash=True`, `.sha256` sidecar is also linked and deleted.
- `archive_mode=True` → ZIP compress and save. In the case of `enable_hash=True`, the sidecar is also included in the ZIP.
- Preventing storage exhaustion: Verify free space with `shutil.disk_usage()` and stop processing + warning if insufficient.
- Self-repairability: If deletion/archiving fails due to other Windows process locks, only a warning will be output and a retry will be made at the next switching timing.
- Maintenance serialization of the same family: purge/archive belonging to the same `directory + pg_name` will not be executed in parallel.
#### 2.6.7 Stricter file name filtering
Design document §7.5 provisions:
> When identifying the target file, perform strict filtering to only target file name prefixes that exactly match `pg_name` in order to prevent false matches due to prefix matches of `pg_name` (e.g., a problem where the pattern of `pg_name='App'` also matches `AppServer_*.log`).
Specifically, only files that **exactly match** one of the following patterns are eligible:
- `{pg_name}.log` (NoneStrategy)
- `{pg_name}_{suffix}.log` (Other Strategy)
---

### 2.7 File integrity verification
#### 2.7.1 Design philosophy
Design document §7.6:
- **Generates SHA-256 hashes when the file is switched due to routing, instead of every time it is written**.
- There is no hash on the active file (because hashes in intermediate states are meaningless).
- Does not block main thread I/O at all (separate thread, Fire-and-Forget, but subject to bounded wait in safe shutdown).
#### 2.7.2 Sidecar file (`.sha256`)
`sha256sum -c` compatible formats:
```text
a1b2c3d4e5f6789... (64-character hex SHA-256) MyApp_20260328.log
```

- Separator between hash and file name: **2 half-width spaces** (`sha256sum` compatible)
- File name: **Relative path (file name only)** → Verification will not be broken even if the log set is moved to another location
- Verification: `sha256sum -c MyApp_20260328.log.sha256`
#### 2.7.3 Manifest file
Hash history of all routed files, generated when `manifest_path` is specified.
```text
[2026-03-28T23:59:59.123] a1b2c3d4e5f6789... MyApp_20260328.log
[2026-03-29T23:59:59.456] b2c3d4e5f6789a1... MyApp_20260329.log
```

- Append format. Do not overwrite.
- The timestamp is the date and time when the hash was finalized.
- Serialization: Additions to the same `manifest_path` are always done one thread at a time.
- Operational value: File loss detection (files in the manifest but not on the disk), improved tampering resistance (stored in a separate directory and with different permissions), history overview.
#### 2.7.4 Execution order and threading model
| Condition | Execution method |
|---|---|
| `enable_hash=True` and non-cyclic and `backup_count > 0` | **Execute hash generation in advance** in `PurgeWorker` / `ArchiveWorker` |
| `enable_hash=True` AND non-cyclic AND `backup_count=0` | Fire-and-Forget independent `HashWorker` |
| Cyclic routing and `enable_hash=True` | Output warning to stderr and force overwrite to `enable_hash=False` |
| `enable_hash=False` | No related processing |
For `.sha256` sidecar writing, **atomic replacement by `os.replace()`** is recommended (do not show the partially written state to the outside).
#### 2.7.5 Out of scope
Items explicitly excluded by Design Document §7.6.7:
- **HMAC Signature**: outside the scope of this library as it introduces extraneous responsibilities of key management. The plan is to delegate uses that require signatures to external tools that take the hash of this library as input.
- **CLI verification command**: Since the `sha256sum -c` compatible format allows immediate verification with OS standard commands, no special commands are added.
---

### 2.8 Multiprocess support (`dsafelogger.mp`)
#### 2.8.1 Design Purpose (§11.1)
> Safely aggregate logs generated from multiple processes into one Writer runtime, and reuse the file pipeline (routing / hash / manifest / archive / purge / reopen) that the single-process version already has with its semantics intact.
#### 2.8.2 client / Writer model (§11.5)
| Terminology | Meaning |
|---|---|
| **client process** | The process that makes the log call. Includes main and worker |
| **Writer runtime** | Internal process that owns file sinks and ultimately writes logs from the client |
| **`ctx`** | **opaque and picklable bootstrap object for client process to participate in Writer runtime** |
| **log plane** | One-way path carrying normal log `LogEvent` from client → Writer |
| **control plane** | Route for exchanging control messages such as reopen / detach / stop / status |
Writer runtime is an implementation element inside the logger, and is not something that developers can start directly with `multiprocessing.Process`. The contracts that developers should be aware of are limited to `ctx` / `AttachCurrentProcess()` / `DetachCurrentProcess()`.
#### 2.8.3 `ctx` Contract (§11.7)
`ctx` is **opaque** on the public API and does not show the actual queue or pipe to the developer.
Required information categories for `ctx`:
- protocol version
-Writer session identity
- see log plane endpoint
- see control plane request endpoint
- `protocol_version` verification information at bootstrap ready / attach
-default queue policy
-resolved config digest
-custom level registry hash
- runtime metadata required for attach
Five basic agreements:
- `ctx` is **opaque**
- `ctx` is **picklable**
- `ctx` is **bound by the lifetime of Writer runtime**
- `ctx` is **pickle round-trip verified** when generating `ConfigureLogger()`
- `ctx` must not contain **non-picklable synchronization primitives** (`Event` / `Lock` / `Condition`)
#### 2.8.4 registry hash matching (§11.7)
| Timing | Verification details |
|---|---|
| Writer bootstrap ready ACK | Compare the registry hash sent by the client and the initial registry on the Writer side |
| When running `AttachCurrentProcess(ctx)` | Compare the registry of the current process with the hash in `ctx` |
Mismatch is **Fail-Fast** by `RuntimeError`. The hash algorithm is **SHA-256**.
#### 2.8.5 bootstrap payload construction principles (§11.7)
The design specifies principles to structurally avoid the unpickleability problem of Formatter instances:
- Configuration information included in `ctx` is **raw dict/primitive values ​​only**.
- **Does not include raw instances** of `Strategy` / `Formatter`.
- Formatter normalizes to picklable spec consisting of `kind + constructor args`.
- Rebuild `Strategy` / `Formatter` from the raw config dict / formatter spec received on the Writer side.
- Define `ResolvedConfig` as a pickleable intermediate representation, and redefine it so that it does not hold the `Strategy` instance.
#### 2.8.6 Process payload schema (§11.8)
Four types of payload categories:
| Payload | Direction | Key Fields |
|---|---|---|
| `ctx` | bootstrap | session id / endpoint / protocol version / digest / registry hash / runtime metadata |
| `LogEvent` | client → Writer | route identity / level / logger name / message / source location / process/thread metadata / `_ds_context` / `_ds_extra` / `_ds_diag_frames` / exception payload |
| `ControlRequest` | client → Writer | request id / client id / command type / command payload / picklable reply endpoint |
| `ControlAck` | Writer → client | request id / success flag / error category / error message / result payload |
**Convention**: `_ds_context` and `_ds_extra` of `LogEvent` always exist as keys, and empty is represented as `{}`. Since the distinction by hasattr is not established via pickle, the presence of the key clearly indicates that the snapshot has been acquired on the Capture side.
#### 2.8.7 Fixed reply endpoint (§11.8.3)
v22i fixed:
- The reply endpoint shall be the reply path according to `multiprocessing.Pipe(duplex=False)` of per-request.
- The Queue-in-Queue method, in which a Queue is sent as the payload of another Queue, does not hold due to Python's `multiprocessing` constraint, so it is not adopted.
- Pipe reply endpoint is assumed to be closed by both client and writer after request/ack is completed.
#### 2.8.8 log plane / control plane separation (§11.9)
| Plane | Application | Transport | QoS |
|---|---|---|---|
| log plane | One-way normal log hand-off | bounded `multiprocessing.Queue` | drop (visible reject) when timeout exceeds |
| control plane | reopen / attach / detach / stop / status | Independent queue + per-request Pipe reply | Fixed for each command type |
QoS for each control plane command type (§11.16.3):
- `ATTACH` / `DETACH` / `STOP`: **drop not possible**
- `REOPEN` / `STATUS`: **ACK required**
- `ipc_log_timeout` does not apply to control plane
Design principles (§11.9):
- Do not mix control command with log plane
- Do not mix ACK in log plane
- Do not include non-picklable synchronization objects in the control payload
- Pipe send/recv failure is normalized to `RuntimeError` system as control plane failure without leaking raw `BrokenPipeError` / `EOFError` to the outside.
#### 2.8.9 queue capacity and `ipc_log_timeout` (§11.16)
| Setting items | Default value | Range | Environment variable |
|---|---|---|---|
| `ipc_log_queue_maxsize` | 10000 | `ValueError` in `<=0`, warning in `>100000` | `{prefix}_IPC_LOG_QUEUE_MAXSIZE` |
| `ipc_client_queue_maxsize` | Equivalent to `ipc_log_queue_maxsize` | `<=0` to `ValueError` | `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` |
| `ipc_log_timeout` | 0.5 seconds | `ValueError` in `<=0`, warning + clip in `>3.0` | `{prefix}_IPC_LOG_TIMEOUT` |
| `MAX_IPC_LOG_TIMEOUT_SECONDS` | 3.0 (internal limit) | Absolute line of defense for the framework | — |
> Design decision: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` is an absolute upper limit that does not cause the normal log producer path to be blocked for too long. The queue is taken as an upper limit long enough to wait for natural recovery from temporary saturation, but not so long as to irreversibly harden the GUI thread or request handler thread.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.16.1)
v23h revised: **`ValueError`** (fail-fast from warning + ignore) if environment variable value cannot be interpreted as int / float.
#### 2.8.10 Overflow policy (§11.16.2)
- **Drop record** when `ipc_log_timeout` exceeds or `queue.Full`.
- When dropping, increment the drop counter on the client side.
- stderr warning on first drop occurrence and subsequent summary timings.
- Silent drop is not performed.
#### 2.8.11 `TrackedQueue` (v23h, §11.16.1)
The implementation of log plane queue uses `TrackedQueue`, which is derived from `multiprocessing.queues.Queue`.
- Automatic fallback to `multiprocessing.Value` counter only when `super().qsize()` is **exception probed** and `NotImplementedError` is caught in the constructor.
- Identification independent of OS name (such as macOS). Works correctly on future or minor unsupported platforms without additional support.
#### 2.8.12 attach/detach (§11.13, §11.21)
Responsibilities of `AttachCurrentProcess(ctx)`:
- Verification of `ctx`
- Generate process-local reply endpoint
- Sending an ATTACH request
- update process-local attach state
- process-local application of `logging.setLoggerClass()`
- Enable Capture → Writer hand-off
Idempotency:
- Reattach to same `ctx` is no-op (if necessary, only regenerate process-local thread / transport)
- Reattach to another `ctx` is `RuntimeError`
`fork` Relationship with inheritance (§11.13.3):
- In POSIX forks, the attach state of the parent process can be inherited. v22i treats this as a normal case.
- However, since fork only copies the main thread, `is_async=True`'s process-local pump thread etc. must be regenerated on the child process side.
- Fork the child after completing logger initialization and attach on the parent side. Forking while `ConfigureLogger()` / `AttachCurrentProcess()` is running is prohibited.
- Constructed only while the Writer session persists. STOP If the session has been accepted, is draining, or has ended, the child must not automatically revive the same session.
#### 2.8.13 Conditions for establishing the multiprocess version of Drop-in Replacement (§11.14)
- `dsafelogger.mp.ConfigureLogger()` applies `logging.setLoggerClass()` to the calling process.
- `AttachCurrentProcess(ctx)` also reapplies process-local to attach target process.
- In the worker process after attach is completed, all of `GetLogger()` / `logging.getLogger()` / **`logging.getLogger()`** called internally by the third party library are aggregated into Writer.
#### 2.8.14 Definition of terms for delivery status (§12.3)
Design document §12.3 defines hierarchically.
**Lifecycle states**:
| Terms | Definitions |
|---|---|
| `attempted` | Log call passed by user code to logger |
| `accepted` | Level judgment and client-side filter passed, and transport assumed delivery responsibility |
| `enqueued` | accepted log submitted to client-local queue or mp log queue |
| `delivered_per_sink` | Pass the flush contractual completion point in target sink units |
| `delivered` | `delivered_per_sink` holds true for all required sink sets |
**Terminal states**:
| Terms | Definitions |
|---|---|
| `rejected` | Failure to accept delivery responsibility due to timeout / closed / invalid state / Writer unavailable, etc. |
Discarded after | `dropped` | accepted or at local queue stage. It should not be silent and will be reflected in counter / warning / summary |
| `writer_reject` | After reaching the writer, it is judged as undeliverable by route / sink / writer-side policy |
| `partial_delivered` | Only part of the required sink set was reached. It should not be silent and will be reflected in counter / warning / summary |
| `unexpected_loss` | accepted, but it is not recorded as dropped/rejected/writer_reject/partial_delivered, and it is not recorded as delivered after shutdown. **Treat as a design or implementation bug** |
**Policy qualifier**:
| Terms | Definitions |
|---|---|
| `overload_shed` | OOM / Permanent block / Assigned to rejected or dropped that was explicitly discarded by the bounded queue / timeout policy to avoid the main body involvement stop |
The required sink set is defined mainly around file sinks. The console sink will be a best-effort sink, and will be subject to a warning/counter in the event of failure, but will be separated from `unexpected_loss` of file delivery.
#### 2.8.15 Breakdown of `writer_reject` (§12.3)
| Classification | Definition |
|---|---|
| `writer_route_reject` | route unresolvable, or route target sink absent |
| `writer_reconstruct_reject` | Corruption/reconstruct failure of LogEvent (separated from `writer_event_reject` in v23h) |
| `writer_close_marker_reject` | Invalid CloseMarker (missing client_id / session mismatch / unknown client. Separated in v23h) |
| `writer_sink_reject` | Required sink exists but emit / write / flush fails (per record) |
| `writer_policy_reject` | Delivery refusal due to required handler filter or Writer side policy |
| `writer_format_reject` | formatter / JSON encode not possible. Folded into `writer_sink_reject` in v23h |
| `writer_best_effort_failures` | Best-effort sink (console, etc.) emit failure. Do not include in terminal state of `writer_reject` |
All are assigned a dedicated counter and stderr warning (rate-limited). Structurally does not allow silent failure.
#### 2.8.16 shutdown ordering and active client registry (§11.21)
`AttachCurrentProcess()` Upon success, Writer registers client in **active registry**.
stop judgment:
1. Received a stop request from main side
2. The number of active clients must be 0.
When both conditions are met, proceed to shutdown.
**Registry consistency during worker crash**:
- If the worker process terminates without sending `DETACH`, there may be residuals in the active client registry.
- Set an **internal timeout** to wait for the number of active clients to be 0 during shutdown.
- When timeout is reached, issue **stderr warning** and transition to forced stop.
- **Do not cause a silent hang**.
shutdown ordering:
1. Drain client side async queue
2. Completed sending from client to Writer
3. client sends detach / close
4. Writer side drains log plane queue
5. Writer side closes sink handlers / hash / manifest finalize
6. Writer runtime ends
#### 2.8.17 Bounded shutdown contract (v23h, §12.4.1)
A silent hang should not occur even if the normal termination path is shutdown. `mp.ConfigureLogger()` calls `_mp_shutdown` → `WriterRuntime.stop()` on `atexit`, but `stop()` is subject to the following bounded contract:
- `stop(timeout)` waits for `log_thread` / `control_thread` to join for a maximum of `timeout` seconds (default `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`).
- If the thread is alive after timeout, **outputs a visible warning to stderr** (includes the stuck thread name and does not make it a silent failure).
- Writer `log_thread` / `control_thread` starts with **`daemon=True`**, so even if stop() fails to complete drain, the Python interpreter can exit (process survives principle).
```text
bounded wait (≤ timeout) → visible warning (expose incomplete drain) → process exits
```

Prevents the host process from blocking permanently even if an unknown hang is mixed in the drain route. Drain integrity is ensured by `stop()`'s serial drain logic, and the daemon flag is only used for fail-safe escapes.
#### 2.8.18 Writer flush strategy (v23g, §11.27)
The per-message flush of the multiprocess version of Writer will be maintained as the default behavior (§12.2 ``Weakening the flush contract''). For high-throughput applications, you can opt-in to batch flush with `ConfigureLogger(writer_flush_batch=N)`.
| `writer_flush_batch` | Operation | Assumed use |
|---|---|---|
| `1` (default) | per-message flush. No loss during Writer process crash | High durability requirements |
| `2 – 64` | Flush every N items + idle flush when queue empty. Possibility of loss of up to N-1 items during process crash | Throughput priority |
| `> 64` | Same as above, but with high risk of reduced visibility | Special uses |
Can be overridden with environment variable `{prefix}_WRITER_FLUSH_BATCH`. Warning in `ValueError` and `>1024` in `<=0`. `WriterRuntime.__init__` also plays `ctx.writer_flush_batch < 1` as `ValueError` (safety net of `BootstrapContext` direct construction route).
§12.3 Correspondence with terms:
- For `writer_flush_batch=1`: dispatch completed = matches `delivered_per_sink`.
- For `writer_flush_batch>1`: Set the batch flush completion point to the arrival point of `delivered_per_sink`. **Per-message visibility is not guaranteed once the user opts in**.
In the multiprocess route, the Configure layer sets `stream_flush_on_emit` of the Sink (`AppendOnlyFileHandler`) to `False`, and the Writer (`_mp_runtime.py`) centrally controls batch / per-message.
#### 2.8.19 `ReopenLogFiles()` is the control plane (§11.20)
`ReopenLogFiles()` in the multiprocess version is a synchronous API that sends a control request from an attached client process and waits for an ACK.
- Can be called from any attached client process
- Serialization responsibility for reopen is on the Writer side
- ACK timeout: internal constant `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` (do not add timeout argument to public API signature)
> Design judgment: The basis for 5.0 seconds is a value that takes into account the typical postrotate script execution time in logrotate/cron operation (within a few seconds) and the margin for the reopen processing time on the Writer side (usually several tens of ms).
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.20.3)
#### 2.8.20 mp_context (§11.12)
`mp_context` is `multiprocessing` context that should be shared by Writer runtime and worker processes.
- Reception type: `None` / `'spawn'` / `'fork'` / `'forkserver'` / `multiprocessing.context.BaseContext`
- Default resolution: `mp_context=None` → **Leave to Python default context** (The library does not perform its own fallback based on OS determination)
- When `mp_context` is specified, **consistently applied to all IPC primitive generation for log/control queue and Pipe reply path**
> Note: Python default multiprocessing context is OS and Python version dependent. If you port `mp_context=None` as is, the attach behavior and initialization requirements may change depending on the start method.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.12)
---

### 2.9 Overload Policy and Survival-first Policy
#### 2.9.1 Classification of v23 series (§12.4)
Do not treat log loss uniformly as the same problem.
| Classification | Treatment |
|---|---|
| `unexpected_loss` | Bug. accepted The log has disappeared for no reason and should be detected by sequence integrity verification |
| policy-driven `rejected` | A state in which the request is rejected due to timeout / closed / writer unavailable, etc. before assuming delivery responsibility. Explicit recording required |
| policy-driven `dropped` | State explicitly discarded to protect the main unit due to bounded queue overflow, etc. counter / warning / summary required |
#### 2.9.2 Default policy
```text
bounded wait → visible reject/drop → process survives
```

A policy that prioritizes the survival of the main process rather than retaining logs indefinitely and performing OOM, or permanently blocking the main process and causing a service outage.
#### 2.9.3 Default prohibitions (§12.4)
| Prohibitions | Reasons |
|---|---|
| unbounded log queue | Unlimited increase in OOM risk when Writer stops or output is clogged |
| indefinite producer block | Involve GUI / Web handler / worker loop with log output |
| silent drop | Operator cannot detect log loss |
| Confusing overflow with `unexpected_loss` | Design bug and misjudging overload policy |
The design document shall specify:
> When adding strict lossless mode, unbounded queue, or a mode that allows OOM risk, be sure to ask the user's judgment as it relates to the safety policy of D-SafeLogger.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §12.4)
---

### 2.10 Concurrency safety and free-threaded support
#### 2.10.1 Explicit locking of shared state (§9.2, §2 v21)
The design document clearly states the policy of not relying on the existence of GIL or the internal lock of `list` / `dict` as safety grounds.
- `_configure_state` / `_active_pipeline` / `_active_workers` / `_custom_levels` are protected with **explicit lock**.
- Execute entire `_do_configure()` of `ConfigureLogger` under `_lifecycle_lock` retention.
- `GetLogger` detects `'configuring'` state and waits for lock structure.
- The independent `self._lock` of `AppendOnlyFileHandler` has been abolished in v21 and unified to the `acquire()` / `release()` API of the parent class `logging.Handler` (double lock overhead eliminated).
#### 2.10.2 cross-thread safety (§9.4)
In a free-threaded build, a `f_locals` live reference to the frame of another running thread is unsafe.
- If a cross-queue hand-off occurs, traceback and `f_locals` are converted to a **safe masked, repr-converted snapshot** on the producer thread side.
- No live references are made on the consumer thread side.
Fallback rules:
1. Use queue hand-off diagnostic snapshot if available
2. Live reference is allowed only if `exc_info` is held within the same thread
3. Otherwise output only standard traceback
#### 2.10.3 Thread boundary semantics (§9.5)
- Initial context inheritance to a new thread created by the user follows the Python specifications.
- The internal thread generated by D-SafeLogger itself **always starts with empty `Context`**. This prevents context from leaking to internal threads.
---

### 2.11 Design characteristics at the specification level
From the materials reviewed in this chapter, we will organize the attitudes observed at the specification/design level.
#### 2.11.1 "Make the determined location unique" merge order
The three-layer configuration management pipeline (§2.3) has a structure in which ``there are three paths to overwrite the same configuration item, but which one is the final decision maker is always determined''. This contrasts with "configure freely whenever" models like Loguru's `add()`, which allows you to trace back where settings were made.
#### 2.11.2 “Keep responsibility boundaries harder than process boundaries”
Capture/Transport/Sink three-layer separation (§2.1.2) does not change responsibility boundaries for single-process or multiprocess. In multiprocess, the Transport boundary only goes through IPC, and Capture (`logging` compatible semantics) and Sink (routing / hash / manifest) have the same structure. This is a design attitude that ``does not treat multiprocess as a special case.''
#### 2.11.3 “Classify failure” delivery status
The delivery state hierarchy in §12.3 does not uniformly treat missing logs as "lost," but classifies them into six types of terminal states (rejected / dropped / writer_reject / partial_delivered / overload_shed / unexpected_loss). Only `unexpected_loss` is treated as a "bug", and the others are treated as "explainable facts" derived from policy.
#### 2.11.4 “Fix the absolute defense line with internal constants”
**Internal hard limits** such as `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` (§2.8.9), `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` (§2.8.19), and `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0` (§2.8.17) are fixed with evidence in the body of the design document. This is a structural guarantee that ``even if the user sets an arbitrarily large value, it will not exceed the length at which the host process is irreversibly hardened on the library side.''
#### 2.11.5 "Make opt-in a boundary for semantic change"
`writer_flush_batch=1` (default) and `writer_flush_batch>1` (opt-in) change the meaning of the destination of `delivered_per_sink` (§2.8.18). The specification clearly states that "per-message visibility is not guaranteed" the moment the user opts in. This is the attitude of ``not silently mixing multiple semantics in the same API.''
#### 2.11.6 "Do not change standards to maintain standardness"
- Do not use global side effects of `addLevelName()` (§2.4.5)
- Do not modify `record.levelname` (§2.4.4)
- Fully override `QueueHandler.prepare()` (separate semantics from stdlib differences, §2.5.4)
- Do not force fallback of `multiprocessing.context` in library (§2.8.20)
These are design approaches that structurally guarantee that ``other code and libraries built on top of stdlib do not violate their assumptions due to the existence of this library.''
---

### 2.12 Summary of specifications and design
The materials reviewed in this chapter can be summarized as follows.
1. **Physical module configuration is localized in 25 files + `mp/` namespace**: Public API entrances are only 2 files `__init__.py` and `mp/__init__.py`, all others are private (`_` prefix). This keeps the public surface area small.
2. **3-layer separation (Capture / Transport / Sink) is operated as a design invariant that extends between single-process and multiprocess**: Design document §11.3 and §12.1 clearly state this as one of the Writer invariants, and fix the boundary as ``In multiprocess, Capture semantics must not be re-executed on the Writer side.''
3. **Configuration merging is a combination of 3-layer strict merging + Fail-Fast**: The overwriting order of environment variables > INI/dict > arguments is combined with the principle of not allowing silent fallbacks (type invalidity is `ValueError`). This structurally eliminates the situation where the settings appear to be reflected but are not.
4. **Sanctuary (only environment variables can be set) is clearly specified**: `diagnose` / `sens_kws` / `sens_kws_replace` / `file_fmt` / `console_fmt` have blocked the configuration paths to the 1st layer, 3rd layer, and 2nd layer for their own reasons.
5. **Delivery states are hierarchically verbalized into 5 + 6 + 1 terms**: Lifecycle states 5 (attempted / accepted / enqueued / delivered_per_sink / delivered), Terminal states 6 (rejected / dropped) / writer_reject / partial_delivered / unexpected_loss / writer_best_effort_failures are recorded separately), Policy qualifier 1 (overload_shed). These are officially defined in §12.3 of the design document and are directly mapped to each counter / warning / summary.
6. **`writer_reject` was classified into 6 classifications + 1 separation in v23h**: route / reconstruct / close_marker / sink / policy / format, and `writer_event_reject` was separated into `writer_reconstruct_reject` and `writer_close_marker_reject`. This prevents abnormal events from being combined into the same counter, improving diagnostic granularity.
7. **The absolute defense line is fixed with three internal constants**: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`. Both of these are placed in the design document with evidence as upper limits that "do not irreversibly harden the host process."
8. **The picklability constraints of the bootstrap payload are structurally carried through to the custom Formatter**: `ctx` only contains the picklable spec (kind + constructor args), not the raw instances of `Strategy` / `Formatter`. The design of rebuilding on the Writer side structurally avoids the unpickleable problem caused by custom Formatter subclasses and closures.
9. **Bounded shutdown contract realizes "process exits" as fail-safe in combination with daemon=True**: `stop(timeout)`'s combination of bounded join + visible warning + daemon thread guarantees the Python interpreter's exit even if an unknown hang is mixed in the drain path. A silent hang cannot occur structurally.
10. **Weakening of the flush contract is only allowed for opt-in only**: Maintain the per-message visibility contract of `writer_flush_batch=1` (default), and transition to `>=2` requires explicit opt-in by the user and specifies that per-message visibility will be lost at that point. **There is a clear line between ``do not break durability by default''**.
11. **The difference between fork / spawn / forkserver is explicitly exposed to developers in `mp_context`**: The meaning of `mp_context=None` is "Leave to Python defaults", and the library does not introduce OS determination. This is an expression of the design attitude that ``if a portability problem occurs, the library will not solve it on its own.''
12. **The native qsize fallback of TrackedQueue is implemented with an exception probe that does not depend on the OS name (v23h)**: Since it is determined whether or not to call `super().qsize()` and capture `NotImplementedError`, it will work correctly even on future or minor unsupported platforms without additional support.
---

### 2.13 Summary of this chapter
The specifications and design of D-SafeLogger v23k can be summarized into the following five points:
1. **Operate the three-layer structure (Capture / Transport / Sink) as an invariant condition**: Responsibility boundaries do not change in either single-process or multiprocess, and in multiprocess, the Transport boundary only goes through IPC.
2. **3-layer configuration pipeline (environment variables > INI/dict > arguments) + Fail-Fast + Sanctuary**: The configuration override route is uniquely determined, and specific settings (diagnose / sens_kws / fmt instance) block the route.
3. **Layer the delivery status using 5 + 6 + 1 terms and treat only `unexpected_loss` as a bug**: The remaining 6 types of terminal states are all derived from policy and are classified as "explainable facts" and are reflected in counter / warning / summary.
4. **Fix the absolute line of defense with internal constants and guarantee bounded shutdown with daemon thread**: The upper limit that does not make the host process irreversible is fixed with three constants, and the shutdown path is realized as fail-safe for "process exits" by the combination of visible warning + daemon thread.
5. **Explicit semantic change at opt-in boundary**: Specifies that `writer_flush_batch>1`'s opt-in loses per-message visibility, and does not weaken the durability contract by default.
These specification facts are revisited in the next chapter, “3. Usability,” from the perspective of public APIs, INI/dict configuration, environment variables, and examples, and again in Chapter 5, “Detailed Analysis by Function,” as the behavior of individual features.
---

> **Main reference materials for this chapter**: `docs/design/D_SafeLogger_Specification_v23k_full.md` §3, §4, §5, §6, §7, §9, §10, §11, §12 / `docs/design/D-SafeLogger_DetailedDesign_v23k.md` §1, §2, §4, §5, §6, §7, §8, §11, §15a / `docs/api/dsafelogger*.md` / `src/dsafelogger/` Module configuration / `pyproject.toml`
> This document is intended to explain and evaluate the current v23k architecture, and does not include improvement proposals, issue management, or future roadmaps.
## Chapter 3 Usability
### 3.1 Public API surface
#### 3.1.1 Entrance is 2 functions
Typical use of D-SafeLogger is completed with two functions: **`ConfigureLogger()` and `GetLogger()`**.
```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path='./logs', pg_name='MyApp')
logger = GetLogger(__name__)
logger.info('Application started')
```

`examples/01_quick_start.md` presents these three lines as "your first log". Example output:
```text
2026-04-03 09:15:22.738 [INF][app.py:4:<module>] Application started
```

As specified in Design Document §10.1, `ConfigureLogger()` has 26 arguments, but all of them have default values, and for minimum use only two, `log_path` and `pg_name`, are sufficient.** The remaining arguments are added in stages (§3.2).
#### 3.1.2 Auxiliary API
| API | Role | Timing |
|---|---|---|
| `contextualize(**kwargs)` | Automatically assigns an identifier to the log in a thread/asyncio task | Any scope |
| `register_level(name, value, abbreviation, color)` | Registering a custom log level | Before `ConfigureLogger()` |
| `ReopenLogFiles()` | Re-open after external log rotation | Any |
All of these are optional and ``if you don't use them, they don't exist'' by design (Design document §9.9/§15a).
#### 3.1.3 multiprocess entrance
Separated into `dsafelogger.mp` namespace (Design document §11.4). The public API has the following 6 functions:
```python
from dsafelogger import mp

ctx = mp.ConfigureLogger(log_path='./logs', pg_name='MPDemo', mp_context=proc_ctx)
mp.AttachCurrentProcess(ctx) # in worker
logger = mp.GetLogger(__name__)
mp.DetachCurrentProcess() # When worker ends
mp.ReopenLogFiles() # optional
init_fn, init_args = mp.GetWorkerInitializer(ctx) # When linking Pool/Executor
```

Design document §11.4 explains the reason for separation as ``the simplicity of the single-process version (completed with one Configure operation) and the complexity of the multiprocess version (attach contract, shutdown synchronization) should not be semantically mixed.''
---

### 3.2 Scaling from minimal code
#### 3.2.1 Incremental feature addition
`examples/01_quick_start.md` shows that the same `ConfigureLogger()` can be extended step by step just by adding parameters.
```python
# Stage 1: console + file logging
ConfigureLogger(log_path='./logs', pg_name='MyApp')

# Stage 2: Daily Routing
ConfigureLogger(log_path='./logs', pg_name='MyApp', routing_mode='daily')

# Stage 3: Routing + JSON Output + Integrity Hash
ConfigureLogger(
    log_path='./logs', pg_name='MyApp',
    routing_mode='daily', structured=True, enable_hash=True,
)
```

At each stage, there is no need to change call sites such as **`logger.info()`**. This is consistent with "extends the standard logging path rather than replacing it" in the README "Why D-SafeLogger?" section.
#### 3.2.2 auto-fire (implicit initialization)
Design document §9.2 and `examples/01_quick_start.md` GetLogger Auto-Fire section:
```python
from dsafelogger import GetLogger

logger = GetLogger(__name__)
logger.info('This just works')
```

If `GetLogger()` is called without explicitly calling `ConfigureLogger()`, `ConfigureLogger()` is internally auto-fired with the default argument (state transitions to `auto`).
- Intended use: notebook, one-shot script, simple CLI
- Note: Explicit `ConfigureLogger()` after entering `auto` works correctly as **old Pipeline stop → reinitialize** (explicit priority semantics)
- Multiprocess version (`dsafelogger.mp.GetLogger`) does not auto-fire (`RuntimeError`). Fail-Fast detection of forgetting to attach
#### 3.2.3 Graduality of arguments stipulated by Design Document §10
If we organize the arguments of `ConfigureLogger()` into usage groups, we can see a typical scaling path.
| Usage | Arguments |
|---|---|
| Minimum startup | `log_path`, `pg_name` |
| Output level control | `default_level`, `console_out` |
| File generation management | `routing_mode`, `interval`, `max_bytes`, `max_lines`, `max_count`, `suffix_digits`, `backup_count`, `archive_mode` |
| Structured log | `structured` |
| Custom format | `fmt`, `file_fmt`, `console_fmt`, `datefmt` |
| Integrity verification | `enable_hash`, `manifest_path` |
| Confidential masking | `sens_kws`, `sens_kws_replace` |
| Externalizing settings | `config_file`, `config_dict`, `env_prefix` |
| async I/O | `is_async` |
| multiprocess | `worker_model`, `mp_context`, `ipc_log_timeout`, `ipc_log_queue_maxsize`, `ipc_client_queue_maxsize`, `writer_flush_batch` |
Corresponding to the positioning (D ecosystem common platform) in §1.1.2 of the design document, the structure is such that everything from minimum startup to auditing and compliance support is expressed in the parameter space of the same API.
---

### 3.3 Operating the three-layer configuration pipeline
#### 3.3.1 Role division
Typical role division shown by `examples/02_configuration_guide.md`:
| Layer | Role | Assumed change agent |
|---|---|---|
| Layer 3: Arguments | Developer default values (fallback) | Application developer |
| Second layer: INI / dict | Deployment baseline (different for each environment) | DevOps / SRE |
| Layer 1: Environment variables | Runtime overrides (change without redeployment) | on-call / operators |
This use case table is specified in the "The Problem" section of `examples/02_configuration_guide.md` as an example of 3 environments x 3 setting items (DEBUG/INFO/WARNING, none/daily14/daily30, color/JSON/JSON+hash).
#### 3.3.2 Emergency override using environment variables (example)
Typical operation shown by `examples/02_configuration_guide.md` and design document §4:
```bash
# Set the overall level to WARNING
D_LOG_LEVEL=WARNING python app.py

# By module: DEBUG db, ERROR api, separate file
D_LOG_MODULES=myapp.db:DEBUG,myapp.api:ERROR:/var/log/api.log python app.py

# Enable diagnostic mode only once
D_LOG_DIAGNOSE=1 python app.py

# Enable JSON output + hash generation only in production
D_LOG_HASH=true D_LOG_MANIFEST=/var/log/audit/checksums.txt python app.py
```

Design document §4.2 / §4.3 provisions:
- `{prefix}_LEVEL` is global only, comma separated **Error message prompting you to migrate to `MODULES` with `ValueError`**
- Individual `MOD_SPEC` of `{prefix}_MODULES` Format violation occurs only in the relevant element stderr warning + Skip (other elements continue to be applied)
- `{prefix}_DIAGNOSE` is valid only for `"1"`. `"true"` / `"yes"` / `"True"` are invalid
#### 3.3.3 Namespace separation with `env_prefix`
Design document §10.1 / §4 / §4.6:
```python
ConfigureLogger(env_prefix='ORDER_LOG', ...)
```

As a result, the subsequent control environment variables will be `ORDER_LOG_LEVEL` / `ORDER_LOG_MODULES` / `ORDER_LOG_CONFIG`, etc. Enables separation of environment variable namespaces for multiple D-SafeLogger instances on the same machine. Since `NO_COLOR` is an industry standard, it is not affected by `env_prefix` (§4.5).
---

### 3.4 INI / dict settings
#### 3.4.1 INI template generation
`examples/02_configuration_guide.md` and `examples/14_cli_operations.md` show:
```bash
dsafelogger init > logging.ini
```

Design document §8.1.1: The template outputs to **standard output** and does not take a file path argument (the user controls the save destination with redirection). All configuration keys are commented out in the template, and inline comments explain each key's role and option choices.
#### 3.4.2 Section by module
Example of full-scale operation shown by `examples/02_configuration_guide.md` and design document §5.4:
```ini
[global]
default_level = INFO
log_path = /var/log/myapp
pg_name = OrderService
routing_mode = daily
backup_count = 30
structured = true
enable_hash = true

[dsafelogger:myapp.db]
level = DEBUG
path = db_queries.log

[dsafelogger:myapp.api]
level = WARNING

[dsafelogger:myapp.tasks]
level = INFO
path = background_tasks.log
```

Design document §5.4 provisions:
- If `path` is omitted, the global settings (`log_path` / `pg_name`) will be inherited, and the routing will be `none` by default.
- `routing_mode` when `path` is specified Default is `none` (assuming simple case with no rotation required)
- If a routing-related key such as `routing_mode` is specified when `path` is omitted, stderr warning + the key will be ignored.
#### 3.4.3 `config_dict` (Dictionary in code)
Design document §5.7:
```python
ConfigureLogger(
    config_dict={
        'global': {
            'default_level': 'INFO',
            'log_path': './logs',
            'backup_count': '30',
        },
        'dsafelogger:myapp.db': {
            'level': 'DEBUG',
        },
        'dsafelogger:myapp.api': {
            'level': 'ERROR',
            'path': '/var/log/myapp/api.log',
            'routing_mode': 'size',
            'max_bytes': '10485760',
        },
    }
)
```

- All values are strings (because they go through the same type conversion and validation pipeline as INI)
- `int` / `bool` Direct specification is `TypeError` (Fail-Fast)
- `config_file` and `config_dict` are exclusive (`ValueError` when both are specified)
- `examples/02_configuration_guide.md` described as "particularly useful in test environments and use cases that generate configurations programmatically"
#### 3.4.4 INI and environment variable merging priority
Example of `examples/02_configuration_guide.md` and design document §5.5:
```ini
[dsafelogger:myapp.db]
level = DEBUG
path = /var/log/db.log
routing_mode = daily
```

```bash
D_LOG_MODULES=myapp.db:ERROR
```

- Level of `myapp.db` is overwritten by `ERROR`
- Since only `MOD:LEVEL` (no path) is specified in the environment variable, `path`, `routing_mode`, etc. on the INI side are **all maintained**
- Environment variable `{prefix}_MODULES` only overrides the level and output path; INI side routing details are not affected.
---

### 3.5 Seventeen example scenarios
The 17 files under `examples/` are organized in the following reading order in the README "Tutorials / Examples" section.
| Number | File | Theme |
|---|---|---|
| 1 | `01_quick_start.md` | Install / configure / first log |
| 2 | `02_configuration_guide.md` | Code / INI/dict / env layers |
| 3 | `03_migration_from_stdlib.md` | Migration from stdlib `logging` |
| 4 | `04_stdlib_ecosystem_coexistence.md` | stdlib-based ecosystem coexistence |
| 5 | `05_windows_service_and_scheduled_batch.md` | Windows service / scheduled batch |
| 6 | `06_web_api_logging.md` | Request-correlated structured logs |
| 7 | `07_long_running_service.md` | Routing / retention / archival |
| 8 | `08_compliance_audit.md` | SHA-256 integrity / audit logs |
| 9 | `09_debugging_production.md` | Diagnostic mode / masking |
| 10 | `10_incident_response_bundle.md` | Incident response bundle |
| 11 | `11_async_performance.md` | Queue-backed async logging |
| 12 | `12_multiprocess_logging.md` | Worker logging through parent-side Writer |
| 13 | `13_external_rotation_reopen.md` | Reopening files after external rotation |
| 14 | `14_cli_operations.md` | `dsafelogger` CLI |
| 15 | `15_opentelemetry_logging.md` | Trace correlation with stdlib instrumentation |
| 16 | `16_structlog_coexistence.md` | structlog coexistence (Pattern A/B) |
| 17 | `17_container_collector_coexistence.md` | container / collector coexistence |
The README recommends the following reading order:
| Learning Path | Number |
|---|---|
| Getting started | 01, 02, 03 |
| stdlib / ecosystem integration | 03, 04, 15, 16 |
| Windows / service operations | 05, 07, 13, 14 |
| Application patterns | 06, 10, 11, 17 |
| Audit / incident response | 08, 09, 10 |
| Multiprocess logging | 12 |
Examples 01 and 02 are introductory tutorials, while examples 03 and later are concrete scenario guides. Runnable scenario tests under `tests/examples/` cover 03-17; 01 and 02 are treated as introductory documentation rather than standalone scenarios.

The fact that the paper is devoted to the thickest sections 12 (multiprocess) and 03 (stdlib migration) reflects the intended readership of this product (existing stdlib `logging`-based apps + audit/multiprocess operations).
#### 3.5.1 Characteristics by learning path
##### Getting started (01/02/03)
- **01**: Introducing features that are added step by step from a startup example with a minimum of 3 lines. Output example for all 5 levels from `logger.debug` to `logger.critical`.
- **02**: Specification of the division of roles in the 3-layer pipeline (dev / staging / prod) using a 3 × 3 table.
- **03**: Three migration patterns from stdlib `basicConfig` / `TimedRotatingFileHandler` / `dictConfig` are presented before/after (detailed in §3.7).
##### stdlib / ecosystem integration (03 / 04 / 15 / 16)
- **03**: Migration from stdlib `logging`. Setup code moves to D-SafeLogger while existing `logger.info()` call sites remain unchanged.
- **04**: Coexistence with the stdlib logging ecosystem. Existing loggers from SQLAlchemy / Django / requests / boto3 can be collected.
- **15**: OpenTelemetry trace correlation. Extra field injection by `contextualize(trace_id=..., span_id=...)` instead of OTel SDK's logging exporter.
- **16**: structlog coexistence. There are two methods: Pattern A (dual stream of JSON in structlog and human text in D-SafeLogger) and Pattern B (assembly of event in structlog -> routing/output pipeline in D-SafeLogger).
##### Windows / service operations (05 / 07 / 13 / 14)
- **05**: Windows service / scheduled batch. Append-only output avoids Windows rename and file-lock issues.
- **07**: Long-running services. daily routing + retention + archive.
- **13**: Coexistence with external rotators (logrotate, etc.). Officially supported only on `routing_mode='none'`.
- **14**: How to use CLI tool 3 commands (init / ls / tail -f).
##### Application patterns (06 / 10 / 11 / 17)
- **06**: Web API pattern. Structured logs add request_id / user_id through `contextualize()`.
- **10**: Incident response bundle. Steps to collect structured logs, diagnostics, hashes, and manifests.
- **11**: Queue-backed asynchronous hand-off due to `is_async=True`.
- **17**: container / collector coexistence. External collectors ship logs while local JSONL remains available.
##### Audit / incident response (08 / 09 / 10)
- **08**: SHA-256 sidecar / manifest / `sha256sum -c` compatibility verification / operation example for audit log.
- **09**: production debugging. A working example of how to use `D_LOG_DIAGNOSE=1` and sens_kws masking.
- **10**: Incident response bundle. Concrete evidence collection for abnormal conditions.
##### Multiprocess logging (12)
- **12**: 438 lines and maximum for all examples. 3 patterns of Process / Pool / Executor, Windows spawn rules, attach/detach lifecycle, environment knobs, failure mode list, shutdown summary interpretation.
---

### 3.6 CLI tool `dsafelogger`
#### 3.6.1 Three commands provided
Design document §8 and `examples/14_cli_operations.md`:
| Command | Role |
|---|---|
| `dsafelogger init` | Output INI configuration file template to **standard output** |
| `dsafelogger ls [log_dir]` | Parse the D-SafeLogger files in the specified directory, group by program name, and display a list |
| `dsafelogger tail -f <log_dir> <pg_name> [options]` | Automatically determines and follows the latest log file of the specified program |
#### 3.6.2 Significance of `tail -f` that “automatically detects and follows the latest file”
Design document §8 Beginning:
> Append-Only routing has the advantage of avoiding fatal file locks, but has the disadvantage that ``Since the file name of the writing destination changes dynamically, it is not possible to always write the same `app.log` to `tail -f`.'' To overcome this, a set of dedicated CLI utilities is included in the package.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §8)
The role of the CLI is to compensate for the operational weaknesses of the Append-Only model, and it is provided as part of the library itself.
> Transparent file tracking: Even if the source application changes files due to log ``day crossing'' during output, the CLI dynamically detects this and transparently replaces the `tail` destination with the new file and continues outputting.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §8.1)
#### 3.6.3 Designing `init` assuming redirection
Design document §8.1: The design intention for `init` to output to standard output without taking a file path argument is as follows.
- Avoid complications such as checking to overwrite existing files
- facilitates combination with pipe redirection
- `dsafelogger init | less` (check contents) / `dsafelogger init > logging.ini` (save) are established with equal naturalness
#### 3.6.4 Omitting hyphens in command names
Design document §8.1: Adopted PyPI package name `dsafelogger` by removing the hyphen from `d-safelogger`. Naming decisions that give priority to omitting hyphens when typing in the shell. The import name matches `dsafelogger`, so it is a good design to remember the same name for Python and CLI.
---

### 3.7 Migration from stdlib `logging`
#### 3.7.1 Three typical migration patterns
`examples/03_migration_from_stdlib.md` indicates before/after:
##### Pattern 1: `basicConfig` → `ConfigureLogger`
| Before (stdlib) | After (D-SafeLogger) |
|---|---|
| 11 lines (`basicConfig` + 2 handler settings) | 4 lines (`ConfigureLogger` + `GetLogger`) |
What you get: source location (`[file:line:func]`), millisecond timestamps, automatic directory creation, ANSI colors, consistent formatting across all loggers.
##### Pattern 2: `TimedRotatingFileHandler` → `routing_mode`
| Before (stdlib) | After (D-SafeLogger) |
|---|---|
| 16 lines (`os.makedirs` + handler + suffix + formatter + addHandler + setLevel) | 7 lines |
What you get: append-only strategy (no midnight rename, no Windows locking issues), SHA-256 option, automatic purge/archive.
##### Pattern 3: `dictConfig` → `config_dict`
The 4-layer structure of `version: 1` / `handlers` / `formatters` / `root` in stdlib `dictConfig` is organized into 2-layer structure of `config_dict={'global': {...}, 'dsafelogger:mod': {...}}`.
#### 3.7.2 Preserving existing call sites
Beginning of `examples/03_migration_from_stdlib.md`:
> Your existing `logger.info()` calls don't change. Your third-party libraries keep logging normally. Only the setup code changes — typically from 10-20 lines to 1-3 lines.
> (`examples/03_migration_from_stdlib.md`)
This is consistent with design document §1 (Drop-in Replacement). By calling `logging.setLoggerClass()` inside `ConfigureLogger()`, existing code that directly calls `logging.getLogger(__name__)` and third parties such as SQLAlchemy / Django can use the configuration flow of this library without changing the code.
#### 3.7.3 Observations on migration costs
Specific comparisons shown within `examples/03_migration_from_stdlib.md`:
- `basicConfig` migration: **11 → 4 lines** (approximately 64% reduction)
- `TimedRotatingFileHandler` migration: **16 → 7 lines** (approximately 56% reduction)
- `dictConfig` migration: 4 layers → 2 layers (`global` + `dsafelogger:module_name`)
This reduction is not a syntactic shortening, but rather a design consequence where manual wiring of handler / formatter / setLevel is consolidated into parameters of `ConfigureLogger()`.
---

### 3.8 Multiprocess usage
#### 3.8.1 Three worker_models
`examples/12_multiprocess_logging.md` and design document §11.11:
| Pattern | Corresponding `worker_model` | Recommended use |
|---|---|---|
| **Pattern A: `multiprocessing.Process`** | `'process'` (default) | If you want to specify the lifecycle. The behavior is easiest to understand on Windows |
| **Pattern B: `multiprocessing.Pool`** | `'pool'` | Existing code is Pool based |
| **Pattern C: `concurrent.futures.ProcessPoolExecutor`** | `'executor'` | Future base operation |
`ThreadPoolExecutor` is not applicable (thread parallelism is the responsibility of the single-process version).
#### 3.8.2 Typical code for Pattern A
`examples/12_multiprocess_logging.md` Section 5:
```python
import multiprocessing
from dsafelogger import mp


def worker(log_ctx, worker_id: int) -> None:
    mp.AttachCurrentProcess(log_ctx)
    try:
        logger = mp.GetLogger("jobs.worker")
        with logger.contextualize(worker=worker_id):
            logger.info("worker started")
            # ... work ...
            logger.info("worker finished")
    finally:
        mp.DetachCurrentProcess()


def main() -> None:
    proc_ctx = multiprocessing.get_context("spawn")

    log_ctx = mp.ConfigureLogger(
        log_path="./logs",
        pg_name="MPDemo",
        routing_mode="daily",
        structured=True,
        mp_context=proc_ctx,
    )

    processes = [
        proc_ctx.Process(target=worker, args=(log_ctx, i))
        for i in range(4)
    ]
    # ...
```

#### 3.8.3 attach/detach lifecycle accountability
`examples/12_multiprocess_logging.md` Section 3 clearly states what Writer does and does not guarantee.
> The Writer does not guarantee:
> - That every record survives a hard process termination, an OS crash, or power loss.
> - That records lost before the runtime accepts them ... are recovered.
> - That `UnexplainedLost` is always zero. The whole point of that counter is that some abnormal scenarios cannot be classified more precisely; the value is making them visible rather than silent.
> - That records are never dropped under backpressure. ... but they are counted as `KnownDropped`, not silent loss.
> (`examples/12_multiprocess_logging.md` Section 3)
This is consistent with the "What Not To Claim" section of the README (BENCHMARK.md) and the design document §1.2.5 (Be honest about multiprocess behavior). **The document side also maintains a stance of clearly stating the scope of warranty**.
#### 3.8.4 Advance guidance for Windows spawn rules
Design document §11.12 and `examples/12_multiprocess_logging.md`:
- `mp_context=None` is left to Python's default context (library does not make its own fallback based on OS determination)
- In spawn worker bootstrap, `register_level()` at the top level of the module may be re-executed, and **re-registration of the same definition is allowed as an idempotent no-op** (Design document §10.3 spawn worker re-import rule)
- `examples/12_multiprocess_logging.md` presents `if __name__ == "__main__":` guard and `mp_context=multiprocessing.get_context("spawn")` manifestation as a guide for Windows
---

### 3.9 Coexistence with third-party libraries
#### 3.9.1 structlog coexistence (`examples/16_structlog_coexistence.md`)
Two patterns are defined:
| Pattern | Design concept | Application |
|---|---|---|
| **Pattern A: Dual Stream** | **Responsibility separation** of JSON in structlog and human text in D-SafeLogger | I want to stream native JSON to the log aggregator (Datadog/Elastic) while also leaving human-readable text on disk |
| **Pattern B: Unified Output** | Pipeline that assembles event with structlog → **unifies routing/formatting/rotation** with D-SafeLogger | Using structlog's `bind()` API, entrusts the output route to D-SafeLogger |
#### 3.9.2 OpenTelemetry trace correlation (`examples/15_opentelemetry_logging.md`)
D-SafeLogger itself does not depend on OTel SDK (Vendor-Agnostic, design document §2). Integration pattern shown by `examples/15_opentelemetry_logging.md`:
- Inject ID of current span into context at `contextualize(trace_id=..., span_id=...)`
- Output is as structured JSON (`structured=True`) with `trace_id` / `span_id` appearing in top level fields
- Solve trace correlation on OTel collector / log shipper side
This is consistent with the README "Compatibility / Non-goals" clause (D-SafeLogger is not a log shipper / metrics pipeline / distributed tracing backend).
#### 3.9.3 stdlib logging co-participation with third parties
Design document §1 and README "Why D-SafeLogger?":
- `logging.setLoggerClass()` allows libraries using `logging.getLogger()` such as SQLAlchemy / Django / requests / boto3 to use the configuration flow of this library without modification.
- `examples/03_migration_from_stdlib.md` clearly states "Your third-party libraries keep logging normally"
---

### 3.10 Documentation structure
#### 3.10.1 Five axes of public documentation
From `README.md`, public design documents, and operational guides, this project's public documents are organized into the following five axes.
| Axis | Document | Role |
|---|---|---|
| Entrance | `README.md` / `README_ja.md` | overview + feature comparison + tutorial pointer |
| Learning | `examples/01_*.md`~`examples/17_*.md` (17 files) | tutorial / scenario guide |
| Design | `docs/design/*v23k*.md` (3 files) | Basic design, detailed design, test design |
| API | `docs/api/dsafelogger*.md` | Automatically generated API reference |
| Operation | `TESTING.md` / `BENCHMARK.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | Verification/Performance/Contribution/History |
#### 3.10.2 Automatic generation of docs/api/
Public documentation maintenance verifies generated outputs with the following commands:
```bash
# API docs check
uv run python scripts/generate_api_docs.py --check

# public design docs readiness check
uv run python scripts/check_design_docs_sync.py
```

- After changing public API / docstring, regenerate `docs/api/` with `scripts/generate_api_docs.py` and verify with `--check`
- Public design document is `scripts/check_design_docs_sync.py` and internal synchronization is verified with `docs/design/`
#### 3.10.3 Multilingual support
- README is available in two languages: English (`README.md`) and Japanese (`README_ja.md`)
- examples / docs/design / docs/api / TESTING / BENCHMARK / CONTRIBUTING / CHANGELOG only in English
#### 3.10.4 BENCHMARK.md Operational Boundary
The `BENCHMARK.md` Maintenance Model section explicitly separates benchmark runners from public analysis.
> `BENCHMARK.md` is a public analysis of manual editing. Do not regenerate from benchmark runner.
> (`BENCHMARK.md`)
- `benchmarks/results/<session>/` is complete facts per run
- `benchmarks/summary/manifest.json` is a fixed table of public/representative session
- `benchmarks/summary/*.md` is generated from manifest
- `BENCHMARK.md` is manual editing interpretation
This is designed to avoid "the accident where the last benchmark executed is automatically promoted to the public representative result" (section `BENCHMARK.md` Maintenance Model).
---

### 3.11 Zero-dependency consistency with design document §5.6
INI parser implementation policy defined by design document §5.6:
> Instead of using external libraries (D-Settings, etc.), include a dedicated minimal INI loader using the standard library `configparser.ConfigParser(interpolation=None)` inside D-SafeLogger.
>
> Design rationale: A clear trade-off in favor of "full portability (zero external dependencies)" as the underlying library over the DRY principle (code deduplication). The logger is the foundation at the bottom of all projects, and other D ecosystem libraries (such as D-Settings) may depend on D-SafeLogger. To avoid circular dependencies, the logger itself must not depend on anything external.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §5.6)
From a usability perspective, it is recorded as an observed fact that both ``INI settings can be used'' and ``zero external dependencies'' hold true at the same time.
---

### 3.12 Design characteristics for usability
#### 3.12.1 “Scale to production without changing the first 3 lines”
All 26 arguments of `ConfigureLogger()` have default values, and minimum activation is established with two of `log_path` / `pg_name`. A structure that allows you to achieve audit and compliance compliance by simply adding `routing_mode='daily'` / `structured=True` / `enable_hash=True` / `manifest_path=...` to the parameters of the same function. **Minimum startup and production operations are expressed in the same API parameter space**.
#### 3.12.2 “Assign a layer to each subject of change”
The three-tier pipeline separates "who makes the changes" by layer: developers with arguments, DevOps with INI, and operators with environment variables. This is a design approach that balances ``traceability of configuration changes'' and ``runtime overwriting without redeployment.''
#### 3.12.3 "The cost of migration is observable by the number of configured lines"
`examples/03_migration_from_stdlib.md` presents a concrete example of migrating from stdlib without changing call sites. The reduction in the number of lines of setup code (`basicConfig` 11 → 4 lines, `TimedRotatingFileHandler` 16 → 7 lines) is a result of the design in which the manual wiring of handler / formatter / setLevel is consolidated into the `ConfigureLogger()` parameter, and is not a syntactic shortening.
#### 3.12.4 "Relationship with third-party is not replacement but coexistence"
structlog coexistence 2 pattern, OpenTelemetry trace correlation, stdlib logging 3rd party automatic co-joining. All of them have a unified design attitude of ``not excluding other frameworks'' and ``not stepping into the responsibilities of other frameworks.''
#### 3.12.5 "Complete the operational weaknesses of Append-Only with CLI"
The weakness of Append-Only routing that prevents `tail -f app.log` from being established is compensated for by `dsafelogger tail -f`'s transparent file switching tracking. **Attitude to evaluate the theoretical merits and operational usability of a feature separately and to include both in the main unit.**
#### 3.12.6 “Clarify the boundaries of failure in the document”
The "Writer does not guarantee" list in `examples/12_multiprocess_logging.md` Section 3 and the "What Not To Claim" list in `BENCHMARK.md` are an expression of the attitude of actively enumerating the range of non-guarantees in the document. A design decision that is ``used appropriately without being overly expected.''
---

### 3.13 Usability summary
The materials reviewed in this chapter can be summarized as follows.
1. **Minimum startup code is 3 lines**: `ConfigureLogger(log_path=..., pg_name=...)` + `GetLogger(__name__)` + `logger.info(...)`. This is made explicit in both the README "Quick Start" section and `examples/01_quick_start.md`.
2. **There are two functions at the entrance to the public API**: Typical usage is completed with `ConfigureLogger()` and `GetLogger()`. The auxiliary API (`contextualize` / `register_level` / `ReopenLogFiles`) is optional and "doesn't exist if you don't use it" model.
3. **All 26 arguments have default values**: Design document §10.1. Minimal startup and production audit operations are expressed in the same API parameter space.
4. **stdlib migration is call-site invariant**: All three `examples/03_migration_from_stdlib.md` patterns reduce the number of setup code lines by 50–60% and do not change the `logger.info()` call site.
5. **3-layer pipeline supports change subject**: Correspondence between argument (developer) / INI or dict (DevOps) / environment variable (operator) is clearly specified in `examples/02_configuration_guide.md`.
6. **CLI tools are included**: 3 commands: `dsafelogger init` / `ls` / `tail -f`. Positioned to structurally complement the operational weaknesses of the Append-Only model.
7. **examples 17 files organized into learning paths**: Grouped by 6 learning paths (getting started / stdlib and ecosystem integration / Windows and service operations / application patterns / audit and incident response / multiprocess) in the README. The maximum is 12_multiprocess (438 lines), reflecting the intended readership.
8. **multiprocess supports 3 worker_models (process / pool / executor) in a dedicated namespace (`dsafelogger.mp`)**: `examples/12_multiprocess_logging.md` covers 3 patterns of actual code, lifecycle, failure mode list, and shutdown summary interpretation in 438 lines.
9. **Third-party coexistence is documented on two axes**: structlog (two patterns of dual stream / unified output), OpenTelemetry (contextualize-based trace_id injection). stdlib logging 3rd parties (SQLAlchemy / Django, etc.) participate without modification by `logging.setLoggerClass()`.
10. **Actively enumerated scope of non-claims**: `examples/12_multiprocess_logging.md` Section 3 and the "What Not To Claim" clause of `BENCHMARK.md`. The meaning of `UnexplainedLost` (counter to prevent muting) has been clearly stated.
11. **Multilingual support is available in README only in two languages**: `README.md` English version and `README_ja.md` Japanese version. Examples / Design document / API reference / Operation guide is available in English only.
12. **API documentation is automatically generated + internally synchronized with check script**: `scripts/generate_api_docs.py --check` / `scripts/check_design_docs_sync.py` enables CI integration for consistency verification of docs/api/ and docs/design/ when changing API.
---

### 3.14 Summary of this chapter
The usability goals of D-SafeLogger v23k can be summarized in the following five points:
1. **Entrance is consolidated into 2 functions (`ConfigureLogger` / `GetLogger`), and auxiliary API is optional**: Start with a minimum of 3 lines, and scale up to audit and compliance by adding 26 arguments step by step.
2. **3-tier pipeline (environment variables > INI/dict > arguments) supports change agents (developers/DevOps/operators)**: `env_prefix` separates namespaces and structures runtime overrides without redeployment.
3. **stdlib `logging` migration is call site unchanged, setup reduced by 50–60%**: 3 patterns of `basicConfig` / `TimedRotatingFileHandler` / `dictConfig` are materialized in before/after. Third-party libraries such as SQLAlchemy / Django can participate without modification.
4. **17 examples organized as learning paths**: The largest example is multiprocess, which covers attach/detach lifecycle, failure mode, and shutdown summary. stdlib ecosystem, Windows service, incident response, container collector, structlog, and OpenTelemetry coexistence patterns are documented as separation-of-responsibilities examples.
5. **CLI tools are included in the main unit and are responsible for supplementing the operation of Append-Only models**: 3 commands: `init` / `ls` / `tail -f`. `tail -f` structurally compensates for the operational weaknesses of Append-Only by transparently following file switching.
These points are revisited in the next chapter, “4. Security,” as safety aspects such as zero-dep supply chain posture, the `diagnose` sanctuary, sens_kws masking, and SHA-256 integrity, and again in Chapter 5, “Detailed Analysis by Function,” as individual feature behavior.
---

> **Main references for this chapter**: `docs/design/D_SafeLogger_Specification_v23k_full.md` §4, §5, §8, §10, §11.4, §11.11, §11.12 / `examples/01_quick_start.md`, `02_configuration_guide.md`, `03_migration_from_stdlib.md`, `04_stdlib_ecosystem_coexistence.md`, `05_windows_service_and_scheduled_batch.md`, `06_web_api_logging.md`, `07_long_running_service.md`, `08_compliance_audit.md`, `09_debugging_production.md`, `10_incident_response_bundle.md`, `11_async_performance.md`, `12_multiprocess_logging.md`, `13_external_rotation_reopen.md`, `14_cli_operations.md`, `15_opentelemetry_logging.md`, `16_structlog_coexistence.md`, `17_container_collector_coexistence.md` / `README.md` / `README_ja.md`
> This document is intended to explain and evaluate the current v23k architecture, and does not include improvement proposals, issue management, or future roadmaps.
## Chapter 4 Security
> **Definition of "security" in this chapter**: Security dealt with in this chapter is not limited to encryption, authentication, and access control. Treated as operational safety, including supply chain, misconfiguration, exposure of confidential information, auditability, failure prevention during parallel execution, and suppression of availability degradation through logging mechanisms. This library itself is not an access control system or cryptographic infrastructure (README "Compatibility / Non-goals" section).
>
> Therefore, the six axes of Safe discussed in this chapter are not security functions in a narrow sense, but a broad design concept that includes operational safety, auditability, observability, and concurrent safety.
### 4.1 Six axes of Safe and the role of security
`README.md` The Overview section organizes the concept of "Safe" for this product along six axes (reposted).
| Axis | Positioning from a security perspective |
|---|---|
| **Startup safety** | Reject invalid settings and unwritable paths during setup → Structurally eliminate situations where "it appears to be working with broken settings" |
| **File safety** | Do not rename/truncate → Structurally avoids the problem of not being able to rename Windows active logs + Post-mortem verification possible with SHA-256 sidecar |
| **Record/context safety** | Eliminate dependence on snapshot → live `contextvars` during hand-off on the producer side. Apply `sens_kws` masking during diagnostic snapshots and Writer-side formatting |
| **Operational control** | Diagnostics, routing, and hashes can be overwritten with environment variables without rebuilding |
| **Concurrency/multiprocess safety** | Workers do not directly open shared log files, and the parent Writer owns the sink. Eliminate unlimited waiting for host process with bounded queue + explicit timeout |
| **Failure observability** | Classify delivery failures by `KnownRejected` / `KnownDropped` / `UnexplainedLost` → silent loss is not allowed structurally |
In this chapter, we will sequentially discuss (1) supply chain, (2) startup security, (3) confidential information masking, (4) integrity verification, (5) parallel/multiprocess safety, (6) failure visualization, and (7) blocking of logging-related abuse paths as elements that can be evaluated individually from a security perspective among these six axes.
---

### 4.2 Supply Chain Security (Zero Dependency)
#### 4.2.1 Zero runtime dependencies
`pyproject.toml` and design document §1 / §2:
> Zero Dependency: Consists only of standard libraries. Structurally eliminate external dependence and reduce supply chain risk to zero.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §2)
In §1 of the design document, this condition is specified as an "absolute condition."
> While making "complete compliance with the standard library" an absolute requirement, it achieves diagnostic capabilities that surpass third-party libraries (such as Loguru) and robustness that avoids fatal file locking problems in Windows environments with **zero external dependencies**.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §1)
This allows us to observe:
- Do not pull dependent packages during installation (complete with `pip install d-safelogger`)
- A structure that prevents this library from being attacked when a vulnerability in a dependent package is discovered.
- The risk of supply-chain attacks (unauthorized commits/hijacking of dependent packages) is reduced to attacks on the Python standard library itself.
#### 4.2.2 Vendor-Agnostic Principles (v20)
Design document §2:
> Do not include any vendor-specific imports (such as OpenTelemetry) or data references in the core module (under `src/dsafelogger/`). Vendor integration such as OTel is provided as custom Formatter insertion using `file_fmt` / `console_fmt`, context injection using `contextualize()`, and sample code under `examples/`.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §2)
significance:
- Since imports of opentelemetry-api / opentelemetry-sdk / other vendor SDKs do not exist in the core code, there is no path for these vulnerabilities to propagate to this library.
- Vendor integrations are separated as examples (sample code that users can optionally include) and are not included in the trust boundary of the library itself.
#### 4.2.3 Separation of development and bench dependencies
`pyproject.toml` and dependency groups:
- Runtime dependency: None
- `dev` dependency group: Testing tools such as pytest (not required during installation)
- `benchmark` dependency group: Benchmark tool (not required during installation)
- `optional_integration` test marker is for checking the integration operation of OpenTelemetry / structlog etc. (It is executed in CI, but it is not drawn during end user installation)
#### 4.2.4 License
`LICENSE`: Apache License 2.0. Contributes to legal predictability during OSS integration.
#### 4.2.5 Minimum distribution
`MANIFEST.in` and `pyproject.toml`:
- import name `dsafelogger` (no hyphen) / distribution name `d-safelogger` (PyPI normalization)
- Includes `py.typed` (specifies type information)
- The wheel contains runtime package files only. The sdist includes docs / examples / tests / benchmark summaries / selected benchmark summaries for public validation and reproducibility. Private planning materials and temporary working files are excluded.
---

### 4.3 Startup safety / fail-fast behavior
#### 4.3.1 Design attitude
Design documents §9.1 and §2:
> Fail-Fast initialization verification & pre-storage verification: Immediately tests whether the output destination directory can be created and permissions at startup (when running `ConfigureLogger`), and detects permission errors and disk fullness at an early stage. Even if the value in the INI file is invalid, an exception will be thrown immediately without silent fallback.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §2)
**A design approach that structurally eliminates the situation where the settings appear to move even though they are not reflected.**
#### 4.3.2 Items verified at startup
| Verification items | Behavior in the event of failure | Specification basis |
|---|---|---|
| `log_path` directory permissions | Fail-Fast with `PermissionError` / `OSError` | §9.1 |
| `log_path` Directory disk space (test file creation) | Fail-Fast with exception | §9.1 |
| Permissions for `path` by module | Fail-Fast | §9.1 |
| `manifest_path` Directory permissions (when specified) | Fail-Fast with `PermissionError` | §7.6.6 / §9.1 |
| INI type conversion not possible (`is_async` / `max_bytes`, etc.) | Fail-Fast with `ValueError` | §5.3 |
| `[dsafelogger:]` in INI (module name empty) | Fail-Fast with `ValueError` | §5.4 |
| Simultaneous specification of `config_file` and `config_dict` | Fail-Fast with `ValueError` | §5.7.3 |
| `routing_mode='size'` and `max_bytes <= 0` | `ValueError` and Fail-Fast | §7.6.6 |
| `routing_mode='count'` and `max_lines <= 0` | `ValueError` and Fail-Fast | §7.6.6 |
| Custom level name conflicts with built-in | Rejected with `ValueError` | §9.9.3 |
| Call `register_level()` after `ConfigureLogger()` | `RuntimeError` | §9.9.2 |
| Non-string value for `config_dict` (directly specified int/bool) | Fail-Fast with `TypeError` | §5.7.1 |
| Environment variable `{prefix}_IPC_LOG_TIMEOUT` cannot be interpreted as float (v23h) | `ValueError` | §11.16.1 |
| Environment variables `{prefix}_IPC_LOG_QUEUE_MAXSIZE` / `IPC_CLIENT_QUEUE_MAXSIZE` cannot be interpreted as int | `ValueError` | §11.16.1 |
| Environment variable `{prefix}_WRITER_FLUSH_BATCH` cannot be interpreted as int (v23h) | `ValueError` | §11.27 |
| `{prefix}_LEVEL` separated by commas (module-specific syntax) | `ValueError` (message prompting migration to `MODULES`) | §4.2 |
#### 4.3.3 Principle of not allowing silent fallback
Design document §5.3:
> For type conversion of string values ​​read from the INI file (`is_async` to bool, `max_bytes` to int, etc.) or format violations, immediately throw an exception and stop startup (Fail-Fast) instead of easily falling back to the default value. Silent fallback to default values ​​creates the most dangerous failure pattern: ``settings appear to be working even though they are not reflected.''
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §5.3)
This is a design decision that ensures that configuration errors will surface at startup, and eliminates "hidden configuration inconsistencies" that are only discovered during the operational phase after deployment.
#### 4.3.4 fail-fast enhancements in v23h
v23h revision of design document §11.16.1 / §11.27:
- If the value of the environment variable `{prefix}_IPC_LOG_TIMEOUT` cannot be interpreted as float: **fail-fast conversion from warning + ignore to **`ValueError`**
- Same as above `IPC_LOG_QUEUE_MAXSIZE` / `IPC_CLIENT_QUEUE_MAXSIZE`: Same as above
- Same as above `WRITER_FLUSH_BATCH`: Same as above
This is an enhancement in the direction of ``not silently ignoring errors in the interpretation of environment variable values, but making them explicit at startup.''
---

### 4.4 Sensitive information masking
#### 4.4.1 `diagnose` Sanctuary
Design document §4.4 and `examples/09_debugging_production.md`:
The `diagnose` function (automatic expansion of `f_locals` when an exception occurs) is protected by the following triple guard.
| Setting route | Possibility |
|---|---|
| **Environment variable `{prefix}_DIAGNOSE=1`** | **Only activation path** |
| `diagnose` key in INI / config_dict | **Cannot be set** (Ignored even if it is described. No warning or error is issued, just treated as an invalid key) |
| Argument of `ConfigureLogger()` | **Does not exist as an argument in the first place** |
Design document §4.4 clearly states the reason for this design decision as follows.
> Since there is no way to write `diagnose=True` in the source code, the accident pattern of "writing it in the code and forgetting to put it back" **doesn't work in normal usage**.
>
> INI files are often included in version control (git), and the risk of `diagnose = true` being committed and entering the production environment is the same as arguments in the code. Therefore, the route from the INI file is also blocked.
>
> If it is necessary to enable it in the production environment, do it explicitly as an infrastructure layer operation by setting environment variables.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §4.4)
`examples/09_debugging_production.md` describes the pattern as “The Sanctuary Pattern”:
> Diagnostic mode is deliberately hard to enable. This is by design — it's a safety mechanism:
> - A developer can't accidentally enable it in code — there is no Python parameter for it.
> - An INI config can't turn it on — the setting is not recognized in config files.
> - **ONLY an operator setting `D_LOG_DIAGNOSE=1` can activate it.**
>
> This prevents the single most common source of credential leaks: "debug mode left on in production." The operator who sets the environment variable knows exactly what they're doing, and they remove it as soon as the debugging session is over.
> (`examples/09_debugging_production.md`)
#### 4.4.2 `"1"` is the only valid value
Design document §4.4: Only `"1"` is valid as the environment variable value. `"true"` / `"yes"` / `"True"` etc. are treated as invalid values.
> By limiting it to only `"1"`, it prevents unintended activation due to differences in truth value notation depending on the operating environment.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §4.4)
This decision was made to eliminate the risk of increasing omissions and contamination by allowing multiple truth value expressions.
#### 4.4.3 Sensitive keyword masking with sens_kws
Design document §9.4:
When expanding `f_locals`, values ​​that include sensitive words in variable names are replaced with `*** MASKED ***`.
**Built-in keywords (12 words)** (design document §9.4 official definition):
```text
password, passwd, pass, secret, token, key, api_key, apikey,
auth, credential, private, cert
```

Example output for `examples/09_debugging_production.md`:
```text
--- Local Variables (payment.py:5) ---
  user_id = 42
  api_key = *** MASKED ***
  amount = 15000.0
  token = *** MASKED ***
```

#### 4.4.4 Matching rules
Design document §9.4:
- Determine by **partial match** (case does not matter) for the variable name
- Example: `password` matches any of `user_password` / `PASSWORD_HASH` / `my_password_field`
#### 4.4.5 Customization
Design documents §9.4 and §10.1:
| Setting method | Operation |
|---|---|
| `sens_kws=['ssn', 'credit_card']` (Additional) | Match the total of 12 built-in words + additional words |
| `sens_kws=['ssn'], sens_kws_replace=True` (replacement) | Discard the built-in 12 words and match only the specified word |
`sens_kws` / `sens_kws_replace` Both **Settings from environment variables are intentionally not supported** (§3.4 / §4 / §5.3). The design document explains this as "sanctuary treatment similar to `diagnose`" (§3.4 notes).
> v20 Clarification: `sens_kws` / `sens_kws_replace` intentionally does not support settings from environment variables. This is treated as a "sanctuary" similar to `diagnose`, and is a design decision to prevent unintended changes to sensitive keywords.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §3.4)
#### 4.4.6 Areas where masking is not applied
`examples/09_debugging_production.md` Section "What Is NOT Masked":
- Message body directly passed to `logger.info(...)` / `logger.error(...)` etc.
- `extra=...` / `contextualize()` / Fields added in structured JSON output
- Normal logging when `D_LOG_DIAGNOSE` is off
> If you place a secret directly in the message body or extra fields, it is logged **as-is**. Keep secrets in variables whose names match your masking rules, or redact them before logging.
> (`examples/09_debugging_production.md`)
This is a warning in the document to clearly indicate the boundary that ``masking only works on the `f_locals` route in `diagnose` mode'' and to prevent users from misperceiving the boundary and passing on secrets in the message body.
#### 4.4.7 Suppressing huge repr and handling when repr fails
Design document §9.4:
- `repr()` for individual local variables are **truncated** to prevent large objects or excessively redundant data from polluting the log.
- Even if `repr()` itself fails, the entire diagnostic log is not destroyed, and the failure is output as a placeholder.
This functions as an indirect defense against ``attacker-induced `__repr__` exceptions'' and ``log size attacks using large objects.''
#### 4.4.8 cross-thread safety
Design document §9.4:
> In a free-threaded build, a `f_locals` live reference to frame of another running thread is unsafe. Therefore, when a hand-off across queues occurs, the traceback and `f_locals` are converted to a **safe masked, repr-converted snapshot** on the producer thread side, and no live reference is made on the consumer thread side.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §9.4)
Although this is a matter of correctness rather than security, it also helps reduce the risk of data leakage by eliminating accidents in which the internal state of other threads is unintentionally referenced in a free-threaded environment.
---

### 4.5 File integrity verification
#### 4.5.1 Sidecar file (`.sha256`)
Design document §7.6.2 and `examples/08_compliance_audit.md`:
- When switching files by routing, generate `{original_file_name}.sha256` for files that have been written.
- `sha256sum -c` compatible format (1 line):
```text
a1b2c3d4e5f6789... (64-character hex SHA-256) MyApp_20260328.log
```

- The hash and file name are separated by **two half-width spaces** (compatible with `sha256sum`)
- File name is **relative path (file name only)** → Verification will not be broken even if you move the log set to another location
- Verification: `sha256sum -c MyApp_20260328.log.sha256`
#### 4.5.2 Manifest file
Design document §7.6.3 and `examples/08_compliance_audit.md`:
```text
[2026-04-01T23:59:59.999] a1b2c3d4... AuditService_20260401.log
[2026-04-02T23:59:59.999] e5f6a7b8... AuditService_20260402.log
```

- Append format. Do not overwrite.
- The timestamp is the date and time the hash was finalized (ISO8601 with milliseconds)
- Serialization: Additions to the same `manifest_path` are always done by 1 thread at a time
#### 4.5.3 Audit value of manifest
Design document §7.6.3 specifies three operational values:
> - **File loss detection**: Files that are listed in the manifest but do not exist on the disk can be determined to have been "deleted." Sidecar files alone cannot detect when files and sidecars are deleted together.
> - **Improved tampering resistance**: By storing the manifest in a separate directory and with different permissions from the log itself, even if the log file is manipulated by an attacker, it can be detected by the inconsistency with the manifest.
> - **Overview of history**: You can instantly check whether all the logs for the past N days are complete by checking the number of lines in one manifest file.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.6.3)
#### 4.5.4 Threat model (clarification of warranty scope)
`examples/08_compliance_audit.md` Section "Threat Model and Limitations":
> The sidecar + manifest flow proves that a **completed** log file still matches the recorded SHA-256 digest. It does **not** make local logs tamper-proof by itself.
>
> - If an attacker can rewrite the log file **and** its `.sha256` / `manifest.txt` with the same OS permissions, they can regenerate matching hashes.
> - The **current active log file** is not hashed until rotation/finalization happens.
> - The manifest records operational metadata (when files were finalized), so it needs normal access control just like the logs themselves.
>
> For stronger guarantees, ship sidecars/manifests to an **external append-only or immutable store** (for example S3 Object Lock, WORM storage, or a separate audit system). If you need cryptographic non-repudiation, layer a signing scheme on top.
> (`examples/08_compliance_audit.md`)
This is a typical example of the attitude of actively clarifying the ``scope of guarantee'' and ``scope of non-guarantee'' in the document. HMAC signatures and cryptographic non-repudiation are also explicitly declared out of scope in Design §7.6.7.
#### 4.5.5 Atomicity of sidecar writes
Design document §7.6.4:
> Atomic nature of sidecar writing: `.sha256` In order to prevent the sidecar from showing the partially written state to the outside, we recommend writing to a temporary file and then atomically replacing it with the main file using `os.replace()`.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.6.4)
This prevents the verification tool from ``referring to a sidecar that was written midway and causing verification to fail''.
#### 4.5.6 Fail-fast in cyclic mode
Design document §7.6.5:
In `cyclic_weekday` / `cyclic_month` / `size`/`count` with `max_count` specified mode, file names are reused. Combining this with `enable_hash=True` cannot preserve hash semantics, so `ConfigureLogger()` fails fast with `ValueError`. This structurally prevents erroneous audit records.
#### 4.5.7 Out of scope (explicit)
Design document §7.6.7:
- **HMAC Signature**: outside the scope of this library as it introduces extraneous responsibilities of key management. The plan is to delegate uses that require signatures to external tools that take the hash of this library as input.
- **CLI verification command**: Since the `sha256sum -c` compatible format allows immediate verification with OS standard commands, no special commands are added.
This is a design approach that ``does not have to handle all security functions in-house, but separates the responsibility between the OS and external tools.''
---

### 4.6 Concurrency and multiprocess safety
#### 4.6.1 Workers do not open shared log files directly
Design document §11.1 / §11.6 and `examples/12_multiprocess_logging.md`:
> Workers **never** open the shared log files directly. They submit `LogEvent` messages over an IPC queue.
> (`examples/12_multiprocess_logging.md` Section 4)
This achieves the following:
- Structurally eliminates line mixing due to multiple processes writing independently to the same file**
- **File handle monopoly** is consolidated in the parent side Writer, eliminating the possibility of Windows file lock contention.
- **routing/hash/manifest responsibilities are centralized in Writer**, so state inconsistencies (multiple `.sha256` generation/multiple manifest updates) do not occur between multiple processes.
#### 4.6.2 bounded queue + explicit timeout
Design document §11.16:
| Settings | Default | Absolute Upper Limit (Line of Defense) |
|---|---|---|
| `ipc_log_queue_maxsize` | 10000 | warning with `>100000` |
| `ipc_log_timeout` | 0.5 seconds | `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` Force to seconds clip |
| ACK timeout | 5.0 seconds (`CONTROL_PLANE_ACK_TIMEOUT_SEC`) | Do not add timeout argument to public API |
| stop wait timeout | 10.0 seconds (`WRITER_STOP_WAIT_TIMEOUT_SEC`) | Do not add timeout argument to public API |
These four internal constants are a structural guarantee that ``even if the user sets arbitrarily large values, the length will not exceed the length at which the host process is irreversibly hardened on the library side.''
Design document §11.16.1 Line of Defense:
> Design decision: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` is an absolute upper limit to prevent the normal log producer path from being blocked for too long. We use 3.0 seconds as an upper bound that is long enough to wait for the queue to recover naturally from temporary saturation, but not so long that it irreversibly freezes the GUI thread or request handler thread.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.16.1)
#### 4.6.3 Prohibition of unbounded queue / permanent block
Design document §12.4:
| Prohibitions | Reasons |
|---|---|
| unbounded log queue | OOM risk increases indefinitely when Writer stops or output is clogged |
| indefinite producer block | Involve GUI / Web handler / worker loop with log output |
| silent drop | Operator cannot detect log loss |
| Confusing overflow with `unexpected_loss` | Design bug and misjudging overload policy |
This is a restriction to prevent the logging mechanism itself from becoming the starting point for DoS. The addition of strict lossless mode / unbounded queue / OOM permissive mode is clearly specified in the design document as a matter to be determined by the user (§12.4).
#### 4.6.4 Bootstrap payload picklability constraints
Design document §11.7:
- `ctx` only contains picklable spec (`kind + constructor args`)
- Raw instances of `Strategy` / `Formatter` are not included.
- Rebuild `Strategy` / `Formatter` from the raw config dict / formatter spec received on the Writer side
This structurally reduces the scope for **pickle payloads that involve arbitrary code execution** (RCE exploiting `__reduce__`) in payloads that cross process boundaries. Due to the constraints of the allow-list expression, payloads that fall outside the standard spec construction path will not be accepted by the receiver.
#### 4.6.5 registry hash matching (SHA-256)
Design document §11.7:
- At Writer bootstrap ready ACK: Check the registry hash sent by the client and the initial registry on the Writer side.
- When running `AttachCurrentProcess(ctx)`: Check the registry of the current process and the hash in `ctx`
- Any discrepancy is Fail-Fast by `RuntimeError`
- hash algorithm is SHA-256
This is a mechanism to detect ``incorrect attaching to different Writer sessions'' and ``semantic inconsistency between clients/Writers with different levels registries'' at the startup boundary.
#### 4.6.6 Control plane error normalization
Design document §11.9:
> Pipe send/recv failure is not leaked as raw `BrokenPipeError` / `EOFError`, but is normalized to `RuntimeError` system as a control plane failure.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.9)
This prevents accidents where exceptions originating from the internal implementation (such as `BrokenPipeError`) leak outside the API boundary and the user code writes an exception handler that depends on the internal implementation. By fixing the exception type to the contract, compatibility is maintained when changing the internal implementation.
#### 4.6.7 Prohibiting `mp.ConfigureLogger()` for the second time in the same process
Design document §10.5 / §11.23:
> The second `dsafelogger.mp.ConfigureLogger()` in the same process is `RuntimeError`
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §10.5)
This structurally eliminates the accident of ``two Writer runtimes / two types of `ctx` coexisting in the same process.''
#### 4.6.8 Child-only client identity after fork inheritance
Design document §11.13.3 / §11.21.1:
> In POSIX `fork`, the attach state of the parent process can be inherited. v22i treats this as a normal case. However, since `fork` only copies the main thread, the process-local pump thread etc. used in `is_async=True` must be regenerated on the child process side.
>
> A child must not reuse its parent's client identity. After confirming that it is the same Writer session, establish a process-local client identity exclusively for child, register it in the Writer active client registry, and then restart logging.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.13.3)
This is a rule to prevent accidents in which ``child continues to use the parent's identity after forking, causing the consistency of the active client registry on the Writer side to collapse.''
#### 4.6.9 Prohibition of resurrection after Writer session ends
Design document §11.13.3:
> Boundary condition: The above fork inheritance child re-registration only holds true while the original Writer session is still alive. If the parent/Writer side has accepted `STOP`, is draining, or has terminated, the child process must not **automatically revive** the same session. In this case, the subsequent `emit()` will be handled through the normal Writer unavailable route (drop + stderr warning), and continued operation is not guaranteed.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.13.3)
This is a convention that prevents an unexpected resurrection in which the child is silently restarted after the Writer exits.
---

### 4.7 Failure Observability
#### 4.7.1 Prohibiting silent drop / silent hang / silent fallback
Design document §12.1 (Writer invariants):
> fail-safe: avoid silent loss, silent hang, silent fallback
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §12.1)
This is used as a Writer invariant throughout the v23 series. The principle of no silent failure applies throughout the library.
#### 4.7.2 Delivery status classification
The six terminal states specified in Design Document §12.3 (restated and detailed in §2.8.14):
| Terminology | Meaning from a security perspective |
|---|---|
| `rejected` | Delivery refused due to timeout / closed / writer unavailable. Explicit record |
| `dropped` | Explicitly discarded to protect the main unit due to bounded queue overflow, etc. Reflected in counter / warning / summary |
| `writer_reject` | Route / sink / policy rejection after reaching Writer (6 breakdowns: route / reconstruct / close_marker / sink / policy / format) |
| `partial_delivered` | Only part of the required sink set was reached. Don't make it silent |
| `unexpected_loss` | accepted was created but disappeared for no reason → **Treat it as a design or implementation bug** |
| `overload_shed` | qualifier for explicit destruction based on bounded queue / timeout policy |
By treating only `unexpected_loss` as a bug, the remaining five types can be treated as explainable facts derived from policy.
#### 4.7.3 Rate-limited output of stderr warning
Design document §12.3 / §11.22:
- All `writer_reject` breakdowns are assigned a dedicated counter and stderr warning (rate-limited)
- stderr warning on first drop occurrence and subsequent summary timing (§11.16.2)
Rate limiting reduces the risk that stderr itself becomes a source of log pollution due to a series of abnormal events.
#### 4.7.4 Writer exit code
Design document §11.22.4:
> Normal termination is exit code 0. Abnormal termination is non-zero. Parent/caller process issues stderr warning if Writer exit code is non-zero.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.22.4)
This makes it possible for the monitoring system (such as systemd) to detect abnormal termination of Writer.
#### 4.7.5 Bounded shutdown contract (v23h)
Design document §12.4.1:
```text
bounded wait (≤ timeout) → visible warning (expose incomplete drain) → process exits
```

Prevents the host process from blocking permanently even if an unknown hang is mixed in the drain route. Combine with daemon=True to make "process exits" fail-safe.
From a security perspective, this corresponds to ``the logging mechanism does not involve the host process and stop it even under a DoS situation.''
#### 4.7.6 Registry timeout during worker crash
Design document §11.21.2:
> If the worker process terminates without sending `DETACH`, there may be some residue in the Writer's active client registry. An internal timeout is provided to wait for the number of active clients to be 0 during shutdown. When the timeout is reached, a stderr warning is issued and the process transitions to a forced stop. Avoid silent hangs.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.21.2)
This is a rule to abort an incident where "shutdown cannot proceed forever due to a worker crash" with a timeout. Convert silent hang to forced stop + warning.
---

### 4.8 Blocking logging-related abuse paths
#### 4.8.1 Sanitizing `pg_name`
Design document §7.1:
> Sanitization rules for `pg_name`: `pg_name` has characters prohibited in OS file names (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`), replace them with `_`. This is not a Fail-Fast feature, but a specification for generating safe file names while avoiding startup inhibition as a log base.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.1)
As a result, path traversal via `pg_name` and OS-specific special file name injection do not occur structurally.
#### 4.8.2 Stricter file name filtering
Design document §7.5:
> When identifying the target file, perform strict filtering to only target file name prefixes that exactly match `pg_name` in order to prevent false matches due to prefix matches of `pg_name` (e.g., a problem where the pattern of `pg_name='App'` also matches `AppServer_*.log`).
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.5)
This is a rule that eliminates accidents where ``generation management accidentally deletes files of other apps when logs of other apps exist in the same directory.''
#### 4.8.3 Self-healability and lock contention
Design document §7.5 / §2:
> Fire-and-Forget Asynchronous purge and self-healing: Generation management (deleting and archiving old files) is performed using a separate disposable thread only when switching output destinations. Even if purge fails due to Windows file lock, etc., it will automatically repair itself (retry) at the next switching timing.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §2)
From a security perspective, this means that this library does not forcibly take the lock or forcefully delete the log file while another process (monitoring tool, etc.) has the log file open.
#### 4.8.4 Log file name is a "fixed name selected by the application"
Design document §7.1: The output file name is based on `{log_path}/{pg_name}` and is given a fixed pattern suffix depending on the routing mode. **There is no path for user input (such as request parameters) to be injected directly into the file name**.
#### 4.8.5 INI/environment variable values ​​do not lead to arbitrary code execution
Design document §5.3 / §4: All INI and environment variable values ​​are read as strings, and only specified type conversions (int / bool / str) are applied. There is no arbitrary object restoration route such as eval / exec route or YAML `!!python/object`.
#### 4.8.6 Vendor-Agnostic Core Consequences
Design document §2 / §11.7: Since there are no vendor-specific imports in the core module and the bootstrap payload is limited to the picklable spec of `kind + constructor args`, the path for an attacker to inject malicious Formatter/Strategy instances (arbitrary object restoration via the pickle payload) is structurally reduced.
---

### 4.9 Boundaries with third-party libraries
#### 4.9.1 Minimize the impact of stdlib `logging` on global state
Design document §9.8:
> Do not use global level name override with `logging.addLevelName()`.
>
> Design Rationale: `addLevelName()` changes the process-global state of the `logging` module, thus affecting all loggers (including 3rd party libraries) within the same process. The abbreviation conversion of D-SafeLogger should be completed within the responsibility of the own Formatter, and by avoiding global side effects, maintain test independence and coexistence with third-party libraries.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §9.8)
From a security perspective, the side effect of ``the existence of a library itself changing the behavior of other libraries within the same process'' can be suppressed.
#### 4.9.2 Non-destructive handling of `LogRecord`
Design document §9.7 (reprinted, detailed in §2.4.4):
The same instance of `logging.LogRecord` is shared among all handlers. This library does not modify `record.levelname` or `record.msg` and solves the problem using a display proxy.
From a security perspective, this prevents accidents in which "a subsequent handler (third-party `SMTPHandler`, etc.) receives `LogRecord` modified by this library and behaves differently than intended."
#### 4.9.3 Starting an empty Context in internal thread
Design document §9.5:
> The internal thread that D-SafeLogger itself creates always starts with an empty `Context`. This prevents context from leaking to internal threads.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §9.5)
This is a rule to eliminate accidents in which ``the user's request context (user_id, etc.) is leaked to the internal thread of this library, and subsequent logs are mixed with context that the user did not intend.''
---

### 4.10 Design characteristics for security
#### 4.10.1 “Accident patterns should not be established structurally”
Limit `diagnose` environment variables (§4.4.1), Sanctuate `sens_kws` (§4.4.5), Sanitize `pg_name` (§4.8.1), Stricter file name filtering (§4.8.2), Second time in the same process mp.ConfigureLogger() Prohibited (§4.6.7). What they all have in common is a design attitude that ``no false paths from code/settings/inputs exist in the first place.''
#### 4.10.2 “Actively clarify the warranty scope”
Threat Model section of `examples/08_compliance_audit.md`, HMAC out-of-scope declaration in design document §7.6.7, "Writer does not guarantee" list in `examples/12_multiprocess_logging.md` Section 3, "What Not To Claim" in `BENCHMARK.md`. These are manifestations of the attitude of declaring in advance what cannot or will not be done in the document. Prevent "misuse due to excessive expectations".
#### 4.10.3 "Fix the absolute defense line with internal constants"
`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`. Fix the upper limit on the length of the irreversible hardening of the host process using an internal constant that cannot be overwritten by the user. A design decision that structurally guarantees that it will not become a starting point for DoS.
#### 4.10.4 “Separate responsibilities between OS/external tools”
HMAC signatures are delegated to external tools (§7.6.7), sidecar verification uses `sha256sum -c` (§7.6 / §8), and external rotation coexists with logrotate (`examples/13_external_rotation_reopen.md`). **Attitude to utilize the mechanisms already provided by the OS/external tools rather than having to carry out all the security functions ourselves**.
#### 4.10.5 “Classifying abnormalities”
Silent loss is classified into 7 layers of `accepted / rejected / dropped / writer_reject / partial_delivered / unexpected_loss / overload_shed` (§12.3, §4.7.2). **Design attitude that does not uniformly treat "log disappeared" as a "failure", but structurally distinguishes whether it originates from a policy or a bug.** Only `unexpected_loss` is treated as a "bug" and the rest are treated as explainable facts.
#### 4.10.6 "Minimize side effects on global state"
Locally resolve within Formatter without using `addLevelName()` (§4.9.1), start internal thread with empty Context (§4.9.3), and do not modify `record.levelname` (§4.9.2). **Attitude that the library's existence is neutral with respect to other components within the same process**.
---

### 4.11 Summary of security aspects
The materials reviewed in this chapter can be summarized as follows.
1. **Zero runtime external dependencies are clearly stated as an ``absolute condition''**: Design document §1 declares ``achieved with zero external dependencies'' as an absolute condition, and the Vendor-Agnostic principle (§2) structurally excludes vendor imports from core modules. There are no third-party dependencies that an attacker could pass through in the supply chain.
2. **At least 16 items are verified at startup**: log_path / module-specific path / manifest_path permissions, INI type conversion, INI section rules, `config_file`/`config_dict` exclusive, routing_mode different threshold, custom level name collision, `register_level()` calling order, interpretability of each environment variable (fail-fast in v23h) verification) is verified at startup, and if invalid, startup is stopped with an exception.
3. **`diagnose` is protected by only environment variables, only `"1"`, and triple guard**: ``Inadvertent introduction into production'' is structurally eliminated by three layers: code path (no argument), configuration file path (ignored even if written in INI), and truth value representation fluctuation (`"true"`, etc. are invalid).
4. **`sens_kws` / `sens_kws_replace` are also blocked from setting from environment variables as a similar sanctuary**: This is clearly stated as a design decision to prevent unintentional changes to sensitive keywords (clarification in §3.4 v20).
5. **12 built-in keywords for masking**: `password` / `passwd` / `pass` / `secret` / `token` / `key` / `api_key` / `apikey` / `auth` / `credential` / `private` / `cert` (Design document §9.4). Match by partial match (case does not matter).
6. **The scope of masking is clearly specified in the document**: `examples/09_debugging_production.md` actively warns that only the `f_locals` route works, and `logger.info()` message body / `extra` / `contextualize` / normal logging is not covered.
7. **Integrity verification is `sha256sum -c` compatible + file name relative path**: Can be verified using OS standard commands. Designed so that validation does not break even if a set of logs is moved to another location. Sidecar is atomically written by `os.replace()`.
8. **Threat model boundaries for integrity verification are clearly documented**: HMAC signatures are explicitly out of scope (§7.6.7). The `examples/08_compliance_audit.md` Threat Model section clearly states that if an attacker can rewrite the file + sidecar + manifest with the same authority, tampering cannot be detected.
9. **The absolute line of defense is fixed with four internal constants**: `ipc_log_timeout` upper limit 3.0 seconds (`MAX_IPC_LOG_TIMEOUT_SECONDS`), ACK timeout 5.0 seconds, stop wait 10.0 seconds, `ipc_log_queue_maxsize` warning threshold 100000. The upper limit that does not irreversibly harden the host process is fixed with a constant that cannot be overwritten by the user.
10. **bootstrap payload is picklable spec only**: Raw instances of `Strategy` / `Formatter` are not included in `ctx`, only `kind + constructor args` is passed. The allow-list expression structurally reduces the number of acceptance paths for malicious pickle payloads.
11. **Registry hash verification is SHA-256 and executed in two timings**: at Writer bootstrap ready ACK and at `AttachCurrentProcess(ctx)` execution. Mismatch is Fail-Fast with `RuntimeError`.
12. **silent loss / silent hang / silent fallback are prohibited as v23-based invariants**: Delivery status is classified into 7 levels, and only `unexpected_loss` is treated as a bug. The remaining six types are explainable facts derived from policy.
13. **Bounded shutdown contract (v23h) structurally prohibits permanent blocking of host process**: `bounded wait (≤ timeout) → visible warning → process exits`. Combined with daemon=True to make "process exits" fail-safe.
14. **`pg_name` sanitization rules and strict file name filtering eliminate file path abuse**: Replace OS file name prohibited characters with `_`, exact match filtering to prevent false matches due to prefix matches of `pg_name`.
15. **Side effects on the global state of stdlib are minimized**: resolve locally in Formatter without using `addLevelName()`, start internal thread with empty Context, do not modify `record.levelname`. Maintain neutrality towards other libraries and other code within the same process.
16. **The second `mp.ConfigureLogger()` in the same process is `RuntimeError`**: Structurally eliminates the accident where multiple Writer runtimes/multiple `ctx` coexist in the same process.
17. **Child does not reuse parent client identity after fork inheritance**: Registry consistency is maintained after fork by registering a child-specific client identity in the Writer active client registry. Resurrection after the Writer session ends is prohibited.
18. **Control plane exceptions are normalized to the `RuntimeError` series**: Exceptions originating from internal implementations such as `BrokenPipeError` / `EOFError` do not leak outside the API boundary, and user code exception handlers do not depend on internal implementations.
19. **License is Apache 2.0**: Commercial use, modification, and redistribution are permitted, and the patent clause ensures predictability for users.
---

### 4.12 Summary of this chapter
The security goals of D-SafeLogger v23k can be summarized into the following five points:
1. **Structurally eliminates supply chain paths**: Zero runtime external dependencies + Vendor-Agnostic core means there are no vulnerability propagation paths via third-party dependencies. Apache 2.0 license also ensures legal predictability.
2. **Structurally prohibit "accidental mixing into production"**: `diagnose` is enabled only with the environment variable `"1"`, `sens_kws` is also blocked as a sanctuary, and invalid INI types are Fail-Fast. It is impossible for ``write it in the code and forget to put it back'' or ``a misconfiguration will work silently.''
3. **Actively clarify the scope of warranty and non-warranty in the document**: Outside the HMAC scope, the meaning of `UnexplainedLost`, what the Writer does not guarantee, and What Not To Claim are previously declared in `examples/` and `BENCHMARK.md`.
4. **Structurally ensure that the logging mechanism does not become a DoS trigger**: Do not irreversibly harden the host process with bounded queue + 4 internal constants (3.0 / 5.0 / 10.0 seconds, 100000 maxsize warning). Make "process exits" fail-safe with daemon=True and bounded shutdown.
5. **Classify abnormalities and do not allow silent failure**: 7-layer delivery status classification (only `unexpected_loss` is treated as a bug) + `writer_reject` 6 breakdown + rate-limited stderr warning + Writer exit code, abnormal events are externalized as monitorable facts.
These points are revisited in the next chapter, “5. Detailed Analysis by Function,” as the behavior of individual features such as Append-Only routing, async transport, multiprocess delivery states, and SHA-256, and again in Chapter 7, “Positioning at OSS Release,” as technical value for the audit/compliance and supply-chain-focused segments.
---

> **Main references for this chapter**: `docs/design/D_SafeLogger_Specification_v23k_full.md` §1, §2, §4.4, §6, §7.1, §7.5, §7.6, §9.1, §9.4, §9.5, §9.7, §9.8, §10.1, §10.5, §11.1, §11.6, §11.7, §11.9, §11.13, §11.16, §11.21, §11.22, §11.23, §12.1, §12.3, §12.4, §12.4.1 / `README.md` Overview, Main Features section / `examples/08_compliance_audit.md` / `examples/09_debugging_production.md` / `examples/12_multiprocess_logging.md` / `examples/13_external_rotation_reopen.md` / `LICENSE` / `pyproject.toml` / `MANIFEST.in`
> This document is intended to explain and evaluate the current v23k architecture, and does not include improvement proposals, issue management, or future roadmaps.
## Chapter 5 Detailed Analysis by Function
### 5.0 Chapter structure
This chapter covers the major features of v23k **individually** and organizes each feature's (a) design purpose, (b) operational specifications, and (c) technical characteristics. The functions mentioned across multiple contexts in the previous chapters will also be verbalized again from the perspective of "functional units."
| Section | Feature Group |
|---|---|
| 5.1 | Append-Only Routing Function Group (9 Modes) |
| 5.2 | Generation management (purge/archive) and self-healing |
| 5.3 | Coexistence with external rotation and `ReopenLogFiles()` |
| 5.4 | File Integrity Verification (SHA-256/Manifest) |
| 5.5 | Structured logging and per-sink Formatter configuration |
| 5.6 | Contextualize / FrozenContext |
| 5.7 | Custom log level (register_level) |
| 5.8 | Console color output |
| 5.9 | async transport (QueueTransport) |
| 5.10 | 5 State Life Cycle |
| 5.11 | `dsafelogger.mp` Writer runtime |
| 5.12 | `dsafelogger.mp` log plane / control plane |
| 5.13 | `dsafelogger.mp` Delivery status counters |
| 5.14 | `dsafelogger.mp` bounded shutdown and flush strategy |
| 5.15 | TrackedQueue |
| 5.16 | Operational control using environment variables |
| 5.17 | Elaborating INI/dict settings |
| 5.18 | CLI tool |
| 5.19 | Free-threaded support |
| 5.20 | diagnose (variable automatic expansion) |
| 5.21 | sens_kws masking |
| 5.22 | Organization by function |
| 5.23 | Summary of this chapter |
---

### 5.1 Append-Only Routing Functions
#### 5.1.1 Design Purpose
Design document §7.2:
> **Historical background**: The renaming method became popular due to its simplicity, ``the current log is always `app.log`'', but it has a fatal flaw in that it locks the file **In a Windows environment, renaming results in a Permission Error even if another monitoring tool etc. has the file open, causing the entire backend service to go down**.
>
> **Technical advantage**: D-SafeLogger uses **Append-Only (does not perform any renaming, just switches the stream to a file that has been given a date or sequential number from the beginning)** as its architecture, and completely eliminates this locking problem in O(1). Similar ideas can be found in specific options such as Logback and Log4j2, but no design with this as the default core exists in the Python ecosystem.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.2)
#### 5.1.2 Nine routing modes
Suffix rules established by detailed design document §5.2:
| `routing_mode` | Suffix format | Example | Switching trigger | Generation management target |
|---|---|---|---|---|
| `none` | None | `Default.log` | No switching | — |
| `daily` | `_YYYYMMDD` | `Default_20260328.log` | Change date | ○ |
| `hourly` | `_YYYYMMDD_HH` | `Default_20260328_14.log` | Every hour | ○ |
| `min_interval` | `_YYYYMMDD_HHMM` | `Default_20260328_1430.log` | Specified minute interval (an integer that divides 60) | ○ |
| `startup_interval` | `_YYYYMMDD_HHMMSS` | `Default_20260328_143005.log` | Start time base point specification interval | ○ |
| `size` | `_NNN` (sequential number) | `Default_000.log` | `max_bytes` Excess | ○ (only when max_count is not specified) |
| `count` | `_NNN` (serial number) | `Default_000.log` | `max_lines` Excess | ○ (same as above) |
| `cyclic_weekday` | `_ddd` (day of the week abbreviation) | `Default_thu.log` | Change day of the week | × (overwrite, not applicable) |
| `cyclic_month` | `_MM` (month number) | `Default_03.log` | Month change | × (same as above) |
#### 5.1.3 RoutingStrategy Abstract base class
Detailed design document §5.1:
```python
class RoutingStrategy(ABC):
    @abstractmethod
    def get_current_path(self) -> Path: ...
    @abstractmethod
    def should_switch(self, record: logging.LogRecord) -> bool: ...
    def advance(self) -> None: ... # Update state after file switch
    def on_emit(self) -> None: ... # v22h: hook after record is successfully written
    def is_cyclic(self) -> bool: ... # Cyclic mode?
```

Each Strategy (`NoneStrategy` / `DailyStrategy` / `HourlyStrategy` / `MinIntervalStrategy` / `StartupIntervalStrategy` / `SizeStrategy` / `CountStrategy` / `CyclicWeekdayStrategy` / `CyclicMonthStrategy`) inherits this base and implements suffix determination and switching determination.
#### 5.1.4 Size / count mode branching
Design document §7.3.4: The essential purpose of operation differs depending on whether `max_count` is specified.
| `max_count` | Operating mode | Application |
|---|---|---|
| Specified | Cyclic overwrite | Disk full prevention, log circulation within limited area |
| Not specified (None) | Upper limit reached error | Strict system that "absolutely wants to prevent log loss or unintentional overwriting" |
Behavior of limit reached error mode:
- The serial number increases monotonically up to the maximum value of `suffix_digits` (`.999` if it is 3 digits).
- When the limit is reached, **`OverflowError`** is sent when switching files and the application execution is stopped.
- `backup_count > 0` or `archive_mode=True` contradicts the design intent and causes `ConfigureLogger()` to fail fast with `ValueError`.
This is typical of the design attitude of "stopping a capacity design error rather than allowing it to continue running."
#### 5.1.5 min_interval constraints
Design document §7.3.2: In `min_interval` mode, `interval` can only be specified as a numerical value (unit: minutes), and only numbers that are divisible by 60 can be specified (`{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}`). This is a constraint to guarantee "switching timing on the hour".
#### 5.1.6 Flexible unit specification for startup_interval
Design document §7.3.3: In `startup_interval` mode, in addition to an integer for `interval`, string specifications such as `'12h'` / `'1d'` are also accepted. The suffix uses the absolute date and time at the moment of switching (`YYYYMMDD_HHMMSS`).
#### 5.1.7 Base file name determination and sanitization
Design document §7.1:
- Basic configuration: `{log_path}/{pg_name}` + Suffix + `.log`
- Automatically create `os.makedirs` when `log_path` directory does not exist
- Sanitization of `pg_name`: Forbidden characters in OS file names (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) is replaced with `_` (generates a safe file name while avoiding startup inhibition instead of Fail-Fast)
#### 5.1.8 Functional Observation
- The routing mode is **fixed at startup** and dynamic changes during runtime are not expected.
- 9 modes including `none` can be selected with the `routing_mode` argument and can also be overwritten with INI/environment variables (for each module).
- The implementation is a pull-type decision model that calls `should_switch()` every time immediately before emit. In time-based mode, a simple implementation that evaluates the current time each time (Detailed Design Document §5.4–§5.6).
---

### 5.2 Generation management (purge/archive) and self-healability
#### 5.2.1 Switching flow (design document §7.5)
```text
1. Handler asks Strategy if it is necessary to switch
2. Close the old stream if necessary and open the file with the new name (do not rename)
3. If enable_hash=True, generate SHA-256 in HashWorker or PurgeWorker/ArchiveWorker
4. If the target is generation management, sort log files of the same type within the directory and identify log files that exceed backup_count.
5. archive_mode=False → unlink, True → ZIP (also works with .sha256 sidecar)
6. In case of failure, only issue a warning and leave self-repair to the next switching timing
7. Serialize maintenance of the same family
```

#### 5.2.2 Behavior of archive_mode
Design document §7.5:
| `archive_mode` | Handling old files | Handling sidecars |
|---|---|---|
| `False` (default) | `unlink` | `.sha256` Sidecar is also deleted |
| `True` | ZIP conversion | `.sha256` Sidecar also included in ZIP, original file deleted |
**Prevention of storage exhaustion**: Verify the free space with `shutil.disk_usage()` before starting the ZIP processing, and if there is insufficient space, stop the process + console warning.
#### 5.2.3 PurgeWorker / ArchiveWorker / HashWorker
Detailed design document §7 / ​​§15.5:
- All `threading.Thread` derivatives (`daemon=True`)
- Starts only when switching files (Fire-and-Forget)
- Joined as a bound wait target during safe shutdown
- In case of failure, processing continues with only stderr warning (self-repair)
#### 5.2.4 Serialization of the same family
Design document §7.5:
> Maintenance serialization of the same family: purge/archive belonging to the same `directory + pg_name` will not be executed in parallel. To avoid duplicate deletion, duplicate ZIPing, and frequent conflict warnings, maintenance of the same family is serialized in key units.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.5)
This is a rule to eliminate conflicts in ``settings where multiple routing modes share the same `pg_name` prefix.''
#### 5.2.5 Stricter file name filtering
Design document §7.5: To prevent false matches due to prefix matches of `pg_name` (e.g., the pattern `'App'` also matches `AppServer_*.log`), target files must only **exactly match** one of the following:
- `{pg_name}.log` (NoneStrategy)
- `{pg_name}_{suffix}.log` (Other Strategy)
#### 5.2.6 Not subject to generation management when max_count is specified
Design document §7.3.4 / §7.5:
- `max_count` of `size` / `count` specified (cyclic) → Due to file name reuse **Not subject to generation management**
- `cyclic_weekday` / `cyclic_month` → Same as above
- Because this is a "no history" mode and contradicts the semantics of generation management
#### 5.2.7 Functional Observation
- Generation management is expressed as `backup_count > 0` (number of retention) instead of ON/OFF.
- "Save compressed instead of delete" can be switched independently by archive_mode.
- Due to self-healing properties, the "delete failed because another process is locking" condition does not become a permanent failure.
---

### 5.3 Coexistence with external rotation and `ReopenLogFiles()`
D-SafeLogger does not forbid external rotation. For compatibility with existing operations, it provides `ReopenLogFiles()` only for `routing_mode='none'`.

This is a compatibility path, not the design center. The design center is append-only routing: the logging layer chooses the destination at write time instead of mutating the active file and depending on signal/reopen coordination.

#### 5.3.1 Design Purpose
Design document §7.3.1 and `examples/13_external_rotation_reopen.md`:
When coexisting with an external rotator such as `logrotate` on Linux/Unix, this library officially supports only `routing_mode='none'`. After the external side executes rename + create, the application side explicitly calls `ReopenLogFiles()` to reopen the new inode.

#### 5.3.2 Constraints
Design document §7.3.1:
> `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / cyclic etc. D-SafeLogger Routing, in which file switching is done by itself, and external rotation operation should not be mixed. `ReopenLogFiles()` sends `ValueError` if any of the writer-side file sinks is `routing_mode != 'none'`.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.3.1)
#### 5.3.3 Difference between single / multiprocess
Design document §10.4 / §11.20:
| Version | Behavior |
|---|---|
| single-process | reopen file handle synchronously |
| multiprocess | Control request to control plane → Wait for ACK (`CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` seconds) |
Design decisions for the multiprocess version of ACK timeout (§11.20.3):
> The basis for 5.0 seconds is a value that takes into account the typical postrotate script execution time (within a few seconds) in logrotate/cron operations and the margin for the reopen processing time on the Writer side (usually several tens of ms).
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.20.3)
#### 5.3.4 Boundary conditions on network, virtual, and volatile filesystems
On a local POSIX filesystem, an external rename can succeed while the writer continues appending through the old descriptor. The problem can therefore stay hidden for some time. On NFS, SMB/CIFS, FUSE mounts, cloud-synced folders, container bind mounts, and other network or virtual filesystems, the failure modes around external rename/unlink of an active log file can become more visible and more implementation-dependent.

On NFS, unlinking an open file may appear as a `.nfsXXXX` silly-rename file. Depending on client/server behavior, cache state, deletion races, crashes, or reconnects, operators may see orphaned files, unreleased space, `ESTALE`, or cleanup failures.

On SMB/CIFS, Windows-style sharing, locks, oplocks, or cache behavior can affect rename and delete behavior. FUSE mounts, cloud-synced folders, and container bind mounts can also differ from local ext4/xfs semantics for rename, unlink, caching, and durability.

In-memory or virtual filesystems such as D-MemFS have a different risk profile. The main questions are durability, quota, process lifetime, and explicit export/flush responsibility rather than distributed rename/unlink behavior. They can be useful for temporary buffers, tests, and isolated sandboxes, but audit-oriented active logs need a separate persistence strategy.

D-SafeLogger therefore does not claim universal active-log safety across filesystems. What it avoids structurally is the design where an external process renames or truncates the active file and correctness depends on a later signal/reopen step. For robust and audit-oriented deployments, prefer writing active logs to a durable local filesystem and transferring only closed routed files to NFS, SMB, cloud-synced locations, or archive storage.

#### 5.3.5 Functional observations
- Design that explicitly positions `routing_mode='none'` as "external rotation coexistence mode."
- By rejecting the mix of internal routing and external rotation using `ValueError`, operational confusion (obscuring who is in charge of rotation) is structurally eliminated.
- `ReopenLogFiles()` is a compatibility path for external rotation, not D-SafeLogger's central file lifecycle.
- For special destinations such as NFS, SMB, FUSE, or in-memory filesystems, append-only routing does not remove every filesystem-specific risk. For robust deployments, write active logs to a durable local filesystem and transfer only closed files to external storage.
---

### 5.4 File Integrity Verification (SHA-256/Manifest)
#### 5.4.1 Design overview
The summary was described in Chapter 4 §4.5, but here we will focus on the implementation level of detailed design document §15.
#### 5.4.2 Implementation of hash calculation
Detailed design document §15.2:
```python
def compute_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(65536) # 64KB chunk
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()
```

- Chunk reading (64KB units) to support large files.
- Only standard library `hashlib` is used (zero-dep maintained).
#### 5.4.3 Atomicity of sidecar writes
Detailed design document §15.3:
```python
def write_sidecar(file_path: Path, hash_value: str | None = None) -> None:
    if hash_value is None:
        hash_value = compute_sha256(file_path)
    sidecar_path = file_path.with_suffix(file_path.suffix + '.sha256')
    temp_path = sidecar_path.with_suffix(sidecar_path.suffix + '.tmp')
    temp_path.write_text(
        f'{hash_value} {file_path.name}\n',
        encoding='utf-8',
    )
    os.replace(temp_path, sidecar_path)
```

- Write to `.sha256.tmp` → Atomicly replace with `os.replace()`.
- `hash_value` can be received as an argument to prevent double calculations (pre-calculation in Purge/Archive Worker is reused).
#### 5.4.4 Lock order of manifest addition
Detailed design document §15.4:
```python
def append_manifest(file_path, manifest_path, hash_value=None):
    ...
    lock = _get_manifest_lock(manifest_path.resolve())
    # Lock ordering: family_lock -> manifest_lock (never reverse)
    # Do NOT acquire family maintenance lock while holding this lock
    with lock:
        with open(manifest_path, 'a', encoding='utf-8') as f:
            f.write(entry)
```

- Additions to the same `manifest_path` are **serialized** with lock for each key (preventing manifest line corruption and line-by-line conflicts).
- lock ordering rule: `family_lock → manifest_lock` (reverse ordering prohibited). This is specified in the design to avoid deadlocks.
- The directory is automatically generated with `parents=True, exist_ok=True`.
#### 5.4.5 HashWorker implementation
Detailed design document §15.5:
```python
class HashWorker(threading.Thread):
    def __init__(self, file_path, manifest_path=None):
        super().__init__(daemon=True, name=f'HashWorker-{file_path.name}')
        self._file_path = file_path
        self._manifest_path = manifest_path

    def run(self) -> None:
        try:
            def _run_body() -> None:
                write_sidecar(self._file_path)
                if self._manifest_path is not None:
                    append_manifest(self._file_path, self._manifest_path)
            _run_in_empty_context(_run_body)
        except OSError as e:
            print(f'[D-SafeLogger] Hash generation failed for ...', file=sys.stderr)
        finally:
            _unregister_worker(self)
```

Noteworthy points:
- Use `_run_in_empty_context()` to ensure that the internal thread does not inherit the parent's context (conventions in §9.5 of the design document).
- If failure occurs, continue with only a warning (same as self-healing of purge).
- Since the file name is included in the thread name, it is easier to identify stuck threads when diagnosing them.
#### 5.4.6 Priority control of execution order
Design document §7.6.4:
| Condition | Execution method |
|---|---|
| `enable_hash=True` and non-cyclic and `backup_count > 0` | **Preemptive execution** of hash generation in PurgeWorker/ArchiveWorker |
| `enable_hash=True` AND non-cyclic AND `backup_count=0` | Fire-and-Forget independent `HashWorker` |
| cyclic routing and `enable_hash=True` | `ConfigureLogger()` fails fast with `ValueError` |
The order guarantee that ``hash is always determined before purge'' is specified at the design document level.
#### 5.4.7 Functional Observation
- HMAC signature/CLI verification commands are explicitly out of scope in design document §7.6.7.
- `sha256sum -c` compatible format allows verification with OS standard tools.
- ``File disappearance'' can also be detected by manifest (undetectable by sidecar alone).
---

### 5.5 Structured logging and per-sink Formatter configuration
#### 5.5.1 Default format
Design document §6.1:
```text
%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s
```

- Date and time format: `%Y-%m-%d %H:%M:%S`
- Level name abbreviation: `DBG` / `INF` / `WAR` / `ERR` / `CRI` (and `register_level()` 3-letter abbreviation of registered custom level)
- Contextualize information is added to the end of the message in `[task_id:42 worker:db_sync]` format
#### 5.5.2 Structured logs (JSON Lines)
Design document §6.4: Switch to 1 line per JSON in `ConfigureLogger(structured=True)`. Since it is **completely orthogonal** to the Append-Only architecture, routing and generation management will continue to operate without any changes.
Terms of `structured=True`:
- Context given with `contextualize()` is output as a top level field
- String specification for `fmt` / `file_fmt` / `console_fmt` and simultaneous specification with Formatter instance specification is **`ValueError`** (violation of exclusive specification)
#### 5.5.3 Per-sink Formatter configuration (v20 new feature)
Design document §6.3:
```python
ConfigureLogger(
    file_fmt=StructuredFormatter(),
    console_fmt='%(levelname)s %(message)s',
)
```

Resolution priority:
```text
file_fmt specified → used for file sink
file_fmt falls back to None or empty string → fmt
fmt is also None → default format
(same as console_fmt)
```

- `fmt` is the existing overall default Formatter (maintaining backward compatibility)
- `file_fmt` / `console_fmt` is a `str` or `logging.Formatter` instance
- Corresponding keys can also be set in INI/config_dict (§5.3)
- Settings from environment variables are not supported (because Formatter instances cannot be expressed using environment variables)
- If `file_fmt` / `console_fmt` is not specified, the behavior is completely the same as v18 (non-destructive change)
#### 5.5.4 Four Formatter families
Detailed design document §4:
| Class | Role |
|---|---|
| `DSafeFormatter` | Text output (default format). Compatible with all styles of `%` / `{}` / `$` |
| `StructuredFormatter` | JSON Lines. `contextualize()` Information to the top level. `extra` attribute is vendor-neutral and output to JSON (standard `LogRecord` key and internal `_ds_*` attribute are excluded) |
| `DiagnosticFormatter` | Text output when `diagnose=True`. Expand `f_locals` |
| `DiagnosticStructuredFormatter` | `diagnose=True` and `structured=True`. `f_locals` to JSON `locals` field |
#### 5.5.5 Multiprocess version Formatter spec
Detailed design document §15a.5.2a:
In the multiprocess version, the Formatter instance may not be picklable, so pass it as the picklable spec of `kind + constructor args`.
```python
class FormatterSpec(TypedDict, total=False):
    kind: Literal[
        'logging.Formatter',
        'DSafeFormatter',
        'DiagnosticFormatter',
        'StructuredFormatter',
        'DiagnosticStructuredFormatter',
    ]
```

Design document §10.5 provisions:
> The multiprocess version of `fmt` / `file_fmt` / `console_fmt` allows the same type faces as the single-process version, but only instances of **`logging.Formatter` body and D-SafeLogger built-in Formatter body** are allowed to freeze/reconstruct at the process boundary.
>
> Custom formatter instances (including custom subclass) other than the above allow-list are set to `TypeError`, and only the picklable spec consisting of `kind + constructor args` is passed on the Writer side.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §10.5)
#### 5.5.6 Functional Observation
- Structured logs and custom formats are exclusive (avoiding semantic conflicts due to implementing the same function through different routes).
- File output (JSON for observability tools) and console output (human-readable text) can use different formats through per-sink Formatter configuration.
- Even via multiprocess, custom Formatter is constrained according to allow-list, and the unpickleability problem is structurally avoided.
---

### 5.6 Contextualize (contextualize / FrozenContext)
#### 5.6.1 Design Purpose
Design document §2 / §9.5:
- Context management that provides independent isolation not only between threads but also between asyncio tasks.
- The producer side takes a snapshot at hand-off, and the consumer/writer side does not refer to live `contextvars`.
- Reduced hand-off cost via async/multiprocess to **O(1) pass by reference** (v20 No-Copy Snapshot).
#### 5.6.2 Implementation of FrozenContext
Design document §9.5:
- Adopted `contextvars.ContextVar[MappingProxyType]` (changed from `ContextVar[dict]` in v20).
- Due to immutability of `MappingProxyType`, snapshot is O(1) pass by reference.
- `contextualize()` Generation of a new MappingProxyType at the entrance is O(n).
#### 5.6.3 Fail-Fast Rejection of Mutable Values
Design document §2:
> Pass only immutable values ​​(str, int, float, tuple, etc.) to kwargs of `contextualize()`**. If the value of kwargs passed to contextualize() is a typical mutable object such as list, dict, set, etc., a TypeError or ValueError is raised (Fail-Fast). This ensures that unintended side effects due to O(1) reference passing are detected during development.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §2)
Note: `MappingProxyType` only protects top-level key operations, and cannot prevent content changes if the value is mutable (list, dict, etc.). This is specified in the specifications.
#### 5.6.4 Hand-off rules for sync mode and async mode
Design document §9.5:
- **sync mode**: Formatter retrieved directly from `contextvars` (for transparency to 3rd party standard Logger)
- **async mode**: Do not trust `contextvars` on the consumer thread side, prefer `FrozenContext` reference given to `LogRecord` on the producer thread side
#### 5.6.5 thread boundary semantics
Design document §9.5:
- Initial context inheritance to new user-generated threads follows Python specifications
- Internal threads generated by D-SafeLogger **always start with empty `Context`** → Prevent context leakage to internal threads
#### 5.6.6 Correct context snapshot fallback (v21)
Design document §2:
Change context return in Formatter from `getattr(record, '_ds_context', None) or get_context()` pattern to `hasattr` base branch:
- If the `_ds_context` attribute exists, **even an empty `MappingProxyType` is treated as an authoritative snapshot**
- Fallback to `get_context()` only when calling directly without going through Transport
This prevents the accident of ``when an empty context is received via IPC, the live context is arbitrarily referenced on the Writer side''.
#### 5.6.7 multiprocess convention: Persistence of `_ds_context` / `_ds_extra`
Design document §11.8.2:
> `_ds_context` and `_ds_extra` always exist as keys, and empty is represented as `{}`.
>
> Supplement: This standing convention is necessary to maintain the hasattr-based context snapshot fallback established in v21 at IPC boundaries. Since the distinction based on hasattr does not hold on the Writer side that receives `LogEvent` via pickle, the existence of the key clearly indicates that "the snapshot has been acquired on the Capture side" to ensure that no live context reference occurs on the Writer side.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.8.2)
#### 5.6.8 Functional Observation
- When exiting the scope of `contextualize()`, state rewinding using Token is performed (standard ContextVar rewinding pattern).
- `examples/06_web_api_logging.md` presents a typical pattern of attaching request_id / user_id etc. with `contextualize()`.
- When combined with structured=True, the context field appears at the JSON top level.
---

### 5.7 Custom Log Level (register_level)
#### 5.7.1 Functional specifications
Design document §9.9:
```python
register_level(name='TRACE', value=5, abbreviation='TRC', color='\033[90m')
```

- `name`: Level name (e.g. TRACE)
- `value`: Log level value (other than standard 5 levels)
- `abbreviation`: 3 letter abbreviation (e.g. TRC)
- `color`: ANSI color code
#### 5.7.2 Forcing Calling Order
Design document §9.9.2:
```text
register_level() ← Any number of times (even 0 times)
     ↓
ConfigureLogger() ← Only once
     ↓
GetLogger() ← Any number of times
```

`register_level()` after `ConfigureLogger()` is `RuntimeError`. The `shutting_down` state is similarly rejected (because additional registration during terminating would destabilize the shared state).
#### 5.7.3 Built-in level of protection
Design document §9.9.3: All of the following operations are rejected as `ValueError`:
- Override built-in values (10, 20, 30, 40, 50)
- Override built-in names (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Override built-in abbreviations (DBG, INF, WAR, ERR, CRI)
#### 5.7.4 3-layer pipeline alignment with all layers
Design document §9.9.4: After `register_level('TRACE', ...)`, `'TRACE'` is available in all layers:
- Argument: `ConfigureLogger(default_level='TRACE', ...)`
- INI: `level = TRACE` of `default_level = TRACE` or `[dsafelogger:mod]`
- Environment variable: `D_LOG_LEVEL=TRACE` or `D_LOG_MODULES=mymod:TRACE`
If an unregistered level name is specified, Fail-Fast validation will result in `ValueError`.
#### 5.7.5 Dynamic generation of convenience methods
Design document §9.9.5:
- `logger.trace(msg)` method is dynamically added to `register_level('TRACE', value=5, ...)` → `DSafeLogger`
- Skip adding a convenient method if it conflicts with an existing method name (`logger.info()`, etc.) (`logger.log(value, msg)` can be used)
- Since a type error occurs in mypy / pyright, the use of `logger.log(VALUE, msg)` or the assignment of `# type: ignore[attr-defined]` is described in the documentation.
#### 5.7.6 Re-import rules for spawn workers
Design document §10.3:
- spawn worker bootstrap may re-execute module top-level `register_level()`
- Re-registration of **same definition** (exact match of name / value / abbreviation / color) is allowed as **idempotent no-op**
- **Unmatched re-registration** is considered registry divergence `RuntimeError`
This allows the normal writing style of writing `register_level()` at the module top level to be maintained in the spawn environment.
#### 5.7.7 multiprocess registry hash matching
Design document §11.7: Registry hash (SHA-256) is included in `ctx` and checked at Writer bootstrap ready ACK and when `AttachCurrentProcess(ctx)` is executed. Mismatch is Fail-Fast with `RuntimeError`.
#### 5.7.8 Functional Observation
- Extension closes before `ConfigureLogger` (does not allow dynamic changes beyond initialization boundaries).
- Built-in levels are protected as "inviolable sanctuaries".
- Consistent with standard Python module loading rules by treating spawn re-import as idempotent.
---

### 5.8 Console color output
#### 5.8.1 Design Purpose
Design document §9.6: The default console output destination is `sys.stderr`. ANSI color codes are assigned to abbreviated display level values. For Windows, enable VT100 with `os.system("")` during initialization.
#### 5.8.2 Instance variable of LEVEL_MAP / COLOR_MAP
Design document §9.8 / §9.9.6:
- `DSafeFormatter.LEVEL_MAP` and `ColorStreamHandler.COLOR_MAP` are **instance variables instead of class variables**, and a built-in 5-level + custom level integration map is built when Formatter is initialized.
- This allows multiple Formatter instances to have different level registration states within the same process.
#### 5.8.3 Color palette settings (INI/dict only)
Design document §9.6 / §5.3:
- The built-in 5-level color palette can be changed using the `color_{lowercase_abbreviation}` key in the `[global]` section of INI / config_dict (e.g. `color_dbg = 36`, `color_inf = 32`, `color_war = 33`, `color_err = 31`, `color_cri = 1;31`).
- The value is the numeric part of the ANSI SGR parameter (e.g. `36`, `1;31`, `38;5;208`).
- Custom level colors can also be overwritten with the same naming convention.
- Settings from environment variables and arguments are intentionally not supported (**second layer only**).
#### 5.8.4 Color palette merging order
Design document §9.6:
```text
(1) Built-in default
  → (2) register_level() Specified color
    → (3) INI/Dictionary color_{abbreviation} key (final override)
```

#### 5.8.5 `color_{abbreviation}` key validation
Design document §5.3:
- **Unknown abbreviation**: If the part after `color_` does not match a valid abbreviation (built-in + custom level), stderr warning + key ignored
- **Illegal characters**: stderr warning + key ignored if value contains characters other than `0-9` and `;`
- **Empty string**: Enabled. Disable colorization for that level
- In either case, continue processing with warning + skip instead of Fail-Fast (does not prevent application of other valid color settings)
#### 5.8.6 Color control priority
Design document §4.5:
```text
1. If NO_COLOR is set, color is always disabled regardless of the value.
2. If NO_COLOR is not set and {prefix}_COLOR is set, follow that value.
3. If both are not set, use sys.stderr.isatty() to determine TTY and decide automatically.
```

`NO_COLOR` is an industry standard (https://no-color.org/) and is the only environment variable not affected by `env_prefix`.
#### 5.8.7 Functional Observation
- The fact that the color palette settings are exclusive to the second layer (cannot be set using environment variables or arguments) is an intentional design restriction. Color settings are assumed to be managed by INI as a "standard theme within the organization."
- Flexibility to disable individual level colors with an empty string like `color_dbg = `.
- ColorStreamHandler is `_ds_required = False` (best-effort sink), and even if it fails, it will only be recorded in `_writer_best_effort_failures` (it will not be aggregated in `reject_counter`).
---

### 5.9 async transport (QueueTransport)
#### 5.9.1 Architecture
Detailed design document §15a.3:
```python
class QueueTransport(Transport):
    def __init__(self, handlers, **kwargs):
        self._queue = queue.Queue(-1)
        self._queue_handler = DSafeQueueHandler(self._queue, **kwargs)
        self._listener = DSafeQueueListener(self._queue, *handlers)

    def start(self):
        self._listener.start()

    def stop(self, timeout):
        return self._listener.stop_with_timeout(timeout)

    def get_root_handlers(self):
        return [self._queue_handler]

    def get_sink_handlers(self):
        return list(self._listener.handlers)
```

#### 5.9.2 Complete override of DSafeQueueHandler
Design document §9.3:
- Queue hand-off of D-SafeLogger does not directly use stdlib `QueueHandler.prepare()` and does not call `super().prepare()` **Complete override**
- Reason: To separate stdlib differences between Python 3.11 / 3.13 / 3.14 from semantics.
Responsibilities on the producer thread side:
- `contextualize()` information to private attribute `_ds_context` of `LogRecord` snapshot
- Convert `f_locals` to a masked, repr-converted snapshot only if `diagnose=True` and `exc_info` are present (`_ds_diag_frames`)
- Lightweight hand-off of copy + context snapshot in normal logs
#### 5.9.3 Safe Termination Assurance Level
Design document §9.3:
- **Log body flush**: Top priority. During normal termination, as long as queue drain is successful, the aim is to complete the output of accepted queued log records before starting shutdown.
- **housekeeping (hash / purge / archive)**: best-effort. A bounded wait is performed, but when timeout occurs, a warning is issued and termination is prioritized.
#### 5.9.4 Recommended finishing order
Design document §9.3:
```text
1. State transition and reference saving
2.queue drain
3. worker join
4. handler flush/close
```

In particular, stop the listener before worker join. This is because the listener may cause a rollover while processing the last queued record and start a new worker.
#### 5.9.5 Positioning of daemon=True
Design document §9.3:
> Since the daemon thread can stop abruptly during shutdown, it should not be used as a basis for safety during normal termination. `daemon=True` remains as a backstop at the time of abnormal termination.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §9.3)
#### 5.9.6 Separating timeout
Design document §9.3:
Shutdown separates queue drain timeout and worker join timeout. If `join()` cannot be continued due to late finalization, it will be degraded to warning and termination will be given priority.
#### 5.9.7 Transport full integration of module-specific path (v21)
Design document §2:
- Apply `is_async=True` semantics consistently to module-specific paths as well as root routes.
- `Pipeline` holds `module_transports: dict[str, Transport]` and structurally stops all Transports at `stop()`
- handler attach to module logger via `pipeline.get_module_handler()`
#### 5.9.8 Functional observation
- `is_async=True` is useful in applications where the GUI thread/request handler thread does not block I/O.
- `examples/11_async_performance.md` shows typical application (high throughput).
- When used with `is_async=True` in multiprocess version, double queuing of process-local async queue + multiprocess log queue + Writer dispatch (§11.17).
---

### 5.10 5-state life cycle
#### 5.10.1 State definition
Design document §9.2:
| Status | Meaning |
|---|---|
| `unconfigured` | Initial state |
| `auto` | `GetLogger()` Preceding auto-fire initialized state |
| `explicit` | State where `ConfigureLogger()` is explicitly called from application code |
| `configuring` | `ConfigureLogger` Internal state during execution (`_lifecycle_lock` held) |
| `shutting_down` | `_shutdown()` Internal state during execution |
#### 5.10.2 State transition table (reposted)
Design document §9.2:
| Current | Event | Transition destination |
|------|---------|---------|
| `unconfigured` | `ConfigureLogger()` | `configuring` |
| `unconfigured` | `GetLogger()` Preceding | `configuring` (auto-fire) |
| `configuring` | Successful completion | `explicit` or `auto` |
| `configuring` | Exception occurred | `unconfigured` (rollback) |
| `configuring` | Same thread reentrant | No-Op return |
| `auto` | `ConfigureLogger()` | `configuring` (old Pipeline stop → reinitialization) |
| `auto` | `_shutdown()` | `shutting_down` |
| `explicit` | `ConfigureLogger()` | **No-Op return** |
| `explicit` | `_shutdown()` | `shutting_down` |
| `shutting_down` | Completed | `unconfigured` |
| `shutting_down` | `ConfigureLogger()` | No-Op |
#### 5.10.3 Concurrency Safety Conventions
Design document §9.2:
- `_lifecycle_lock` is `RLock`. Reentrancy of the same thread is a No-Op, and another thread re-evaluates the state after waiting for lock acquire.
- Exception handling in `configuring`: `try/finally` prevents `_configure_state` from remaining as `configuring`.
- `GetLogger` in `configuring`: Waiting until initialization is completed in another thread, short-circuiting by returning existing logger only when re-entering the same thread.
- `ConfigureLogger` in `shutting_down`: No new initialization, No-Op or explicit rejection.
- `register_level()` in `shutting_down`: `RuntimeError`.
#### 5.10.4 v21 Revised
Design document §2 v21 revised:
- Execute the entire `_do_configure()` of `ConfigureLogger` under `_lifecycle_lock` retention.
- `GetLogger` detects the `'configuring'` state and waits for the lock structure.
- Safely prevent concurrent state reading during initialization.
#### 5.10.5 Functional observation
- 5 states + RLock allows auto-fire / explicit initialization / reinitialization / shutdown to be represented in a single state machine.
- Promotion of `auto` → `explicit` (explicit priority) is allowed, but re-promotion of `explicit` to `ConfigureLogger()` is No-Op (guaranteed as known behavior).
- The multiprocess version (`mp.ConfigureLogger`) has **`RuntimeError`** for the second time in the same process, which is stricter than the single-process version.
---

### 5.11 `dsafelogger.mp` Writer runtime
#### 5.11.1 Writer runtime responsibilities
Design document §11.5 / §11.6:
- owns file sinks
- Received `LogEvent` from log plane queue
- Select sink group according to route
- Receive `ATTACH` / `DETACH` / `REOPEN` / `STOP` / `STATUS` from control plane
- file switch / routing / hash / manifest / purge / archive
- Serialization of reopen / shutdown
- Safe termination based on number of active clients and stop requests
#### 5.11.2 Writer runtime is internally implemented
Design document §11.5:
> Writer runtime is an implementation element inside the logger, and is not something that developers can explicitly start directly using `multiprocessing.Process` / `subprocess.Popen`, etc. The contracts that developers should be aware of are limited to `ctx`, `AttachCurrentProcess()`, and `DetachCurrentProcess()`.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.5)
#### 5.11.3 protocol payload (detailed design document §15a.5.1)
```python
@dataclass(frozen=True)
class BootstrapContext:
    protocol_version: int
    session_id: str
    writer_pid: int
    log_queue: multiprocessing.Queue
    control_queue: multiprocessing.Queue
    resolved_config: dict[str, object]
    resolved_config_digest: str
    registry_hash: str
    log_queue_maxsize: int
    ipc_log_timeout: float
    overflow_policy: Literal['drop']
```

#### 5.11.4 Structure of LogEvent
```python
class LogEvent(TypedDict):
    name: str
    levelno: int
    levelname: str
    pathname: str
    filename: str
    module:str
    lineno: int
    funcName: str
    msg:str
    created: float
    msecs: float
    relativeCreated: float
    process: int
    processName: str
    thread: int
    threadName: str
    _ds_route: str
    _ds_context: dict[str, Any]
    _ds_exc_text: str | None
    _ds_diag_frames: list[dict[str, Any]] | None
    _ds_extra: dict[str, Any]
```

#### 5.11.5 `_serialize_record()` / `_reconstruct_record()` separation of duties
Detailed design document §15a.5.2:
- `LogEvent` is determined at the client side Capture boundary
- `_ds_context` and `_ds_extra` always have a key, and the empty one is `{}`
- Snapshot diagnose is determined on the client side and does not re-evaluate live traceback / live context on the Writer side
- `_reconstruct_record()` only restores `LogRecord` for sink dispatch using `logging.makeLogRecord()`, **does not re-execute logger hierarchy evaluation or level determination**
This is an implementation manifestation of the specification in §11.3 of the design document that ``Capture semantics is the responsibility of the Capture layer.''
#### 5.11.6 Functional Observation
- Writer runtime is implemented as an internal process and started at `multiprocessing.Process`.
- File ownership, routing, hash, manifest, purge, archive, and reopen are all consolidated in Writer.
- The worker process only sends `LogEvent` via IPC and does not perform file operations (§4.6.1).
---

### 5.12 `dsafelogger.mp` log plane / control plane
#### 5.12.1 log plane
Design document §11.9.1:
- One-way client → Writer
- payload is `LogEvent`
- internal transport is **bounded `multiprocessing.Queue`** (v23h: derived from `TrackedQueue`)
- Main path of file writing path
#### 5.12.2 control plane
Design document §11.9.2:
- Handles `reopen` / `attach` / `detach` / `stop` / `status`
- has request/ACK
- `ReopenLogFiles()` uses control plane **Synchronization API**
- ACK is returned on **per-request `multiprocessing.Pipe(duplex=False)` reply path** (§11.8.3)
- Different QoS for each command type
#### 5.12.3 QoS by command type
Design document §11.16.3:
| command | QoS |
|---|---|
| `ATTACH` / `DETACH` / `STOP` | **drop not possible** |
| `REOPEN` / `STATUS` | **ACK required** |
| `LOG` overflow policy does not apply to control plane command |
#### 5.12.4 Design Principles
Design document §11.9:
- Do not mix control commands in normal log queues
- Do not mix ACK in log plane
- Do not include non-picklable synchronization objects in the control payload
- Do not send Queue as the payload of another Queue (Queue-in-Queue method is not adopted because it does not hold due to Python `multiprocessing` constraints)
- Pipe send/recv failure is not leaked as raw `BrokenPipeError` / `EOFError`, but is normalized to `RuntimeError` system as control plane failure.
#### 5.12.5 Structure of ControlRequest
Detailed design document §15a.5.1:
```python
class ControlRequest(TypedDict):
    request_id: str
    client_id: str
    command: Literal['ATTACH', 'DETACH', 'REOPEN', 'STOP', 'STATUS']
    reply_to: Any # multiprocessing.connection.Connection (Pipe send end)
    payload: dict[str, Any]
```

#### 5.12.6 Functional Observation
- The separation of the log plane and control plane is a well-reasoned design decision because "ACK timeout, request serialization, QoS, and error transmission have different semantics than normal logs" (§11.9).
- The reply path by per-request pipe is fixed as an alternative to the Queue-in-Queue method (§11.8.3).
---

### 5.13 `dsafelogger.mp` Delivery status counters
#### 5.13.1 Hierarchy of delivery status (reposted, §2.8.14)
Design document §12.3:
**Lifecycle states**: attempted → accepted → enqueued → delivered_per_sink → delivered
**Terminal states**: rejected / dropped / writer_reject / partial_delivered / unexpected_loss / writer_best_effort_failures (accounted separately)
**Policy qualifier**: overload_shed
#### 5.13.2 Per-record accounting rules by sink classification (v23h, §12.3)
Each handler distinguishes between required and best-effort using the `_ds_required: bool` class attribute.
| handler | `_ds_required` | Meaning |
|---|---|---|
| `AppendOnlyFileHandler` | `True` (default) | required sink. delivered Judgment target |
| `ColorStreamHandler` | `False` | best-effort sink. delivered Non-judgment and failures are recorded separately |
| User-specific `logging.Handler` derivation | No attribute → treated as `True` | Custom handler is default required |
per-record accounting rules:
- All required handlers succeeded → `delivered` (counter not incremented)
- All required handlers fail → increment `_reject_counter += 1`, `writer_sink_reject` or `writer_policy_reject` (increment both for records where both causes are mixed)
- Only some required handlers succeed → `_writer_partial_delivered += 1` (terminal state is `partial_delivered`, `writer_sink_reject` / `writer_policy_reject` is not incremented)
- best-effort handler failure → `_writer_best_effort_failures += 1` only (no aggregation to `reject_counter`)
#### 5.13.3 Conditions for establishing partial_delivered
Design document §12.3:
> partial_delivered and single handler route: `partial_delivered` is a terminal state that indicates a "mixed success and failure" state within the required sink set. When there is one required sink set (a typical `root` route or module route with a single file configuration), the concept of partial does not hold, so the counter always remains 0. Partial is observed only in configurations where the user has registered multiple required handlers for the same route.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §12.3)
#### 5.13.4 6 breakdown of writer_reject (v23h)
Design document §12.3:
| Classification | Definition |
|---|---|
| `writer_route_reject` | route unresolvable, or route target sink absent |
| `writer_reconstruct_reject` | Corruption/reconstruct failure of LogEvent (separated from `writer_event_reject` in v23h) |
| `writer_close_marker_reject` | Invalid CloseMarker (missing client_id / session mismatch / unknown client, separated in v23h) |
| `writer_sink_reject` | Required sink exists but emit / write / flush fails (per record) |
| `writer_policy_reject` | Reject delivery due to required handler filter or Writer side policy (per record) |
| `writer_format_reject` | formatter / JSON encode impossible (folded into `writer_sink_reject` in v23h) |
All are assigned a dedicated counter and stderr warning (rate-limited).
#### 5.13.5 client side drop counter
Design document §11.22.1: Increment the client side counter in the following events:
- log queue `put()` timeout / `queue.Full`
- Send failure without attach
- command failure due to control plane transmission failure
#### 5.13.6 Writer side drop / reject counter
Design document §11.22.2: Increment the Writer side counter in the following events:
-protocol failure
- route failure (unknown route increments reject counter + stderr warning; implicit fallback to root is prohibited)
- discard due to sink failure
#### 5.13.7 Output destination and timing
Design document §11.22.3:
- At least visible via stderr warning
- Output summary during shutdown
- public getter API is not a mandatory requirement for v22h basic design
#### 5.13.8 Writer exit code
Design document §11.22.4:
- Normal termination is exit code 0
- Abnormal termination is non-0
- Parent/caller process issues stderr warning if Writer exit code is non-zero
#### 5.13.9 Functional Observation
- The classification of delivery failures is highly granular, making it possible to identify at what stage a failure occurred during operation.
- Since silent drop/silent loss is not allowed, all abnormal events will be displayed as a counter or warning.
- Only `unexpected_loss` is distinguished as "bug".
---

### 5.14 `dsafelogger.mp` bounded shutdown and flush strategy
#### 5.14.1 Bounded shutdown contract (v23h, §12.4.1)
`mp.ConfigureLogger()` calls `_mp_shutdown` → `WriterRuntime.stop()` with `atexit`. `stop()` is subject to the following bounded contract:
- `stop(timeout)` waits for `log_thread` / `control_thread` to join for maximum `timeout` seconds (default `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`)
- If the thread is alive after timeout, output a visible warning to stderr (include the stuck thread name and do not make it a silent failure)
- Writer `log_thread` / `control_thread` starts with **`daemon=True`**, so even if stop() fails to complete drain, Python interpreter can exit (process survives principle)
```text
bounded wait (≤ timeout) → visible warning (expose incomplete drain) → process exits
```

#### 5.14.2 Shutdown ordering
Design document §11.21.3:
```text
1. Drain client side async queue
2. Completed sending from client to Writer
3. client sends detach / close
4. Writer side drains log plane queue
5. Writer side closes sink handlers / hash / manifest finalize
6. Writer runtime ends
```

#### 5.14.3 Stop judgment
Design document §11.21.2:
Writer proceeds to shutdown when both of the following conditions are met:
1. Received a stop request from main side
2. The number of active clients must be 0.
The main process's shutdown helper must complete the detachment of its own process client before waiting for the Writer thread to join.
#### 5.14.4 Registry consistency during worker crash
Design document §11.21.2:
- If the worker process terminates without sending `DETACH`, there may be residuals in the Writer's active client registry.
- Set an internal timeout to wait for the number of active clients to be 0 during shutdown
- When timeout is reached, output stderr warning and transition to forced stop
- Avoid silent hangs
- Active survivability detection using periodic liveness probes is a future enhancement and is not a mandatory requirement in the basic design.
#### 5.14.5 flush strategy (v23g, §11.27)
| `writer_flush_batch` | Operation | Assumed use |
|---|---|---|
| `1` (default) | per-message flush. No loss during Writer process crash | High durability requirements |
| `2 – 64` | Flush every N items + idle flush when queue empty. Possibility of loss of up to N-1 items during process crash | Throughput priority |
| `> 64` | Same as above, but with high risk of reduced visibility | Special uses |
Can be overridden with environment variable `{prefix}_WRITER_FLUSH_BATCH`. Warning in `ValueError` and `> 1024` in `<= 0`. `WriterRuntime.__init__` also plays `ctx.writer_flush_batch < 1` as `ValueError` (safety net of `BootstrapContext` direct construction route).
#### 5.14.6 §12.3 Correspondence with terms
Design document §11.27:
- For `writer_flush_batch=1`: dispatch completed = matches `delivered_per_sink`
- For `writer_flush_batch>1`: Set the batch flush completion point to the arrival point of `delivered_per_sink`. **Per-message visibility is not guaranteed once the user opts in**
#### 5.14.7 Responsibility for Sink flush control by Writer
Design document §11.27:
In the multiprocess route, the Configure layer (`_build_writer_sink_groups` of `mp/__init__.py`) sets `stream_flush_on_emit` of the Sink (`AppendOnlyFileHandler`) to `False`, and the Writer (`_mp_runtime.py`) centrally controls batch / per-message.
#### 5.14.8 Functional Observation
- By default, durability is not weakened (`writer_flush_batch=1`).
- Clarify the contract by clearly stating in the specifications that per-message visibility is not guaranteed when opt-in.
- Make "process exits" fail-safe with daemon=True and bounded join.
---

### 5.15 TrackedQueue (v23h)
#### 5.15.1 Design Purpose
Design document §11.16.1:
The implementation of log plane queue uses `TrackedQueue`, which is derived from `multiprocessing.queues.Queue`.
#### 5.15.2 Implementing native qsize fallback
> Automatically fallback to the `multiprocessing.Value` counter only when `super().qsize()` is **exception probed** and `NotImplementedError` is caught in the constructor. Since the determination does not depend on the OS name (such as macOS), it will work correctly even on future or minor unsupported platforms without additional support.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §11.16.1)
#### 5.15.3 Functional observation
- On platforms where `Queue.qsize()` returns `NotImplementedError`, such as macOS, seamlessly switches to providing qsize by `Value` counter.
- Since the determination is based on behavior probes rather than branching based on OS name, portability to future platforms is high.
---

### 5.16 Operation control using environment variables
#### 5.16.1 Complete list of environment variables (reprinted, §2.3.3)
| Environment variable | Purpose | Valid values |
|---|---|---|
| `{prefix}_LEVEL` | Global default level | `DEBUG` ~ `CRITICAL` + registered custom level name |
| `{prefix}_MODULES` | Level/output destination by module | `MOD:LEVEL[,...]` or `MOD:LEVEL:PATH[,...]` |
| `{prefix}_DIAGNOSE` | Diagnostic mode | Valid only for `"1"` |
| `{prefix}_CONSOLE` | Forced console output control | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_COLOR` | Color output forced control | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_CONFIG` | INI file path override | file path |
| `{prefix}_HASH` | Enable hash generation | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_MANIFEST` | Manifest file path override | File path |
| `{prefix}_IPC_LOG_TIMEOUT` | MP version log plane transmission wait time | Positive floating point seconds |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` | MP version log plane queue capacity | Positive integer |
| `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` | MP version process-local async queue capacity | Positive integer |
| `{prefix}_WRITER_FLUSH_BATCH` | MP version Writer flush batch size | Positive integer |
| `NO_COLOR` | Forced disable color output | If set (industry standard, `env_prefix` not affected) |
#### 5.16.2 Static reflection principle
Design document §4 Beginning:
> The environment variables in this chapter are not dynamically reflected during process operation. For the changes to take effect, the target process must be restarted, or there must be an initialization path where `ConfigureLogger` is re-executed.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §4)
#### 5.16.3 Special terms for each environment variable
| Environment variables | Special terms |
|---|---|
| `{prefix}_LEVEL` | Comma delimiter is an error (message prompting you to migrate to `MODULES`) |
| `{prefix}_MODULES` | Individual `MOD_SPEC` Format violation occurs only in the relevant element stderr Warning + Skip (continues to apply to other elements) |
| `{prefix}_DIAGNOSE` | Valid only for `"1"`. `"true"` etc. are treated as invalid values |
| `{prefix}_CONFIG` | Overwrite not only `config_file` but also `config_dict` |
| `{prefix}_IPC_LOG_TIMEOUT` | Fail-fast in v23h (`ValueError` with uninterpretable value) |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` / `IPC_CLIENT_QUEUE_MAXSIZE` | Same as above |
| `{prefix}_WRITER_FLUSH_BATCH` | Same as above |
| `NO_COLOR` | The only environment variable not affected by `env_prefix` (industry standard) |
#### 5.16.4 Functional Observation
- `NO_COLOR`'s compliance with industry standards shows that this library does not create its own standards, but follows existing standards.
- Fail-fast in v23h has been strengthened in the direction of ``not silently ignoring errors in the interpretation of environment variable values, but explicitly displaying them at startup.''
---

### 5.17 Elaborating INI/dict settings
#### 5.17.1 INI parser implementation policy
Design document §5.6:
- Contains a dedicated extremely small INI loader using the standard library `configparser.ConfigParser(interpolation=None)`
- Does not depend on external libraries (D-Settings, etc.)
- `interpolation=None` eliminates the need for `%` escape (format string can be written directly)
#### 5.17.2 Section Rules
Design document §5.4 / §5.6:
| Section | Use |
|---|---|
| `[global]` | Global settings |
| `[dsafelogger:module_name]` | Settings by module |
| Other unknown sections | stderr warning + ignored |
| `[dsafelogger:]` (Module name empty) | `ValueError` (Fail-Fast) |
#### 5.17.3 Null value handling for optional keys
Design document §5.3:
- `max_count =` (empty value) is treated as the same as "key absent" (`None`)
- Empty values for optional format keys of `fmt =` / `file_fmt =` / `console_fmt =` / `datefmt =` are also treated as "unspecified" and left to normal fallback rules.
#### 5.17.4 Handling unknown keys
Design document §5.3:
- Unknown key in `[global]` section: stderr warning + ignored (unlike type conversion error of existing valid key, does not start or stop)
- Keys with the `color_` prefix are recognized based on patterns (not included in the fixed key list)
#### 5.17.5 String coercion for `config_dict`
Design document §5.7.1:
> All values ​​are string types: All values ​​in the dictionary are specified as strings so that they go through the exact same type conversion/validation pipeline as when reading from an INI file. Passing `int` or `bool` directly will result in `TypeError` (Fail-Fast).
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §5.7.1)
As a result, the code path for type conversion and validation is completely unified regardless of whether you use INI or dict.
#### 5.17.6 Exclusion constraints
Design document §5.7.3:
```python
# OK: config_file only
ConfigureLogger(config_file='./config/logging.ini')

# OK: config_dict only
ConfigureLogger(config_dict={'global': {'default_level': 'DEBUG'}})

# NG: Specify both → ValueError
ConfigureLogger(config_file='./logging.ini', config_dict={'global': {'default_level': 'DEBUG'}})
```

#### 5.17.7 Relationship with `{prefix}_CONFIG`
Design document §5.7.3 / §4.6:
- When setting `{prefix}_CONFIG`, both `config_file` and `config_dict` are overwritten, and the INI file specified by the environment variable is used as the second layer.
- In this case, exclusive checking of `config_file` and `config_dict` is not performed (because environment variables take precedence over everything)
#### 5.17.8 Functional Observation
- Since INI and dict are designed to go through the same validation pipeline, there is no room for users to misunderstand that ``dict may result in type conversion.''
- `interpolation=None` allows format strings such as `%(asctime)s` to be written without escaping `%%`.
---

### 5.18 CLI tool `dsafelogger`
#### 5.18.1 3 Commands Provided (Reprinted, §3.6)
Design document §8 and detailed design document §13:
| Command | Role |
|---|---|
| `dsafelogger init` | Output INI configuration file template to standard output |
| `dsafelogger ls [log_dir]` | Parse and list D-SafeLogger files in the specified directory |
| `dsafelogger tail -f <log_dir> <pg_name> [options]` | Automatically determines and follows the latest log file of the specified program |
#### 5.18.2 Omitting hyphens in command names
Design document §8.1: Adopted PyPI package name `dsafelogger` by removing the hyphen from `d-safelogger`. Naming decisions that give priority to omitting hyphens when typing in the shell.
#### 5.18.3 init standard output model
Design document §8.1.1:
```bash
# Generate template and save to file
dsafelogger init > ./config/logging.ini

# Check the contents before saving
dsafelogger init | less
```

A design that allows users to freely control the save destination using shell redirection without taking a file path as an argument.
#### 5.18.4 Tail transparent file switching
Design document §8.1:
> Transparent file tracking: Even if the source application changes files due to log ``day crossing'' during output, the CLI dynamically detects this and transparently replaces the `tail` destination with the new file and continues outputting.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §8.1)
This is a design decision to compensate for the operational weakness of the Append-Only model (`tail -f app.log` does not hold) on the CLI side.
#### 5.18.5 Functional Observation
- The CLI is included in the main unit and is not distributed as a separate package.
- `init`'s redirect premise model eliminates interactive processing such as overwriting confirmation.
- Lower the operational hurdles for Append-Only by transparently following `tail`.
---

### 5.19 Free-threaded support
#### 5.19.1 Design Purpose
Design document §1 / §2:
- In addition to the normal build, include **free-threaded build** for Python 3.13 or higher in the design target.
- The implementation does not depend on the 3.14-specific API and uses a method that can be unified in 3.11+.
#### 5.19.2 Explicit locking of shared state
Design document §2 / §9.2:
> The shared states of `_configure_state`, `_active_pipeline`, `_active_workers`, `_custom_levels`, etc. are protected by explicit locking without assuming the existence of GIL. Does not depend on implementation-dependent atomicity of `list` / `dict`.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §2)
#### 5.19.3 cross-thread safety
Design document §9.4:
> In a free-threaded build, a `f_locals` live reference to frame of another running thread is unsafe. Therefore, when a hand-off across queues occurs, the traceback and `f_locals` are converted to a **safe masked, repr-converted snapshot** on the producer thread side, and no live reference is made on the consumer thread side.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §9.4)
#### 5.19.4 thread boundary semantics
Design document §9.5:
- Initial context inheritance to new user-generated threads follows Python specifications
- The internal thread created by D-SafeLogger always starts with empty `Context` → Prevents context from leaking to the internal thread
#### 5.19.5 Enhanced concurrency safety (v21)
Design document §2 v21 revised:
- Execute the entire `ConfigureLogger` initialization process (`_do_configure()`) while retaining `_lifecycle_lock`
- `GetLogger` detects `'configuring'` state and waits for lock structure
- Eliminate double lock overhead by abolishing the independent `self._lock` of `AppendOnlyFileHandler` and unifying it with the lock API (`self.acquire()/release()`) of the parent class `logging.Handler`
#### 5.19.6 Functional Observation
- Structurally eliminates shared state destruction in free-threaded builds by using an explicit locking design that does not assume the existence of GIL.
- Eliminate the risk of live reference to other thread frames in free-threaded build by making `f_locals` a masked, repr-converted snapshot.
- Eliminate accidents where the user's request context is leaked to the internal thread by starting an empty Context in the internal thread.
---

### 5.20 diagnose (variable automatic expansion)
#### 5.20.1 Functional specifications
Design document §9.4:
- Valid only when `{prefix}_DIAGNOSE=1` environment variable is set
- A dedicated formatter is applied to the exception log and `f_locals` is expanded and recorded.
- In case of `structured=True` and `{prefix}_DIAGNOSE=1`, `f_locals` information is included and output as `locals` field of JSON object
#### 5.20.2 Sanctuaryization (reposted, §4.4.1)
- Settings from INI are ignored (no warning or error is issued, just an invalid key)
- Does not exist as an argument for `ConfigureLogger()`
- Only `"1"` is a valid value (`"true"` / `"yes"` / `"True"` etc. are invalid)
#### 5.20.3 lazy path
Design document §9.3 / §9.4:
- Heavy `repr()` expansion for diagnose is executed on the producer thread side only when `diagnose=True` and `exc_info` are present.
- Lightweight hand-off of copy + context snapshot in normal logs
#### 5.20.4 Suppressing huge reprs
Design document §9.4:
- Individual local variables `repr()` are truncated at a fixed length
- Even if `repr()` itself fails, the entire diagnostic log is not destroyed and the failure is output as a placeholder.
#### 5.20.5 Fallback Rules
Design document §9.4:
formatter falls back in the following order:
1. Use queue hand-off diagnostic snapshot if available
2. Live reference is allowed only if `exc_info` is held within the same thread
3. Otherwise output only standard traceback
#### 5.20.6 Functional Observation
- The diagnostic function is positioned as an ``operation tool during production'' rather than a ``useful function during development'' (only environment variables enabled, intentional operation by the operator).
- repr Defensive implementation against failures and large objects.
- Maintains safety in a free-threaded environment because hand-off is performed using masked, repr-converted snapshots even via async/multiprocess.
---

### 5.21 sens_kws masking
#### 5.21.1 Functional specifications (reposted, §4.4)
Design document §9.4:
- When expanding `f_locals`, values that include sensitive words in variable names are replaced with `*** MASKED ***`.
- Built-in 12 words: `password`, `passwd`, `pass`, `secret`, `token`, `key`, `api_key`, `apikey`, `auth`, `credential`, `private`, `cert`
- Partial match (case does not matter)
#### 5.21.2 Customization
| Setting method | Operation |
|---|---|
| `sens_kws=['ssn', 'credit_card']` (additional) | 12 built-in words + additional words |
| `sens_kws=['ssn'], sens_kws_replace=True` (replacement) | Built-in discard, specified word only |
#### 5.21.3 Incompatibility from environment variables
Design document §3.4:
> `sens_kws` / `sens_kws_replace` intentionally does not support settings from environment variables. This is treated as a "sanctuary" similar to `diagnose`, and is a design decision to prevent unintended changes to sensitive keywords.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §3.4)
#### 5.21.4 Masking Scope (Reposted, §4.4.6)
`examples/09_debugging_production.md`:
Masking works on **`f_locals` route only**. The following are not eligible:
- Message body such as `logger.info(...)`
- `extra=...` / `contextualize()` / Fields added in structured JSON output
- Normal logging when `D_LOG_DIAGNOSE` is off
#### 5.21.5 Functional Observation
- Masking function is only for diagnose mode (does not work with normal logs).
- The premise is that the operation pattern is "Secrets are stored not in the message body, but in variable names that match the masking rules."
- Structurally eliminates unintended changes to keywords during production by making them sanctuaries from environment variables.
---

### 5.22 Summary by function
The materials reviewed in this chapter can be summarized as follows.
1. **Append-Only routing has 9 modes**: `none` / `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / `cyclic_weekday` / `cyclic_month`. Suffix rules and switching triggers are uniformly implemented via the `RoutingStrategy` abstract base class.
2. **The purpose of size / count is different depending on whether max_count is present**: Specified = cyclic overwrite (disk full prevention), not specified = app stops when the limit is reached `OverflowError` (strict system). A design decision that "prevents capacity design mistakes from continuing to run."
3. **min_interval must be an integer evenly dividing 60**: A constraint that only accepts `{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}` and guarantees switching timing that is on the hour.
4. **Generation management is represented by `backup_count`, deletion/compression can be switched independently by archive_mode**: `Fire-and-Forget` Separate thread + self-repairability (retry at next switching timing).
5. **Maintenance of the same family is serialized**: Prohibits parallel execution in units of `directory + pg_name`. Eliminate duplicate deletion, duplicate zipping, and conflict warnings.
6. **`pg_name` filename filtering is exact match**: Only applies to `{pg_name}.log` or `{pg_name}_{suffix}.log`. Structurally eliminates false matches (file deletion from another app) due to prefix matches.
7. **External rotation coexistence only in `routing_mode='none'`**: Reject the coexistence of internal routing and external rotation in `ValueError` and clarify the responsibility boundaries.
8. **Integrity verification is SHA-256 + chunk 64KB read + `os.replace()` atomic write**: Only standard library `hashlib` is used (zero-dep maintained), sidecar write is atomic.
9. **Manifest addition is serialized by key unit lock, lock ordering is `family_lock → manifest_lock`**: Deadlock avoidance rules are specified in the design.
10. **HashWorker runs on `_run_in_empty_context`**: Guaranteed not to inherit parent's context. Consistent with the empty Context start principle for internal threads.
11. **Formatter has 4 variants + per-sink configuration**: `DSafeFormatter` / `StructuredFormatter` / `DiagnosticFormatter` / `DiagnosticStructuredFormatter`, plus `file_fmt` / `console_fmt`. In the multiprocess version, the allow-list representation is normalized to a `kind + constructor args` specification.
12. **`structured=True` and `fmt`/`file_fmt`/`console_fmt` string specifications are exclusive**: `ValueError` when specified simultaneously (avoids semantic conflict due to double implementation of the same function).
13. **`contextualize()` is O(1) pass-by-reference based on `MappingProxyType`**: mutable values ​​fail-fast reject. `hasattr` base fallback aligns with `_ds_context` residency convention at IPC boundaries.
14. **`register_level()` is limited before `ConfigureLogger`, built-in 5 stages are inviolable**: identical definition of spawn re-import is idempotent no-op, mismatch is `RuntimeError`.
15. **Color palette is for INI/dict only (cannot be set with environment variables/arguments)**: Merge order is in 3 stages: `built-in → register_level → INI`. For `color_{abbreviation}`, unknown abbreviations and illegal characters in the key produce warning + skip.
16. **Semantics of `is_async=True` applies consistently to root and module-specific path (v21)**: All Transports are structurally stopped at `Pipeline.module_transports`.
17. **5 State Life Cycle + `RLock`**: `unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`. Rollback in case of exception is guaranteed with `try/finally`.
18. **`dsafelogger.mp` maintains Capture / Transport / Sink 3 layers**: There is a written rule that does not re-execute Capture semantics (logger layer evaluation, level judgment, `f_locals` collection) on the Writer side.
19. **log plane / control plane is completely separated, reply path is per-request pipe**: Queue-in-Queue method is not adopted due to Python `multiprocessing` restrictions.
20. **Delivery status is classified into 7 layers + writer_reject 6 breakdown**: Silent loss only `unexpected_loss` is treated as a bug. The rest can be explained as coming from policy. Rate-limited stderr warning for all.
21. **bounded shutdown is protected by four internal constants**: `MAX_IPC_LOG_TIMEOUT_SECONDS=3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC=5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC=10.0` / `ipc_log_queue_maxsize` warning threshold 100000.
22. **`writer_flush_batch=1` (default) specifies per-message visibility, `>=2` opt-in specifies visibility expiration**: A contract that does not weaken durability by default.
23. **Native qsize fallback of TrackedQueue is OS name independent**: Determined by exception probe of `super().qsize()`. Portability to future platforms.
24. **Environment variables are statically reflected only**: They are not dynamically reflected while the process is running (`ConfigureLogger` requires re-execution). Only `NO_COLOR` is unaffected by `env_prefix` as the industry standard.
25. **INI / `config_dict` pass through the same validation pipeline**: All values ​​of `config_dict` must be strings (`int` / `bool`, direct specification is `TypeError`).
26. **CLI 3 commands complement the operation of Append-Only models**: Standard output model of `init`, transparent file switching of `tail`.
27. **Free-threaded support is GIL independent explicit lock + repr snapshot**: Explicit lock protection on shared state, repr snapshot of `f_locals` in producer thread, internal thread starts with empty Context.
28. **diagnose / sens_kws / file_fmt / console_fmt cannot be set as environment variables (sanctuary)**: Specify each reason in the design document.
---

### 5.23 Summary of this chapter
D-SafeLogger v23k features can be organized into five feature categories:
1. **File I/O system**: 9 types of Append-Only routing / generation management + archive / external rotation coexistence / SHA-256 integrity verification. Architecturally avoids Windows file locking issues and integrates with audit workflows with `sha256sum -c` compatibility.
2. **Log generation/display system**: 4 Formatter variants / `file_fmt` / `console_fmt` per-sink configuration / `contextualize` (FrozenContext) / `register_level` / color palette / diagnose / sens_kws masking. `LogRecord` maintains stdlib compatibility through non-destructive handling and display proxies.
3. **Concurrent/asynchronous system**: `is_async` (QueueTransport) / 5-state life cycle / free-threaded support / start empty Context of internal thread / `_lifecycle_lock` (RLock). Protect shared state with GIL-independent explicit locks.
4. **Multiprocess system**: Writer runtime / `ctx` bootstrap / log plane and control plane / classified delivery-state counters / six `writer_reject` subcategories / bounded shutdown / flush strategy / TrackedQueue / registry hash matching / active client registry. Silent loss is structurally disallowed.
5. **Configuration/operation system**: 3-layer pipeline (env > INI/dict > arguments) / 13 types of environment variables / `NO_COLOR` industry standard / CLI 3 commands (`init` / `ls` / `tail -f`) / 13 types of examples. Assign a layer to each subject of change, and use the CLI to supplement the operation of the Append-Only model.
All of these functional groups map to the five design themes identified in §1.3: “do not depend,” “do not break,” “do not degrade silently,” “make failures explainable,” and “extend but do not replace.” This confirms the connection between the design concepts extracted in Chapter 1 and their feature-level implementation.
---

> **Main reference materials for this chapter**: `docs/design/D_SafeLogger_Specification_v23k_full.md` §1, §2, §3, §4, §5, §6, §7, §8, §9, §10, §11, §12 / `docs/design/D-SafeLogger_DetailedDesign_v23k.md` §1, §2, §4, §5, §6, §7, §8, §11, §12, §13, §14, §15, §15a, §16, §17, §18, §19 / `docs/api/dsafelogger*.md` / `src/dsafelogger/` Module configuration / `examples/01_*.md`~`examples/17_*.md`
> This document is intended to explain and evaluate the current v23k architecture, and does not include improvement proposals, issue management, or future roadmaps.
## Chapter 6 Competitive Project Comparison
### 6.1 Chapter 6 Scope and Policy
#### 6.1.1 Comparison target
In this chapter, we will identify the following eight major logging libraries that can be selected as candidates for modern Python applications, confirm the specifications using the primary source, and then organize the differences with D-SafeLogger v23k.
| # | Project | Obtain PyPI version | Primary source verification date |
|---|---|---|---|
| 1 | **stdlib `logging`** | Python 3.14 (official docs) | 2026-05-09 |
| 2 | **Loguru** | 0.7.3 (2024-12-06 release) | 2026-05-09 |
| 3 | **structlog** | 25.5.0 (2025-10-27 release) | 2026-05-09 |
| 4 | **picologging** (Microsoft) | 0.9.3 (PyPI metadata) / 0.9.4 (GitHub release 2024-09-13) | 2026-05-09 |
| 5 | **Eliot** | 1.18.0 (2026-05-07 release) | 2026-05-09 |
| 6 | **Logbook** | 1.9.2 | 2026-05-09 |
| 7 | **logfire** (Pydantic) | 4.32.1 | 2026-05-09 |
| 8 | **OpenTelemetry Python SDK (Logs)** | opentelemetry-sdk 1.41.1 | 2026-05-09 |
#### 6.1.2 Comparison axis
Compare each library on the following nine axes based on the architectural characteristics of D-SafeLogger v23k.
| Axis | Perspective |
|---|---|
| Runtime external dependencies | Number of supply chain routes |
| Relationship with stdlib `logging` | drop-in expansion / parallel running / replacement / OTel bridge |
| File output/routing | rename method / append-only / external rotation coexistence |
| Structured log context management | JSON / contextvars / processor chain |
| Multiprocess support | enqueue / parent Writer / delivery status |
| Integrity verification / Audit function | SHA-256 / Manifest / Tampering detection |
| Free-threaded Python support | PEP 703 support |
| Observability of delivery status | counters / classification / shutdown summary |
| Configuration management pipeline | env / INI / arguments |
#### 6.1.3 Evaluation policy
- **Factual sources**: Include direct excerpts from each project's PyPI / GitHub / official docs / PEP in a footnote or in the text.
- **Elimination of subjective evaluations**: Do not include subjective evaluations such as "fast/slow" or "popular/unpopular." Numerical values ​​such as GitHub stars are cited as fact, but they are not used to judge superiority or inferiority.
- **Clarification of differences in responsibility axes**: In the comparison table, distinguish between `—`, which means "not provided", and `out`, which means "outside the scope of responsibility" (OTel does not handle file rotation because it is not "unimplemented" but "outside the scope of responsibility").
---

### 6.2 Checking the primary source of comparison projects
#### 6.2.1 stdlib `logging` (Python 3.14)
**Source**: `docs.python.org/3/library/logging.html`, `docs.python.org/3/library/logging.handlers.html`, `docs.python.org/3/howto/logging-cookbook.html`, PEP 282, Python 3.13 What's New.
Key facts:
- 4 component configuration: `Logger` / `Handler` / `Filter` / `Formatter`
- `RotatingFileHandler` and `TimedRotatingFileHandler` are rotated using **rename method**
- `WatchedFileHandler` is officially marked as "not suitable for Windows":
  > "This handler is not appropriate for use under Windows, because under Windows open log files cannot be moved or renamed - logging opens the files with exclusive locks."
  > (`docs.python.org/3/library/logging.handlers.html` WatchedFileHandler section)
- The official stance on multiprocessing is as follows:
  > "Although logging is thread-safe, and logging to a single file from multiple threads in a single process is supported, logging to a single file from multiple processes is not supported, because there is no standard way to serialize access to a single file across multiple processes in Python."
  > (`docs.python.org/3/howto/logging-cookbook.html`)
- Recommended pattern: Operate `QueueHandler` + `QueueListener` in a separate process or send to listener via `SocketHandler`.
- There are no changes to the `logging` module itself in Python 3.13. Free-threaded build has an impact on another axis.
#### 6.2.2 Loguru 0.7.3
**Source**: `pypi.org/pypi/loguru/json`, `github.com/Delgan/loguru`, `loguru.readthedocs.io`.
Key facts:
- License: MIT
- Python requirement: `>=3.5, <4.0`
- Runtime dependencies: `colorama>=0.3.4` (Windows only), `aiocontextvars>=0.2.0` (Python <3.7), `win32-setctime>=1.0.0` (Windows only)
- Latest release: 0.7.3 (2024-12-06)
- GitHub stars: 23.9k (as of 2026-05-09)
- Self-assertion: "Python logging made (stupidly) simple"
- Features: thread-safe / multiprocess-safe by `enqueue=True`, async logging in coroutine sink, file rotation (size/time), retention, compression, JSON, `@logger.catch`, `diagnose=True`
- Marketing claim: "10x faster than standard Python logging"
#### 6.2.3 structlog 25.5.0
**Source**: `pypi.org/pypi/structlog/json`, `www.structlog.org`, `github.com/hynek/structlog`.
Key facts:
- License: MIT OR Apache-2.0
- Python requirement: `>=3.8`
- Runtime dependency: `typing-extensions` (Python <3.11 only)
- Latest release: 25.5.0 (2025-10-27)
- Assertion: "Simple. Powerful. Fast. Pick three."
- Positioning: Do not replace stdlib `logging`, work independently or **forward** to stdlib (from official docs)
- Features: processor chains, context construction using `bind()`, native support for `contextvars`, JSON / logfmt / colored console
- Official docs **no mention of file rotation, integrity verification, and multi-process specialization functions**
#### 6.2.4 picologging 0.9.3 / 0.9.4
**Source**: `pypi.org/pypi/picologging/json`, `github.com/microsoft/picologging`, `microsoft.github.io/picologging/`.
Key facts:
- License: MIT
- Python requirement: `>=3.7`
- Runtime dependencies: None (dev extras only)
- Development status: Beta (PyPI classifier `Development Status :: 4 - Beta`)
- Latest GitHub release: 0.9.4 (2024-09-13)
- Provided by: Microsoft
- Claim: drop-in replacement for stdlib `logging`, 4–10x (up to 17x repository README) speedup achieved with C extension
- Official repository clearly states "This project is in beta. There are some incomplete features."
- **No mention of free-threaded (No-GIL) support is observed in GitHub README or official docs** (as of 2026-05-09)
#### 6.2.5 Eliot 1.18.0
**Source**: `pypi.org/pypi/eliot/json`, `eliot.readthedocs.io`, `github.com/itamarst/eliot`.
Key facts:
- License: Apache 2.0
- Python requirement: `>=3.10.0`
- Runtime dependencies: `zope.interface`, `pyrsistent (>=0.11.8)`, `boltons (>=19.0.1)`, `orjson` (CPython only)
- Latest release: 1.18.0 (2026-05-07)
- Assertion: "Logging library that tells you why it happened"
- Positioning: causal action chain. A model where actions spawn other actions and are completed with success/fail.
- Integration with stdlib `logging` (Integrating and Migrating Existing Logging section)
- Supports async (asyncio/Trio/Twisted). Spanning Processes and Threads documentation included
#### 6.2.6 Logbook 1.9.2
**Source**: `pypi.org/pypi/Logbook/json`, `logbook.readthedocs.io`, `github.com/getlogbook/logbook`.
Key facts:
- License: BSD-3-Clause
- Python requirement: `>=3.9`
- Runtime dependencies: `typing-extensions>=4.14.0`
- Claim: "A logging replacement for Python"
- Features: Many Handler types (StreamHandler / file-based / ticketing), Stack-based architecture, Custom processors, stdlib logging compatibility, queue support
- The documentation itself notes "Feedback is appreciated. The docs here only show a tiny, tiny feature set and can be incomplete."
#### 6.2.7 logfire 4.32.1 (Pydantic)
**Source**: `pypi.org/pypi/logfire/json`, `github.com/pydantic/logfire`, `pydantic.dev/docs/logfire/`.
Key facts:
- License: MIT
- Python requirement: `>=3.9`
- Runtime dependencies: 8 packages (`executing`, `opentelemetry-exporter-otlp-proto-http<1.41.0,>=1.39.0`, `opentelemetry-instrumentation>=0.41b0`, `opentelemetry-sdk<1.41.0,>=1.39.0`, `protobuf>=4.23.4`, `rich>=13.4.2`, `tomli>=2.0.1` (Python <3.11), `typing-extensions>=4.1.0`)
- Assertion: "An observability platform built on the same belief as our open source library — that the most powerful tools can be easy to use."
- Positioning: **Hosted SaaS observability platform** (SDK is OSS, UI and backend are proprietary. "Logfire SDKs are open source, and you can use them to export data to any OTel-compatible backend")
- Enterprise self-host is a paid license
- OTel compatible + Python-centric (FastAPI / Pydantic integration / LLM telemetry)
#### 6.2.8 OpenTelemetry Python SDK 1.41.1
**Source**: `pypi.org/pypi/opentelemetry-sdk/json`, `opentelemetry.io/docs/specs/otel/logs/`, `opentelemetry.io/docs/languages/python/instrumentation/`, `github.com/open-telemetry/opentelemetry-python`.
Key facts:
- License: Apache-2.0
- Python requirement: `>=3.9`
- Runtime dependencies: `opentelemetry-api==1.41.1`, `opentelemetry-semantic-conventions==0.62b1`, `typing-extensions>=4.5.0`
- Official logs specification (`opentelemetry.io/docs/specs/otel/logs/`) policy:
  > "We embrace existing logging solutions and make sure OpenTelemetry works nicely with existing logging libraries."
  > (OpenTelemetry Logs Specification)
- Python integration: Bridge method to register `LoggingHandler` as handler of stdlib `logging`. Convert logs via stdlib to OTel log records with `logging.basicConfig(handlers=[handler], level=logging.INFO)`.
- File output/rotation/integrity verification is **outside the scope of responsibility** (specialized in emission/export)
#### 6.2.9 PEP 703 / Free-threaded Python status
**Source**: `peps.python.org/pep-0703/`, `docs.python.org/3/whatsnew/3.13.html`.
Key facts:
- PEP 703 **Accepted on 2023-10-24**
- Target: Python 3.13+ (`--disable-gil` build flag)
- Rollout policy: "the rollout be gradual and break as little as possible, and that we can roll back any changes that turn out to be too disruptive."
- Implications: Libraries with shared mutable state that implicitly depend on the GIL require explicit locking. Cannot rely on implicit thread safety of `list` / `dict`.
- Runtime control: `PYTHON_GIL` environment variable, `Py_mod_gil` module slot
---

### 6.3 Axis 1: Runtime external dependencies
Organize the number of runtime external dependencies (packages installed at the same time during installation) for each project from the primary source (PyPI metadata).
| Project | Number of runtime dependencies | Breakdown |
|---|---:|---|
| **D-SafeLogger v23k** | **0** | None (standard library only) |
| stdlib `logging` | 0 | (Python standard library itself) |
| Loguru 0.7.3 | 3 (conditional) | `colorama` (Windows), `aiocontextvars` (<3.7), `win32-setctime` (Windows) |
| structlog 25.5.0 | 1 (conditional) | `typing-extensions` (<3.11) |
| picologging 0.9.3 | 0 | None |
| Eliot 1.18.0 | 4 | `zope.interface`, `pyrsistent`, `boltons`, `orjson` |
| Logbook 1.9.2 | 1 | `typing-extensions>=4.14.0` |
| logfire 4.32.1 | 8 | OpenTelemetry series 3, `executing`, `protobuf`, `rich`, `tomli` (<3.11), `typing-extensions` |
| OpenTelemetry SDK 1.41.1 | 3 | `opentelemetry-api`, `opentelemetry-semantic-conventions`, `typing-extensions` |
#### 6.3.1 Observed facts
- **Completely zero dependencies (0 including conditionals)** In the scope of this primary source investigation, there are only two cases: D-SafeLogger and picologging.
- `typing-extensions` dependency of structlog/Logbook is **conditional** (old Python only).
- Loguru's Windows-only dependencies (`colorama` / `win32-setctime`) are installed as entities only on Windows.
- logfire's 8 dependencies have a structure that involves the entire OpenTelemetry stack, and the breadth of the supply chain stands out compared to other projects.
#### 6.3.2 Uniqueness of D-SafeLogger
D-SafeLogger's design document §1 declares **zero runtime external dependencies as an "absolute condition"**, and zero dependencies are operated as a constraint on the entire architecture rather than a judgment on individual functions (§4.2.1). The Vendor-Agnostic principle also structurally excludes vendor-specific imports from core modules (§4.2.2). picologging has zero dependencies, but since it is **based on C extensions**, there is an indirect dependence on `cibuildwheel` / native build chain (it is hidden by the wheel distribution from PyPI, but appears when doing a source build).
---

### 6.4 Axis 2: Relationship with stdlib `logging`
Organize the position of each library relative to stdlib `logging`.
| Project | Stance | Observation basis |
|---|---|---|
| **D-SafeLogger** | **drop-in extension** (returns `DSafeLogger` with `logging.setLoggerClass()`) | Design document §2, §9.2 |
| stdlib `logging` | (standard) | — |
| Loguru | **Replace** (your own `logger` singleton) | Loguru README "One and only one logger" |
| structlog | **Parallel running or forward** (independent operation or forwarding to stdlib) | structlog official docs |
| picologging | **drop-in replacement** (same API, faster with C extension) | picologging README "drop-in replacement" |
| Eliot | **Parallel running** (with integration with stdlib) | Eliot docs "Integrating and Migrating Existing Logging" |
| Logbook | **Replacement** (stdlib compatible handler is provided) | Logbook docs |
| logfire | **OTel Bridge** (convert stdlib logging to OTel) | logfire docs / OTel LoggingHandler |
| OpenTelemetry Python | **OTel Bridge** (Convert stdlib to OTel with `LoggingHandler`) | OTel Python instrumentation docs |
#### 6.4.1 Observed facts
- Both D-SafeLogger and picologging claim "drop-in compatibility with stdlib `logging`", but **different purposes**:
  - D-SafeLogger: Add **design differentiation** such as append-only routing, integrity verification, multiprocess Writer, etc.
  - picologging: Keep the same API **Speed up with C extensions** (functionality is equivalent to stdlib)
- Loguru/Logbook is intended for **replacement** with its own singleton/handler. Existing `logger.info()` call sites need to be rewritten (or adapter) when replacing.
- structlog is responsible for the **front end** (assembling the event dictionary), and output can also be forwarded to stdlib.
- logfire / OpenTelemetry is an **emission bridge** that provides a route for forwarding stdlib logging logs to OTLP.
#### 6.4.2 Uniqueness of D-SafeLogger
D-SafeLogger calls `logging.setLoggerClass()` inside `ConfigureLogger()`, and third-party libraries that use `logging.getLogger()` such as SQLAlchemy / Django also use this library's configuration flow without modification. This is equivalent to picologging, but D-SafeLogger additionally provides append-only / integrity verification / multiprocess Writer. Unlike the Loguru/Logbook replacement type, it does not change the existing `logger.info()` call site (`examples/03_migration_from_stdlib.md`, §3.7).
---

### 6.5 Axis 3: File output/routing
| Project | rename method / append-only | external rotation coexistence |
|---|---|---|
| **D-SafeLogger** | **append-only** (does not rename) | Officially supported with `routing_mode='none'` + `ReopenLogFiles()` |
| stdlib `logging` | **rename method** (RotatingFileHandler / TimedRotatingFileHandler) | `WatchedFileHandler` (Windows not available) |
| Loguru | With rotation (rename based) | No official API for external rotation coexistence is observed in the functional documentation |
| structlog | Forward file output to stdlib | (depends on stdlib) |
| picologging | stdlib compatible (rename method) | (depends on stdlib) |
| Eliot | File output is mainly via external connection | — |
| Logbook | With rotation | — |
| logfire | **Out of scope of responsibility** (via OTel exporter) | out |
| OpenTelemetry Python | **Out of scope of responsibility** (emission only) | out |
#### 6.5.1 Observation: OS-specific failure modes of rename-based rotation
`docs.python.org/3/library/logging.handlers.html` specifies the following constraints:
> "This handler is not appropriate for use under Windows, because under Windows open log files cannot be moved or renamed - logging opens the files with exclusive locks - and so there is no need for such a handler."
> (Python official docs `logging.handlers` WatchedFileHandler section)
This is a description of `WatchedFileHandler` (a handler that detects inodes after being renamed by an external rotator), but it is important that the OS restriction itself is clearly stated: ``On Windows, the active log cannot be renamed from another process.''

Rename-based rotation has different failure modes depending on the operating system.

On Windows, as the Python documentation for `WatchedFileHandler` states, active log files cannot reliably be moved or renamed while held open. The rotation operation tends to surface as an immediate file-operation failure.

On POSIX systems, the opposite failure mode is common. `rename()` often succeeds even when the file is open, and existing file descriptors continue to point to the old object. From the external rotator's point of view, rotation can appear successful. As long as the writer holds the old descriptor, however, the logging stream continues flowing to the renamed previous generation rather than the new active file.

In other words, on Windows the rename-based failure is likely to surface as a file-operation failure. On POSIX systems, the filesystem operation can succeed while log output keeps going to the old file. This does not make POSIX inherently safer for active-log generation management; the problem can instead appear later as monitored files receiving no new records, writes into files selected for compression or deletion, unreleased space, or inconsistent generation boundaries during incident review.
#### 6.5.2 Observation: stdlib multiprocess limit
`docs.python.org/3/howto/logging-cookbook.html` specifies:
> "Logging to a single file from multiple processes is not supported, because there is no standard way to serialize access to a single file across multiple processes in Python."
> (Python official logging cookbook)
The official recommended pattern for this is separate process operation of `QueueHandler` + `QueueListener` or via `SocketHandler`.
#### 6.5.3 Uniqueness of D-SafeLogger
D-SafeLogger's append-only routing (design document §7.2) **structurally avoids the OS-specific failure modes of rename-based rotation at the design level**.
> Similar ideas can be seen in specific options such as Logback and Log4j2, but no design with this as the default core exists in the Python ecosystem.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §7.2)
Even within the scope of this primary source investigation (stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OTel), **no projects with append-only routing as the core architecture were observed**. Loguru's rotation function is a general method that involves file rename (section `loguru.readthedocs.io` rotation).
---

### 6.6 Axis 4: Structured Log Context Management
| Projects | Structured Logging | contextvars support | Context Management API |
|---|---|---|---|
| **D-SafeLogger** | JSON Lines with `structured=True` | `ContextVar[MappingProxyType]`(FrozenContext) | `contextualize(**kwargs)` |
| stdlib `logging` | △(`extra=` + custom Formatter) | △(Manual) | `LoggerAdapter` / `extra=` |
| Loguru | ○ (JSON in `serialize=True`) | ○ | `logger.bind()` / `logger.contextualize()` |
| structlog | ◎ (core function, processor chain) | ◎ (`contextvars` native) | `bind()` / `bind_contextvars()` |
| picologging | △ (stdlib compatible) | △ (manual) | `LoggerAdapter` |
| Eliot | ◎(action tree, JSON) | ○(async/contextvars) | `start_action()` |
| Logbook | ○(custom processor) | △ | `Processor` |
| logfire | ◎(OTel attributes) | ○(OTel context) | `with logfire.span()` |
| OpenTelemetry Python | ○(OTel log records, attributes) | ○(OTel context) | `with tracer.start_as_current_span()` |
#### 6.6.1 Observation: Role of structlog
`www.structlog.org` claims:
> "structlog leans on functions that take and return dictionaries hidden behind familiar APIs."
The core of structlog is the **processor chain**, which processes kwargs while binding them to the bound logger. `bind_contextvars()` also provides native support for `contextvars`. Select the output format from JSON / logfmt / colored console.
#### 6.6.2 Observation Fact: Eliot's causal chain
`eliot.readthedocs.io` claims:
> "actions can spawn other actions, and eventually they either succeed or fail. The resulting logs tell you the story of what your software did: what happened, and what caused it."
This is different from general logging, which ``outputs isolated events.'' A design that allows tracing the parent-child relationship of actions.
#### 6.6.3 Uniqueness of D-SafeLogger
`contextualize()` of D-SafeLogger has the following features:
- **O(1) pass by reference** with immutable snapshot by `MappingProxyType` (§5.6.2)
- Fail-Fast rejection of mutable values (§5.6.3)
- Even via multiprocess, snapshots on the Capture side are retained on the Writer side due to the `_ds_context` resident rule (§5.6.7)
structlog's processor chain is a much more powerful front-end feature for structured logging, but it has no ``below the file output boundary'' responsibilities. D-SafeLogger can coexist with structlog (`examples/16_structlog_coexistence.md`, §3.9.1) and is designed so that the responsibility axes do not intersect.
---

### 6.7 Axis 5: Multiprocess support
| Project | Multiprocess capability | Delivery-state observability |
|---|---|---|
| **D-SafeLogger** | `dsafelogger.mp`: parent-side Writer owns file sink, worker sends `LogEvent` via IPC, control plane of `ATTACH`/`DETACH`/`STOP`/`REOPEN`/`STATUS` Separate | 6 layers of `accepted`/`delivered`/`KnownRejected`/`KnownDropped`/`UnexplainedLost`/`partial_delivered` + 6 breakdown of `writer_reject` |
| stdlib `logging` | Officially "multiprocess single file writing is not supported", recommended is separate process operation of QueueHandler + QueueListener | — |
| Loguru | Multiprocess support with `enqueue=True` | — |
| structlog | (depends on stdlib) | — |
| picologging | stdlib compatible | — |
| Eliot | "Spanning Processes and Threads" documentation available | — |
| Logbook | queue support | — |
| logfire | Aggregate to OTel exporter | — |
| OpenTelemetry Python | Aggregate to OTel exporter | — |
#### 6.7.1 Observation Fact: Loguru's `enqueue=True`
Loguru's README clearly states "Thread-safe and multiprocess-safe with enqueue support". Designed to enable multi-process support in `logger.add(..., enqueue=True)`.
#### 6.7.2 Observation: Official recommendation for stdlib
stdlib `logging` is recommended in the official cookbook as follows:
> "When deploying web applications using Gunicorn or uWSGI (or similar), multiple worker processes are created to handle client requests. In such environments, **avoid creating file-based handlers directly in your web application**. Instead, use a `SocketHandler` to log from the web application to a listener in a separate process."
> (Python official logging cookbook)
This is an instruction that says, ``If you are serious about outputting files using multiple processes, create a separate process and send it using socket/queue.'' This is the same direction as D-SafeLogger's `dsafelogger.mp`'s Writer-owned sinks model. The difference is ``Whether or not patterns that the official website recommends for DIY will be provided as a library.''
#### 6.7.3 Uniqueness of D-SafeLogger
The multiprocess functionality of D-SafeLogger has observable differentiation in the following points (§2.8, §5.11–§5.14):
1. **Writer-owned sinks**: File sink, routing, hash, manifest, purge, archive, and reopen are all consolidated in Writer. worker only sends `LogEvent` via IPC.
2. **Complete separation of log plane / control plane**: Normally log and control commands are carried in separate queues, and ACK is per-request `Pipe(duplex=False)` reply path.
3. **7-level classification of delivery status**: In addition to lifecycle of `attempted` / `accepted` / `enqueued` / `delivered_per_sink` / `delivered`, 6 types of terminal states (`rejected` / `dropped` / `writer_reject` / `partial_delivered` / `unexpected_loss` / `writer_best_effort_failures`) + `overload_shed` qualifier.
4. **bounded shutdown contract (v23h)**: Realize "process exits" as fail-safe with bounded join + visible warning + daemon thread for `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0` seconds.
5. **6 breakdown of `writer_reject`** (v23h): route / reconstruct / close_marker / sink / policy / format.
To the scope of this primary source study, no other project has a published specification that categorizes delivery failures with this level of granularity. Loguru's `enqueue=True` provides multi-process secure hand-off, but no hierarchical classification of delivery status counters is observed in the public documentation. OpenTelemetry's log records have retry/queue on the exporter side, but this is not designed to "classify delivery failures" but to "send to OTLP backend".
---

### 6.8 Axis 6: Integrity Verification/Audit Functions
| Project | SHA-256 Sidecar | Manifest | Tamper Detection |
|---|---|---|---|
| **D-SafeLogger** | ◎ (`enable_hash=True`, `sha256sum -c` compatible, relative path) | ◎ (`manifest_path` specification, addition, storage in a separate directory recommended) | Sidecar + manifest inconsistency detection |
| stdlib `logging` | — | — | — |
| Loguru | — | — | — |
| structlog | — | — | — |
| picologging | — | — | — |
| Eliot | — | — | — |
| Logbook | — | — | — |
| logfire | — | — | — |
| OpenTelemetry Python | — | — | — |
#### 6.8.1 Observed facts
Within the scope of this primary source investigation, **D-SafeLogger is the only project that has been observed to provide SHA-256 sidecars or manifest files as library functions**. For Loguru / Logbook / Eliot / structlog / picologging, there is no mention of the integrity verification function in the PyPI summary, GitHub README, or official docs. Since OTel is responsible for "emission/export", file integrity is not its responsibility (external collector/storage side is responsible).
#### 6.8.2 Uniqueness of D-SafeLogger
The integrity verification function of D-SafeLogger has the following characteristics (§4.5, §5.4):
- **`sha256sum -c` compatible format**: Can be verified using OS standard commands (no proprietary verification tools are created)
- **Relative path description**: Verification will not be broken even if the log set is moved to another location
- **File loss detection using manifest**: "File + sidecar deleted together" cannot be detected with sidecar alone, but can be detected with separate directory storage manifest.
- **Atomic write by `os.replace()`**: Avoid the accident where the verification tool refers to the partially written state.
- **HMAC intentionally left out of scope**: to avoid introducing the additional responsibility of key management
This is a result of the design of `examples/08_compliance_audit.md`, which explicitly assumes "audit/compliance (HIPAA/SOC 2/PCI-DSS/FedRAMP)" usage.
---

### 6.9 Axis 7: Free-threaded Python (PEP 703) compatible
PEP 703 **Accepted on 2023-10-24**. Available from Python 3.13 with `--disable-gil` build. Libraries that implicitly depend on the GIL will require explicit locking.
| Project | Mention of free-threaded support |
|---|---|
| **D-SafeLogger** | **Specified as target build in design document §1/§2**. Protect shared state with explicit locks, do not rely on implicit atomicity of `list` / `dict` |
| stdlib `logging` | There are no direct changes to the `logging` module itself in Python 3.13/3.14. The free-threaded build itself is progressing on a separate axis |
| Loguru | No mention of free-threaded support is observed in the official repository, PyPI summary, or docs within the scope of this survey |
| structlog | No mention of free-threaded support in the official docs was observed within the scope of this investigation |
| picologging | C extension base. **No mention of support for `Py_mod_gil` or free-threaded build support is observed in GitHub README or official docs** (as of 2026-05-09) |
| Eliot | No mention of free-threaded support in the docs was observed within the scope of this research |
| Logbook | No mention of free-threaded support in the docs was observed within the scope of this investigation |
| logfire | OTel SDK dependent. Follow the response from OTel Python |
| OpenTelemetry Python | OTel community work in progress. An official declaration that mainstream support for free-threaded build will be supported at the SDK 1.41 level has not been confirmed within the scope of this research. |
#### 6.9.1 Observed facts
`peps.python.org/pep-0703/` and `docs.python.org/3/whatsnew/3.13.html` clarify the following points:
- C extensions must declare GIL compatibility in the `Py_mod_gil` module slot
- Python-level libraries that rely on `list` / `dict` implicit thread safety also need to introduce explicit locking.
- "the rollout be gradual and break as little as possible"
For pure Python libraries (structlog / Logbook / Loguru / Eliot, etc.), ``if you change the implementation, it will work in free-threaded'', but **In the scope of this primary source investigation, D-SafeLogger is the only case observed in which the library consciously declares free-threaded as the design target**.
Since picologging is based on C extension, `Py_mod_gil` compatibility is required, but there is no declaration of compatibility in the current GitHub README (the latest release is 2024-09-13, after PEP 703 Accepted).
#### 6.9.2 Uniqueness of D-SafeLogger
Design document §1 specifies:
>In addition to the normal build, include **free-threaded build for Python 3.13 or higher** in the design target. However, the implementation does not depend on the 3.14-specific API, and uses a method that can be unified with 3.11+.
> (`docs/design/D_SafeLogger_Specification_v23k_full.md` §1)
Design document §2 / §9.2 / §9.4 / §9.5 stipulates explicit locking of shared state, implicit atomicity independence of `list` / `dict`, reprized snapshot of `f_locals`, and empty Context start of internal threads at the specification level. This is consistent with PEP 703's "explicit locking required" requirement.
`TESTING.md` documents the following manual test command for free-threaded builds:
```bash
PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v
```

Free-threaded builds are included in the design target, and a manual test procedure is documented. The normal GitHub Actions matrix targets regular CPython 3.11-3.14 builds.
---

### 6.10 Axis 8: Observability of delivery status (reposted, §6.7.3)
This is organized as an axis specific to **D-SafeLogger**. To the extent of this primary source research, no other project has a published specification that categorizes delivery failures at this level of granularity.
Delivery status hierarchy for D-SafeLogger (§5.13):
```text
Lifecycle: attempted → accepted → enqueued → delivered_per_sink → delivered
Terminal: rejected | dropped | writer_reject | partial_delivered | unexpected_loss | writer_best_effort_failures
Qualifier: overload_shed
```

`writer_reject` 6 Breakdown: `writer_route_reject` / `writer_reconstruct_reject` / `writer_close_marker_reject` / `writer_sink_reject` / `writer_policy_reject` / `writer_format_reject` (v23h).
All are assigned a dedicated counter and stderr warning (rate-limited) and aggregated into a shutdown summary (§4.7).
#### 6.10.1 Contrast with stdlib
There is no official counter in stdlib `logging` that distinguishes between delivery failures. `Handler.handleError()` handles errors in the handler, but this only outputs a traceback to stderr (`docs.python.org/3/library/logging.html` Handler.handleError). Control of `logging.raiseExceptions` flag is similar, and classification and recording of delivery failures is not provided.
#### 6.10.2 Comparison with OTel exporter
OpenTelemetry Python's `BatchLogRecordProcessor` has a queue + retry / drop behavior, but this is a retry queue for "finally delivering to the OTLP backend" and is not designed to "classify delivery failures as policy-based/bug-based" like this library.
---

### 6.11 Axis 9: Configuration Management Pipeline
| Project | Environment variables | INI / dict | Arguments | Clarifying merge rules |
|---|---|---|---|---|
| **D-SafeLogger** | ◎ (`{prefix}_*` 13 types, `NO_COLOR` industry standard) | ◎ (INI and `config_dict`, same validation pipeline) | ◎ (26 arguments, Fail-Fast) | ◎ (Environment variables > INI/dict > Strict merging of arguments is clearly stated in design document §3) |
| stdlib `logging` | △ (Limited support for `LOGLEVEL`, `PYTHONLOGGING`, etc. of `logging.basicConfig()`) | ○ (`fileConfig` / `dictConfig`) | ○ | △ (No systemization of merge rules) |
| Loguru | △ (individual env interpretation) | △ | ◎ (argument of `logger.add()`) | △ |
| structlog | △ | △(`structlog.configure()`) | ◎ | △ |
| picologging | stdlib compatible | stdlib compatible | stdlib compatible | stdlib dependent |
| Eliot | △ | △ | ◎ | △ |
| Logbook | △ | ○ | ◎ | △ |
| logfire | OTel environment variables | logfire `pyproject.toml` settings | ◎ | OTel/logfire unique |
| OpenTelemetry Python | OTel standard environment variable (`OTEL_*`) | △ | ◎ | Depends on OTel spec |
#### 6.11.1 Observed facts
Although `dictConfig` / `fileConfig` of stdlib `logging` is powerful, **Instances where the library provides systematic merging rules for ``environment variables > INI > arguments'' are not observed other than D-SafeLogger in the scope of this investigation.
OTel's `OTEL_*` environment variables exist extensively as part of the OpenTelemetry specification, but these are "settings for the OTel SDK" and are not intended to build a three-layer pipeline with stdlib logging.
#### 6.11.2 Uniqueness of D-SafeLogger
D-SafeLogger's three-layer pipeline has observable differentiation in the following aspects (§3.3, §5.16, §5.17):
- Clarify the strict overwriting order of **Environment variables > INI/dict > Arguments** in design document §3
- INI and `config_dict` go through the **same validation pipeline** (dict also forces all strings to be `int` / `bool`, direct specification is `TypeError`)
- Operational model that assigns change agents to each layer (argument = developer, INI = DevOps, environment variable = operator)
- Sanctuary (`diagnose` / `sens_kws` / `file_fmt` / `console_fmt`) blocks the set path
- Namespace can be separated with `env_prefix`
---

### 6.12 Latest status summary by library
| Item | D-SafeLogger v23k | stdlib `logging` | Loguru 0.7.3 | structlog 25.5.0 | picologging 0.9.3 | Eliot 1.18.0 | Logbook 1.9.2 | logfire 4.32.1 | OTel SDK 1.41.1 |
|---|---|---|---|---|---|---|---|---|---|
| Latest release date | (v23k/0.2.1, as of this report) | Python 3.14 | 2024-12-06 | 2025-10-27 | 2024-09-13 (GitHub) | 2026-05-07 | — | (4.32.1) | (1.41.1) |
| License | Apache 2.0 | PSF | MIT | MIT or Apache-2.0 | MIT | Apache 2.0 | BSD-3-Clause | MIT | Apache-2.0 |
| Python requirements | >=3.11 | (Python itself) | >=3.5,<4 | >=3.8 | >=3.7 | >=3.10.0 | >=3.9 | >=3.9 | >=3.9 |
| Number of runtime dependencies | **0** | 0 | 3 (conditional) | 1 (conditional) | 0 | 4 | 1 | 8 | 3 |
| stdlib compatible | drop-in extension | — | Replacement | Parallel running / forward | drop-in replacement | Parallel running | Replacement (compatible) | OTel bridge | OTel bridge |
| append-only routing | ◎ | — | — | — | — | — | — | out | out |
| Integrity verification (SHA-256) | ◎ | — | — | — | — | — | — | — | out |
| Multi-process function | parent-side Writer + 6-layer delivery state | Officially QueueHandler + separate listener recommended (DIY) | `enqueue=True` | (via stdlib) | (via stdlib) | Yes (Spanning Processes) | queue support | OTel exporter | OTel exporter |
| Delivery status classification | 7 layers + writer_reject 6 breakdown | — | — | — | — | — | — | OTel retry queue | OTel retry queue |
| Structured log | ◎ (JSON Lines) | △ | ○ (serialize) | ◎ (core function) | △ | ◎ (action tree) | ○ | ◎ (OTel) | ○ (OTel) |
| contextvars support | ◎ (FrozenContext) | △ | ○ | ◎ | △ | ○ | △ | ○ | ○ |
| free-threaded compatibility declaration | ◎ (clarified in design document) | △ | — | — | — | — | — | — | — |
| 3-layer configuration pipeline | ◎ (written) | △ (dictConfig) | △ | △ | stdlib compatible | △ | △ | OTel environment variables | OTel standard |
---

### 6.13 Composition of competitive ecosystem
#### 6.13.1 Distribution of "champion" by design axis
| axis | observed champion |
|---|---|
| Developer experience (DX) | Loguru |
| Structured log front end | structlog |
| Accelerating existing stdlib | picologging |
| causal action chain | Eliot |
| Observation SaaS Integration | logfire |
| Standard observability standard | OpenTelemetry |
| append-only Routing/Integrity Verification/Classified Delivery Status | **D-SafeLogger** |
It is observed that each project champions a different design axis. **No direct one-to-one feature overlap exists within the scope of this primary source study**.
#### 6.13.2 Boundary of "whether to replace or extend stdlib"
Three schools of thought are observed in how to handle stdlib `logging`:
1. **Replacement type** (mainly using original logger): Loguru / Logbook
2. **Parallel** (runs alongside or bridges stdlib): structlog / Eliot / logfire / OpenTelemetry
3. **Extended type** (lives in stdlib with `setLoggerClass()` and adds functionality): **D-SafeLogger** / picologging
D-SafeLogger and picologging are the same extension type, but have different purposes:
- picologging: same functionality, **improved speed** (C extension)
- D-SafeLogger: Same API, add **design-level differentiation** (append-only / integrity verification / multiprocess writer / delivery status classification)
#### 6.13.3 “Position in the Observability Stack”
OpenTelemetry's logs spec declares the following policy:
> "We embrace existing logging solutions and make sure OpenTelemetry works nicely with existing logging libraries."
> (OpenTelemetry Logs Specification, `opentelemetry.io/docs/specs/otel/logs/`)
This is the OTel community's stance of not replacing the logging library. logfire / OTel Python uses a bridge over stdlib `logging`.
D-SafeLogger maintains the entrance of stdlib `logging`, so it can coexist directly with the OTel bridge (`LoggingHandler`) (`examples/15_opentelemetry_logging.md`). Design to achieve trace correlation with `structured=True` + `contextualize(trace_id=..., span_id=...)` (§3.9.2).
#### 6.13.4 Gap area: "Multiprocess × local file output"
Within the scope of this primary source investigation, there are two cases in which the stdlib official cookbook recommends that ``if you want to output a file in multiple processes, create a separate process and send it using socket/queue'' as a library, D-SafeLogger and Loguru (`enqueue=True`). Difference:
- Loguru: Provide thread-safe / multiprocess-safe enqueue. Consolidated into a single API of `logger.add()`.
- D-SafeLogger: Explicit model for parent-side Writer + worker attach/detach. Delivery status 7 hierarchy classification. control plane separation. bound shutdown contract.
Within the scope of this research, D-SafeLogger is the only library observed that simultaneously satisfies the requirements of ``local file output, multiprocess, and explainability of delivery status.''
#### 6.13.5 Two systems with “supply chain focus”
Two items that satisfy zero runtime dependence are D-SafeLogger and picologging. Difference:
- picologging: C extension (indirect dependency on native build chain, hidden by wheel distribution)
- D-SafeLogger: Pure Python (only standard libraries such as `hashlib` / `multiprocessing` / `configparser` etc.)
"Pure Python x zero runtime dependencies x stdlib extension" is a combination unique to D-SafeLogger.
---

### 6.14 Competitive Comparison Summary
The primary sources confirmed in this chapter can be summarized as follows.
1. **No direct conflict observed**: Each major logging library (stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OTel) champions different design axes, and there are no projects within the scope of this primary source investigation that completely overlap in functionality with D-SafeLogger.
2. **Only 2 cases with zero dependencies, picologging**: In the scope of this study, compared to the number of dependencies of Loguru (3 conditionals) / structlog (1 conditional) / Eliot (4) / Logbook (1) / logfire (8) / OpenTelemetry SDK (3), only D-SafeLogger and picologging have completely zero dependencies. If you limit it to pure Python, D-SafeLogger alone.
3. **Append-only routing has no precedent in the Python ecosystem**: As claimed in §7.2 of the design document, there are no projects observed in the scope of this study that have append-only routing as the core architecture. It exists as options in Logback / Log4j2, but D-SafeLogger is observed to appear for the first time in Python.
4. **stdlib official clarifies that "active log cannot be renamed on Windows"**: Known limitation specified by `docs.python.org/3/library/logging.handlers.html` in the WatchedFileHandler section. The append-only design of D-SafeLogger is positioned as a direct response to this formal constraint.
5. **stdlib official clarifies that "multiprocess single file writing is not supported"**: The cookbook recommends using separate processes for QueueHandler + QueueListener. `dsafelogger.mp` of D-SafeLogger provides codirectionality (Writer-owned sinks + IPC) as the library itself.
6. **Delivery status 7 Layer classification has no precedent in other projects**: Layering of `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` / `partial_delivered` and `writer_reject` 6 This breakdown is not observed in other projects within the scope of this primary source investigation. OpenTelemetry's retry queue and Loguru's enqueue provide a delivery mechanism, but are not a classification specification for delivery failures.
7. **Completeness verification (SHA-256 sidecar + manifest) has no precedent in other projects**: In the scope of this investigation, other than D-SafeLogger, no project that provides the SHA-256 sidecar/manifest function as a library function is observed. The `sha256sum -c` compatible format allows verification using OS standard commands, which is also unique.
8. **Explicit declaration of free-threaded support is limited to D-SafeLogger within the scope of this research**: PEP 703 was accepted on 2023-10-24, and `--disable-gil` build is now available from Python 3.13. No explicit declaration of free-threaded support is observed in the official docs / GitHub README for any of Loguru / structlog / Eliot / Logbook / picologging / logfire / OpenTelemetry (as of 2026-05-09).
9. **In the scope of this research, D-SafeLogger is the only project that documents the systematic merging rules for the three-layer configuration pipeline (environment variables > INI/dict > arguments)**: `dictConfig` / `fileConfig` in stdlib is powerful, but it does not provide systematic rules for merging between layers. OTel's `OTEL_*` environment variable is limited to the SDK settings.
10. **Possible coexistence with OTel bridge layer**: D-SafeLogger maintains the ingress of stdlib `logging` in `logging.setLoggerClass()`, so it can coexist directly with `LoggingHandler` in OpenTelemetry Python. This position is different from the replacement type of Loguru / Logbook.
11. **Responsibility separation with structlog**: `examples/16_structlog_coexistence.md` presents two combinations in which structlog is responsible for the front end (event dictionary assembly) and D-SafeLogger is responsible for the back end (file output/routing/integrity/multiprocess).
12. **Comparison with logfire / OTel has different responsibilities**: logfire and OpenTelemetry Python are responsible for emission / export, and are not responsible for file output or rotation. It is not a competitive relationship with D-SafeLogger, but a complementary relationship (correlation by trace_id injection).
13. **Comparison with picologging has different objectives**: Both are stdlib compatible, but picologging has speed differentiation (4–17x with C extension), and D-SafeLogger has design differentiation (append-only / completeness / multiprocess writer). Can coexist and have no functional conflicts.
14. **Loguru has GitHub stars 23.9k** (as of 2026-05-09): The highest number of stars among the subjects of this survey. However, stars are an index of popularity and are not used for comparison of design axis with this library (Evaluation Policy §6.1.3).
15. **Latestness of release activities**: Eliot (2026-05-07), structlog (2025-10-27), Loguru (2024-12-06), picologging (2024-09-13). All are actively maintained. The latest release date of Logbook cannot be clearly confirmed within the scope of this investigation.
---

### 6.15 Summary of this chapter
The position of D-SafeLogger v23k in the ecosystem can be summarized in the following five points:
1. **There is no direct conflict and the design axis is unique**: The combination of append-only routing × integrity verification × multiprocess writer × delivery state 7-layer classification × free-threaded support × 3-layer configuration pipeline × zero dependence on pure Python is not observed in other projects within the scope of this primary source investigation.
2. **Among stdlib extension types, D-SafeLogger is the only functionally differentiated type**: picologging is the same extension type, but the purpose is "speed differentiation". It occupies a different niche from the replacement type of Loguru / Logbook and the parallel / bridge type of structlog / Eliot / logfire / OTel.
3. **Direct response to stdlib official known constraints**: Active log cannot be renamed on Windows, multiprocess single file not supported, these two constraints are clearly stated in the Python official docs themselves, and D-SafeLogger's append-only routing and parent-side Writer are direct responses to these.
4. **Relationship with OpenTelemetry / structlog / logfire is not competition but coexistence**: OTel bridge, structlog coexistence (2 patterns), logfire via OTel exporter, integration patterns are presented in `examples/` for both.
5. **The explicit declaration of support for PEP 703 is limited to D-SafeLogger within the scope of this investigation**: Explicit locking of the shared state, reprized snapshot of `f_locals`, and empty Context start of internal threads are stipulated at the specification level.
These points are revisited in the next chapter, “7. Positioning at OSS Release,” as **positioning logic** for evaluating fit with the supply-chain-focused segment, Windows operations segment, audit segment, free-threaded migration segment, stdlib-conservative segment, and multiprocess-audit segment.
---

> **Main reference materials for this chapter**: D-SafeLogger publication materials: `docs/design/D_SafeLogger_Specification_v23k_full.md` §1, §2, §3, §7.2, §11, §12 / `README.md` / `BENCHMARK.md` / `examples/08_compliance_audit.md` / `examples/15_opentelemetry_logging.md` / `examples/16_structlog_coexistence.md`. Primary source: `pypi.org/pypi/loguru/json` / `pypi.org/pypi/structlog/json` / `pypi.org/pypi/picologging/json` / `pypi.org/pypi/eliot/json` / `pypi.org/pypi/Logbook/json` / `pypi.org/pypi/logfire/json` / `pypi.org/pypi/opentelemetry-sdk/json` / `docs.python.org/3/library/logging.html` / `docs.python.org/3/library/logging.handlers.html` / `docs.python.org/3/howto/logging-cookbook.html` / `docs.python.org/3/whatsnew/3.13.html` / `peps.python.org/pep-0703/` / `github.com/Delgan/loguru` / `github.com/microsoft/picologging` / `www.structlog.org` / `eliot.readthedocs.io` / `logbook.readthedocs.io` / `pydantic.dev/docs/logfire/` / `github.com/pydantic/logfire` / `opentelemetry.io/docs/specs/otel/logs/` / `opentelemetry.io/docs/languages/python/instrumentation/`. Confirmation date: 2026-05-09.
> This document is intended to explain and evaluate the current v23k architecture, and does not include improvement proposals, issue management, or future roadmaps. Private planning materials are excluded from reference.
## Chapter 7 Positioning at OSS Release
### 7.1 Scope and policy of this chapter
#### 7.1.1 Scope of this chapter
This chapter logically organizes how the architectural characteristics of this library fit into observable ecosystem requirements and operational patterns at the time of OSS release. We do not make predictions about the adoption rate, popularity, or response; we limit ourselves to the design position that can be confirmed from public materials.
Based on this, this chapter is written along the following lines:
| What to include | What not to include |
|---|---|
| Architectural characteristics (facts observed in existing chapters) | Predictions such as "becoming popular" and "widely adopted" |
| Ecosystem requirements/operation patterns (as confirmed by primary sources) | Compliments such as "great" and "excellent" |
| Compatibility between characteristics and requirements (logical fit) | Unsupported regional claims such as “It may be acceptable in Japan, but overseas...” |
| Technical value by observable segment | Numerical prediction of adoption rate/diffusion |
#### 7.1.2 Definition of evaluation axis
The evaluation in this chapter is described using the following logical structure:
```text
[Observed architectural characteristics] × [Observed ecosystem requirements/operational patterns]
  ↓
If it fits: What technical value can the characteristic provide to that segment?
If it doesn't fit: Why the segment's requirements don't intersect with the library's scope of responsibility.
```

In other words, both the ``reachable layer'' and the ``unreachable layer'' are described as **logic**, and no value judgment is attached to either.
#### 7.1.3 Basis for selecting assumed segments
The following six segments were selected to cover the architectural characteristics of this library confirmed in Chapters 1 to 6. Each segment is defined as a "group of developers or organizations with specific operational or technical requirements," to which one or another axis of architectural characteristics corresponds directly.
| Segment | Corresponding D-SafeLogger characteristics |
|---|---|
| Supply chain security focused layer | Zero runtime external dependencies + Vendor-Agnostic + Apache 2.0 |
| Windows server operation layer | Append-Only routing + Windows rename problem avoidance |
| Audit/Compliance layer | SHA-256 sidecar + manifest + `sha256sum -c` compatible |
| Free-threaded migration consideration layer | PEP 703 explicit support + explicit locking of shared state |
| stdlib conservative layer | drop-in extension + preserve existing `getLogger()` call site |
| multiprocess audit layer | parent-side Writer + delivery status 7 hierarchical classification + bounded shutdown |
These are not independent segments and **can overlap** (e.g. the audit and compliance layer often overlaps with the Windows server operations layer). This chapter evaluates each segment independently, and then discusses overlap, intersection, and domestic and international differences in §7.9.
---

### 7.2 Segment 1: Supply-chain-security-focused users
#### 7.2.1 Observed Requirements for Segments
This segment has the following operational requirements:
- Want to minimize the number of dependent packages during installation (reducing CVE exposure)
- License compatibility of dependent packages needs to be aligned with organizational policies
- Need to continuously track update impact of dependent packages (SBOM/OSV, etc.)
- Want to structurally reduce the risk of dependent package takeover (typosquatting/malicious maintainer replacement)
#### 7.2.2 Corresponding characteristics of D-SafeLogger
Facts confirmed in Chapter 4 §4.2 and Chapter 6 §6.3:
- **Zero runtime external dependencies** declared as an "absolute condition" in design document §1
- **Vendor-Agnostic principle**: Core module (`src/dsafelogger/`) has no vendor-specific imports in the core code (including OpenTelemetry, etc.)
- **License**: Apache License 2.0
- **Distribution**: the wheel contains runtime package files under `src/dsafelogger/`. The sdist includes docs / examples / tests / benchmark summaries / selected benchmark summaries, and excludes private planning materials and temporary working files.
- **`py.typed` included**: Explicit type information
#### 7.2.3 Compatibility relationships
The technical value that this segment can find in this library can be observed as follows:
1. **Additional CVE exposure surface is (theoretically) zero**: No new CVE routes will increase other than vulnerabilities in this library itself. Loguru / structlog / Eliot / Logbook / logfire / OpenTelemetry SDKs all have conditional or unconditional runtime dependencies (§6.3) and have fewer supply chain paths.
2. **One license compatibility check**: Apache 2.0 only. No need to manage combinations of MIT / BSD-3-Clause / OPL, etc.
3. **Minimum number of items when generating SBOM**: Do not add additional items to the output of automatic SBOM tools (CycloneDX / SPDX).
4. **No risk of third-party hijacking**: There is no path for changes in maintainers of dependent packages or malicious updates to be introduced via this library.
5. **OSV/GHSA scan hits are concentrated on the library itself**: Results from vulnerability scanners such as `pip-audit` / `safety` can be narrowed down to the library itself.
#### 7.2.4 Non-conformance logic
The conditions under which the requirements of this segment are not met are as follows:
- **"I want to integrate logging based on the Pydantic/OpenTelemetry ecosystem" **Does not directly meet my needs (logfire/OTel SDK is more direct). However, indirect integration is possible with the `contextualize(trace_id=...)` pattern of `examples/15_opentelemetry_logging.md` (§3.9.2).
- **"I want to extract multiple functions from a single dependent package"** Does not meet the needs. This library has a narrowly defined scope of responsibility and does not handle the entire observability (traces / metrics / logs) (README "Compatibility / Non-goals" section).
#### 7.2.5 Positioning
This library satisfies the combination of "zero dependencies x pure Python x stdlib extension", and within the scope of this primary source investigation, no direct equivalents other than picologging (C extension) have been observed (§6.3.1). This is positioned as an option that has a different design axis from other libraries in response to the requirement of "strengthening logging without increasing dependencies."
---

### 7.3 Segment 2: Windows server operations
#### 7.3.1 Observed Requirements for Segments
This segment has the following operational requirements:
- Operate resident services on Windows Server
- Environment where antivirus/backup tools/monitoring agents open log files at the same time
- Encountered a situation where rename / move / delete of active log file fails with `PermissionError`
- Experienced incidents where midnight rotation fails with default stdlib `RotatingFileHandler` / `TimedRotatingFileHandler`
#### 7.3.2 stdlib official known constraints
Constraints specified by `docs.python.org/3/library/logging.handlers.html`:
> "This handler is not appropriate for use under Windows, because under Windows open log files cannot be moved or renamed - logging opens the files with exclusive locks."
> (`logging.handlers` WatchedFileHandler clause)
This restriction is a description of WatchedFileHandler, but the OS restriction itself that **active log files on Windows cannot be renamed from other processes** is officially documented.
#### 7.3.3 Corresponding characteristics of D-SafeLogger
Facts confirmed in Chapter 5 §5.1 and Chapter 6 §6.5:
- **Append-Only Routing**: Designed to manage generations by switching output destination file names without rename/truncate (Design document §7.2)
- **9 routing modes**: `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / `cyclic_weekday` / `cyclic_month` / `none`, all append-only
- **Self-healing**: If purge fails, retry at next switching timing
- **Sanitization rules for `pg_name`**: Forbidden characters in Windows filenames (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) replaced with `_`
- **CLI tool `dsafelogger tail -f`**: Transparent file switching tracking (operation complement of Append-Only model)
#### 7.3.4 Compatibility relationships
The technical value that this segment can find in this library can be observed as follows:
1. **Rename failure due to Windows lock contention does not occur**: Since the rename operation is not performed at the design level, it does not face the limitations explicitly stated in the stdlib official.
2. **Coexistence with antivirus/backup tools**: Even if another process has the log file open, the log output will be switched to the file with the new name, so it will not be affected.
3. **midnight rotation failure incident structurally disappears**: Switching with `routing_mode='daily'` only opens the new file and does not rename the old file.
4. **CLI compensates for the operational weaknesses of `tail -f`**: The weaknesses of the Append-Only model where file names change dynamically are compensated for by transparent tracking of `dsafelogger tail -f` (Design document §8.1).
#### 7.3.5 Non-conformance logic
- **`routing_mode='none'` meets the needs of ``I want to operate with a single fixed file name (`app.log`)'', but in that case, there is little need for the advantage of append-only (avoiding rename conflicts) (because rotation itself does not occur).
- **"I want to operate `logrotate` in a Linux-only environment"** needs can be met with `routing_mode='none'` + `ReopenLogFiles()`. On Linux/POSIX, rename-based rotation often succeeds at the filesystem layer, but writers can still continue through old descriptors, so operations that mutate the active file should be checked against the boundary conditions in §5.3.4.
#### 7.3.6 Positioning
In the scope of this primary source investigation, no other library has been observed in the Python ecosystem that solves the Windows renameability constraint that is clearly stated in the stdlib official (§6.5.3). In Java, Logback / Log4j2 provide an equivalent append-only option, but in Python, this library takes precedence.
---

### 7.4 Segment 3: Audit and compliance
#### 7.4.1 Observed Requirements for Segments
This segment has the following operational requirements:
- Applications running in regulated industries (medical HIPAA, financial SOC 2/PCI-DSS, government FedRAMP, etc.)
- Detection of log file tampering is required as an audit requirement
- Detection of missing log files is required as an audit requirement
- It is desirable that the verification method be standard (OS standard command/industry standard format)
- A mechanism is required to prevent confidential information (API keys, tokens, passwords) from being mixed into logs.
#### 7.4.2 Corresponding characteristics of D-SafeLogger
Facts confirmed in Chapter 4 §4.4, §4.5, Chapter 5 §5.4, Chapter 5 §5.21:
- **SHA-256 sidecar** (`{original_file_name}.sha256`): `sha256sum -c` compatible format, relative path description, atomic write with `os.replace()`
- **Manifest file** (`manifest_path`): Addition with timestamp, storage recommended in separate directory and with separate permissions, file loss detection
- **chunk 64KB read**: Use only standard library `hashlib`
- **Sanctuary of `diagnose`**: Enabled only by environment variable `D_LOG_DIAGNOSE=1`, cannot be set from INI / argument
- **`sens_kws` Built-in 12-word masking**: `f_locals` Mask by matching variable name part during expansion
- **HMAC/CLI verification commands clearly marked as out of scope**: Design document §7.6.7
The beginning of `examples/08_compliance_audit.md` is specified as follows:
> In regulated industries — healthcare (HIPAA), finance (SOC 2, PCI-DSS), government (FedRAMP) — proving that logs haven't been tampered with isn't optional.
> (`examples/08_compliance_audit.md`)
#### 7.4.3 Compatibility relationships
The technical value that this segment can find in this library can be observed as follows:
1. **Can be verified with OS standard commands**: By adopting the `sha256sum -c` compatible format, verification is possible with `sha256sum` of `coreutils` or `Get-FileHash` of PowerShell. There is no need to include proprietary verification tools as audit targets.
2. **Strong for log transfer due to file relative path description**: Verification will not be broken even if a set of logs is transferred to another location (WORM storage for auditing, etc.).
3. **File loss detection using manifest**: The pattern of "file + sidecar deleted together", which cannot be detected by sidecar alone, can be detected by inconsistency with manifests in different directories and different permissions.
4. **Structural containment of `diagnose`**: Structurally eliminates the pattern of "leaving debug mode in production" (there is no way to write `diagnose=True` in code, it cannot be set from INI, only `"1"` is a valid value).
5. **Customizability of masking**: `sens_kws` You can also add organization-specific sensitive keywords (`ssn`, `credit_card`, `account_number`, etc.).
6. **The boundaries of the threat model are clearly stated in the document**: It is clearly stated in the `examples/08_compliance_audit.md` Threat Model section that if an attacker can rewrite the file + sidecar + manifest with the same authority, tampering cannot be detected, which prevents misuse due to excessive expectations.
#### 7.4.4 Non-conformance logic
- **"Cryptographic non-repudiation (HMAC signature/digital signature) is an audit requirement"** is outside the scope of this library. Design document §7.6.7 expressly excludes. The plan is to delegate responsibility to an external signature tool (such as another library in the D ecosystem) that takes the hash of this library as input.
- **"I also want to ensure the integrity of the active log file" **Does not meet your needs. This library's hashing is only applicable to "files that have been written" (§5.4 Hashing has no meaning in intermediate states).
- If you want to write logs to WORM storage in real time, this library is designed to handle up to local file output and delegate shipping to an external tool (Fluent Bit / Vector / Filebeat, etc.) (README "Compatibility / Non-goals" section).
#### 7.4.5 Positioning
In the scope of this primary source investigation, we do not observe any Python projects that provide SHA-256 sidecars or manifests as library functions (§6.8.1). OpenTelemetry/logfire is responsible for emission/export, but file integrity is outside of its scope of responsibility. For Loguru / structlog / Eliot / Logbook / picologging, there is no mention of the integrity verification function in the official docs. This library is positioned as a technological option that directly addresses the niche of "local file auditing".
---

### 7.5 Segment 4: Free-threaded migration evaluation
#### 7.5.1 Observed Requirements for Segments
This segment has the following technical requirements:
- After PEP 703 Accepted (2023-10-24), `--disable-gil` build will be adopted experimentally or in production.
- It is necessary to check GIL independence support for libraries with shared mutable state.
- It is necessary to check the `Py_mod_gil` compatibility of libraries that include C extensions.
- Request an implementation that does not rely on implicit thread safety for `list` / `dict`
#### 7.5.2 Current status of PEP 703
Main facts of `peps.python.org/pep-0703/` (§6.9):
- 2023-10-24 Accepted
- Available on Python 3.13+ with `--disable-gil` build flag
- Rollout policy: "the rollout be gradual and break as little as possible"
- Runtime control: `PYTHON_GIL` environment variable, `Py_mod_gil` module slot
#### 7.5.3 Corresponding characteristics of D-SafeLogger
Facts confirmed in Chapter 5 §5.19 and Chapter 6 §6.9:
- Design document §1 **Specifies free-threaded build of Python 3.13 or higher as the design target**
- Design document §2 stipulates that "The shared states of `_configure_state`, `_active_pipeline`, `_active_workers`, `_custom_levels`, etc. are protected by explicit locking without assuming the existence of GIL. They do not depend on the implementation-dependent atomicity of `list` / `dict`."
- Run entire `ConfigureLogger` under `_lifecycle_lock` retention in v21 revision
- Convert `f_locals` to repr'd snapshot in producer thread (cross-thread safety, §9.4)
- Start internal thread with empty `Context` (§9.5)
- No need for `Py_mod_gil` support (C extension side) due to pure Python implementation
- Manual test procedure documented in `TESTING.md`: `PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v`
#### 7.5.4 Compatibility relationships
The technical value that this segment can find in this library can be observed as follows:
1. **Zero additional support cost when adopting PEP 703**: Since it is already protected by explicit locking, the risk of race condition caused by this library is structurally low even if you switch to `--disable-gil` build.
2. **Pure Python implementation, no need for C extension support**: `Py_mod_gil` module slot support, wheel build reconfiguration, and C extension update verification are not required. It has a different cost structure compared to C extension libraries like picologging.
3. **Manual test procedure for free-threaded builds is documented**: The normal CI matrix targets regular CPython 3.11-3.14 builds, while free-threaded builds are validated using the `TESTING.md` procedure.
4. **Explicit locking of shared state is declared as a design decision**: The design intent of locking is documented so that intent can be tracked during maintenance in free-threaded environments.
#### 7.5.5 Non-conformance logic
- This feature does not provide direct value to those who are not interested in free-threaded builds and are satisfied with only a GIL-enabled environment. However, even in this case, explicit locking works in the direction of reducing the race condition risk not only in free-threaded but also in normal build (neutral).
- Picologging is more suitable for the layer where ``speeding up is essential by extending own C''** (speed differentiation). This library and picologging can coexist because their responsibilities are different (§6.13.2).
#### 7.5.6 Positioning
In the scope of this primary source investigation, no explicit declaration of free-threaded support is observed in the official docs / GitHub README of Loguru / structlog / Eliot / Logbook / picologging / logfire / OpenTelemetry (§6.9.1, as of 2026-05-09). This library is unique within the scope of this study in that it has been explicitly declared as a design target after being accepted by PEP 703.
This is seen as an option that has a different design axis from other libraries in response to the requirement that "organizations considering adopting PEP 703 are looking for a library that proactively supports the logging layer." However, the rollout of PEP 703 is "gradual and break as little as possible," and the number of organizations that have adopted free-threaded builds in production is likely to be limited at this point (the size of this segment is not estimated in this chapter).
---

### 7.6 Segment 5: stdlib-conservative users
#### 7.6.1 Observed Requirements for Segments
This segment has the following operational requirements and orientation:
- The existing codebase is written mainly around `import logging` / `logging.getLogger(__name__)`
- Extensive use of `logging.getLogger()`-based third parties such as SQLAlchemy / Django / Flask / requests / boto3 etc.
- Don't want to pay the cost of "replacing a logging framework"
- How to use the standard library/want to maintain conventions
- Want to maintain affinity to official `dictConfig` / `fileConfig` structures
#### 7.6.2 Corresponding characteristics of D-SafeLogger
Facts confirmed in Chapter 1 §1.4, Chapter 3 §3.7, Chapter 6 §6.4:
- **Drop-in extension with `logging.setLoggerClass()`**: Do not change existing `logging.getLogger()` / `logger.info()` call sites
- **Automatic co-participation of third-party libraries**: The logger obtained by SQLAlchemy / Django etc. with `logging.getLogger()` will follow the configuration flow of this library.
- **`config_dict` has the same validation as INI**: The structure is different from the official `dictConfig`, but it has a simple two-layer structure that is compatible with INI (`global` + `dsafelogger:module_name`)
- **Keep existing call site**: `examples/03_migration_from_stdlib.md` presents 3 migration patterns (basicConfig / TimedRotatingFileHandler / dictConfig), all of which require no change to `logger.info()` call site
- **Setup code lines reduced by 50–60%**: manual wiring of handler / formatter / setLevel consolidated into `ConfigureLogger()` parameter
#### 7.6.3 Compatibility relationships
The technical value that this segment can find in this library can be observed as follows:
1. **Features can be added without rewriting the existing codebase**: append-only routing / integrity verification / environment variable override / multiprocess Writer can be added without changing the call site of `logger.info()`.
2. **Unified management of third-party library logs**: SQLAlchemy query logs, Django middleware logs, requests retry logs, etc. are included in the routing/integrity verification of this library (because they use the common `logging.getLogger()`).
3. **Stdlib API semantics are not broken**: Do not modify `record.levelname`, do not use global side effects of `addLevelName()`, and completely override `QueueHandler.prepare()` to separate semantics from stdlib differences (§4.9, §5.4.4). Third party `SMTPHandler` / `pytest caplog` etc. also work as intended.
4. **Low learning cost**: The entrance to the public API is two functions: `ConfigureLogger()` and `GetLogger()`. Minimum code is 3 lines (§3.1–§3.2).
#### 7.6.4 Non-conformance logic
- **"I want to use Loguru / structlog API (`logger.bind()` / `logger.add()`)" **Does not meet your needs. This library is not a replacement type. However, two patterns of coexistence with structlog are presented in `examples/16_structlog_coexistence.md` (§3.9.1).
- If you want to maintain the detailed filter/custom handler structure of stdlib `logging`'s dictConfig, you will need to convert the structure when migrating because the granularity is different from the two-layer structure of `config_dict` in this library.
#### 7.6.5 Positioning
This library is the same "stdlib extension type" as picologging, but its purpose is different (§6.13.2):
- picologging: same functionality, improved speed
- D-SafeLogger: Same API, adds design level differentiation
Regarding the requirement of ``I want to enhance the area below the file output boundary while maintaining the API of stdlib `logging`,'' within the scope of this primary source investigation, no options other than this library were observed that directly correspond to the requirement. Loguru/Logbook is a replacement type, structlog is a parallel type, and logfire/OTel is a bridge type, so the design axes do not intersect.
---

### 7.7 Segment 6: Multiprocess audit
#### 7.7.1 Observed Requirements for Segments
This segment has the following operational requirements:
- I want to aggregate logging from multiple worker processes (Gunicorn / uWSGI / Celery / multiprocessing.Pool / ProcessPoolExecutor etc.)
- I want to configure the worker process to not directly open the shared log file (avoiding Windows lock/Linux file descriptor conflicts)
- I want to visualize log loss during backpressure as a counter / warning instead of a "silent gap"
- Requires predictable shutdown behavior during worker crash
- I want to enable post-analysis of abnormal events using shutdown summary.
#### 7.7.2 stdlib official statement
Clarification of `docs.python.org/3/howto/logging-cookbook.html` (§6.5.2 reposted):
> "Logging to a single file from multiple processes is not supported, because there is no standard way to serialize access to a single file across multiple processes in Python."
>
> "When deploying web applications using Gunicorn or uWSGI (or similar), multiple worker processes are created to handle client requests. In such environments, **avoid creating file-based handlers directly in your web application**. Instead, use a `SocketHandler` to log from the web application to a listener in a separate process."
This is the official recommendation that ``When outputting a file using multiple processes, a separate process listener is required.''
#### 7.7.3 Corresponding characteristics of D-SafeLogger
Facts confirmed in Chapter 2 §2.8, Chapter 5 §5.11–§5.14, and Chapter 6 §6.7:
- **sink ownership by parent-side Writer**: file sink, routing, hash, manifest, purge, archive, reopen are all consolidated in Writer
- **Worker only sends `LogEvent` via IPC**: Do not open shared log files directly (§4.6.1)
- **Complete separation of log plane / control plane**: Normal log and control commands are in separate queues, ACK is per-request `Pipe(duplex=False)`
- **7-level classification of delivery status**: lifecycle 5 + terminal 6 + qualifier 1
- **6 breakdown of `writer_reject`** (v23h): `writer_route_reject` / `writer_reconstruct_reject` / `writer_close_marker_reject` / `writer_sink_reject` / `writer_policy_reject` / `writer_format_reject`
- **shutdown summary**: Summarize all counters and output at shutdown
- **bounded shutdown contract** (v23h): `bounded wait (≤ 10 seconds) → visible warning → process exits`, physical guarantee with daemon=True
- **active client registry + worker crash timeout**: Terminate the registry remaining at timeout at worker crash (does not cause silent hang)
- **3 worker_model compatible**: `process` / `pool` / `executor` (`ProcessPoolExecutor` only, `ThreadPoolExecutor` is not applicable)
- **Child-only client identity after fork inheritance**: Rules not to reuse parent identity
- **registry hash verification (SHA-256)**: 2 timings: Writer bootstrap ready ACK and attach
#### 7.7.4 Compatibility relationships
The technical value that this segment can find in this library can be observed as follows:
1. **Stdlib official recommended structure is provided in the library itself**: You can use the officially recommended pattern of "separate process listener + IPC" without DIY.
2. **Explanability of delivery failure**: Bounded queue overflow / Writer crash / sink failure / route unresolvable / policy reject etc. are recorded as a counter of 7 layers + 6 items. "Log disappeared" can be classified into policy origin, bug origin, or unknown rather than uniformly.
3. **Only `unexpected_loss` is treated as a bug**: The remaining 6 types can be operationally explained as being derived from policy, and the granularity is defined such that only "state where accepted log disappears for no reason" is subject to alarm.
4. **No direct access to files from workers in a Windows environment**: Only the parent Writer holds the file, so there is no Windows lock contention from the worker's perspective (because the worker uses only IPC).
5. **Guaranteed host process survival with bounded shutdown**: Even if an unknown hang is mixed in the drain route, the host process exits after bounded join + visible warning + daemon thread in `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0` seconds.
6. **Non-zero notification of Writer exit code**: Abnormal termination of Writer can be detected from the monitoring system (systemd / Kubernetes liveness probe, etc.).
7. **`examples/12_multiprocess_logging.md`'s 438-line guide**: Covers the 3 patterns of Process / Pool / Executor, Windows spawn rules, attach/detach lifecycle, failure mode list, and shutdown summary interpretation.
#### 7.7.5 Non-conformance logic
- Does not meet the needs of ``raw multiprocess throughput is the top priority''**. As confirmed in `BENCHMARK.md` and §C.3, stdlib logging takes precedence in raw multiprocess throughput (D-SafeLogger sync is 63–75% of stdlib sync). The multiprocess value of this library is not raw throughput, but Writer-owned sinks + observability of delivery status.
- **"I want to aggregate using remote aggregation / network protocol" **The need is out of scope (Design document §11.2, Out-of-scope: remote aggregation / network protocol). Limited to local aggregation within a single host.
- **"I want to improve fan-in scalability with Writer parallelization" **The need is outside the scope (v23 system invariant, §12.1). Writer This is clearly stated as a matter that requires separate user judgment, as it tends to conflict with the safety of owning it alone.
#### 7.7.6 Positioning
In the scope of this primary source investigation, no other Python logging library was observed that reflects delivery failures in 7-level classification in counters / warning / shutdown summary (§6.7.3, §6.10). Loguru's `enqueue=True` provides multi-process secure hand-off, but does not provide hierarchical classification of delivery status. OpenTelemetry's retry queue is a retry mechanism to the OTLP backend, not a classification specification for delivery failures.
Within the scope of this research, this library is observed as a unique option for a library that simultaneously satisfies "local file output x multiprocess x explainability of delivery status" (§6.13.4).
---

### 7.8 Overlaps and intersections between segments
These six segments are not independent and tend to overlap operationally.
| Overlapping combinations | Typical observed use cases |
|---|---|
| Supply chain × stdlib conservative | Systems that want to minimize the addition of dependent packages in government, public sector, and regulated industries |
| Windows × Audit/Compliance | Windows server operation in regulated industries (auditing client terminals in finance and insurance, etc.) |
| Windows × multiprocess audit | Gunicorn for Windows / Celery worker configuration on Windows Server |
| Audit/Compliance × multiprocess audit | Batch processing platform with audit requirements, ETL pipeline, log aggregation with multiple workers |
| Free-threaded × stdlib conservative | PEP 703 I am a backend developer considering hiring and would like to maintain the existing stdlib `logging` configuration |
| Supply chain × Free-threaded | C Organizations moving to free-threaded while avoiding extended dependencies |
These overlaps only indicate a structure in which "architectural characteristics support multiple operational requirements simultaneously" and do not predict the size or adoption rate of each segment.
---

### 7.9 Domestic vs. overseas ecosystem differences
#### 7.9.1 Reconfirmation of evaluation policy
When OSS is released, it can be evaluated both domestically and internationally, but this document does not make subjective popularity predictions. This section only describes “regional differences in observable ecosystem characteristics” and “which architectural characteristics of this library align with those differences.”
#### 7.9.2 Regional differences in observable ecosystem characteristics
The following are **observable trends** in the technical community and operational environment, and should not be used to judge the superiority or inferiority of this library.
| Viewpoint | Observed regional differences | Corresponding axes of this library |
|---|---|---|
| Ratio of Windows Server Business Systems | In Japan, there is a relatively high adoption of Windows Server in domestic business SaaS/on-premises business systems (according to official statistics, the percentage of enterprise use is high). Overseas, Linux is the main choice, but there are also organizations that use Windows | Append-Only Routing (§7.3) |
| Regional framework for audit and compliance requirements | Domestic: Financial Services Agency regulations, Personal Information Protection Act, Medical Information Guidelines, etc. Overseas: HIPAA / SOC 2 / PCI-DSS / FedRAMP / GDPR etc. **In both cases, requirements include log integrity and tampering detection** | SHA-256 sidecar + manifest (§7.4) |
| Demand for Japanese documents | Japanese documents have a high affinity in Japan | `README_ja.md` is available, and the design documents are also in Japanese |
| Culture of organizational contribution to OSS | OSS PR/Issues tend to be highly active overseas (especially in the US and Europe). Domestically, it is increasing, but historically it is small | (Library's response axis is neutral) |
| OpenTelemetry Ecosystem Adoption | A rapidly growing global trend. Although there is a time difference between Japan and overseas, the adoption direction is the same | Coexistence with OTel Bridge (§7.6) |
| Supply Chain Security Awareness | Overseas, after examples of supply chain attacks (SolarWinds, etc.), regulations such as Executive Order 14028 in the United States are increasing requirements. In Japan, SBOM provision is mentioned in the Ministry of Economy, Trade and Industry's "Cyber ​​Physical Security Measures Framework" | Zero dependency × Apache 2.0 (§7.2) |
#### 7.9.3 Logical response to domestic issues
Correspondence between domestic operational environment characteristics (Windows business system ratio, Japanese document affinity, on-premises operation in regulated industries) and this library's characteristic axis:
- **Append-Only Routing × Windows Server Adopting Organizations**: Direct response to stdlib official known constraints identified in §7.3.
- **SHA-256 completeness × Domestic regulated industries (financial, medical, public)**: Compliant with audit log requirements confirmed in §7.4. `sha256sum -c` compatibility and verifiability using OS standard commands correspond to the requirement of ``minimizing the introduction of external tools'' in domestic on-premise operations.
- **`README_ja.md` + Japanese design document**: The design document (`docs/design/D_SafeLogger_Specification_v23k_full.md`) is written in Japanese, and the ability to refer to the context of design decisions in their native language will help reduce learning costs for domestic developers.
These are not predictions that the library will “become popular domestically”; they are a logical summary of characteristics that align with operational requirement patterns observed in Japan.
#### 7.9.4 Logical response to overseas countries
Correspondence between overseas technical community characteristics (Linux-based, OpenTelemetry ecosystem expansion, OSS contribution activity, supply chain regulatory requirements) and this library's characteristics:
- **Zero dependencies × Apache 2.0 × Supply chain regulatory requirements**: Correspondence to the context of SBOM / Executive Order 14028 / NIST SSDF etc. confirmed in §7.2.
- **Coexistence with OpenTelemetry bridge × OTel ecosystem expansion**: trace correlation via `LoggingHandler` confirmed in §7.6.
- **PEP 703 free-threaded support × Pre-adoption trend in overseas communities**: Declaration of support after PEP 703 Accepted confirmed in §7.5.
- **`README.md` (English) + examples English**: The design document itself is in Japanese, but the 17 example files and README are written in English.
- **monorepo / large-scale microservice configuration × multiprocess audit**: The parent-side writer + delivery status 7 layer classification confirmed in §7.7 corresponds to the observability requirements in large-scale microservice configurations typical overseas.
However, since the already established options of Loguru / structlog / OpenTelemetry Python are widely recognized in the overseas community, it is logically assumed that this library will be positioned as "an option for subset organizations with specific operational requirements (Windows, auditing, zero dependencies)" rather than as a direct replacement candidate.
#### 7.9.5 Common Logical Fit in Japan and Overseas
| Common requirements | Support of this library |
|---|---|
| Tamper detection requirements for regulated industries | SHA-256 Sidecar + Manifest |
| Increased Supply Chain Requirements | Zero Dependencies + Apache 2.0 + Vendor-Agnostic |
| Existing asset protection based on stdlib `logging` | drop-in extension (`setLoggerClass`) |
| OpenTelemetry ecosystem coexistence | `contextualize(trace_id=...)` + `LoggingHandler` coexistence |
| Free-threaded migration consideration | Explicit locking + pure Python |
These common axes are not region-specific; they can be observed as cross-regional ways in which this library’s characteristics apply.
---

### 7.10 Technical structure of OSS distribution
Organize the structural characteristics of this library in terms of OSS release (not the marketing positioning, but the technical structure of the distributed product).
#### 7.10.1 Distribution form
Facts that can be confirmed from `pyproject.toml` and `MANIFEST.in`:
- **distribution name**: `d-safelogger` (PyPI normalization)
- **import name**: `dsafelogger` (no hyphen)
- **Distribution target**: Only under `src/dsafelogger/`
- **Included**: `py.typed` type information, CLI entry point `dsafelogger`
- **Runtime dependencies**: None
- **Python Requirements**: `>=3.11`
#### 7.10.2 Documentation structure (reposted, §3.10)
- README: English version (`README.md`) + Japanese version (`README_ja.md`)
- examples: 17 files (English)
- Design document: `docs/design/` 3 files (basic design, detailed design, test design)
- API reference: `docs/api/` (automatically generated)
- Operation guide: `TESTING.md` / `BENCHMARK.md` / `CONTRIBUTING.md` / `CHANGELOG.md`
#### 7.10.3 Quality Gate
`TESTING.md` and public validation procedures:
- v23k local validation on Python 3.14.3 / Windows: **658 passed, 3 skipped** (661 collected, `uv run pytest tests -v`)
- The skipped count is platform-dependent because fork E2E tests are POSIX-only and Windows spawn E2E tests are Windows-only.
- Coverage: terminal total **87%**, XML line-rate **88.97%**, branch-rate **81.46%**
- multiprocess tests / OTel/structlog coexistence tests are included in the official quality gate
- Type validation: public validation includes `mypy src`, `pyright src`, `pyright tests/typing_smoke`, and a 100% `pyright --verifytypes dsafelogger --ignoreexternal` completeness gate against the built wheel. The smoke-test directory is named `tests/typing_smoke/` to avoid shadowing the standard-library `typing` module.
- free-threaded build test: `PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v`
#### 7.10.4 Release Management
Public validation procedures:
- Internal synchronization verification of public design document with `scripts/check_design_docs_sync.py`
- API documentation verified with `scripts/generate_api_docs.py --check`
- The benchmark selection session is fixed at `benchmarks/summary/manifest.json` (to avoid the accident that the last benchmark executed is automatically promoted to the public representative result)
- `BENCHMARK.md` is an interpretation of manual editing and will not be regenerated from benchmark runner
#### 7.10.5 Status at time of publication
Pre-publication review record (as of 2026-05-07):
- Current release target version: `0.2.1`
- Latest pre-release review results: **GO-with-fixes**
- Required correction items before publication (release blockers) are listed
Although these indicate the existence of a ``prepared release operation flow,'' this chapter does not consider this to be the ``reason for popularity,'' but only records it as the technical structure of the distribution.
---

### 7.11 Positioning Summary
#### 7.11.1 Summary of reachable audiences
Summarizing the compatibility with the six segments discussed in this chapter, this library is positioned as an option with a different design axis from other libraries on the following four axes:
1. **``stdlib extended type × pure Python × zero dependencies × append-only''**: A combination not observed elsewhere in the scope of this primary source investigation.
2. **``parent-side Writer × Hierarchical classification of delivery status''**: A combination that provides the separate process listener pattern recommended by stdlib official together with delivery status counters.
3. **“SHA-256 sidecar × manifest × `sha256sum -c` compatible”**: Integrity verification as a library function is not observed elsewhere in the scope of this investigation.
4. **“Explicit support for PEP 703 × Explicit locking of shared state”**: No other declaration of support in official docs was observed within the scope of this investigation.
All of these four axes are for "subset organizations with specific operational requirements", and their design purpose is different from "DX improvement for a wide range of developers" axes like Loguru/structlog.
#### 7.11.2 Summary of hard-to-reach groups
Due to its design purpose, this library is difficult to reach for those with the following operational requirements and orientations:
| layer | reason |
|---|---|
| DX-focused layer that wants the logger API to be completely redesigned | This library is a drop-in extension type, and the API is maintained as stdlib. Loguru / Logbook fits the purpose better |
| A layer that prioritizes speed only | Does not provide speedup through C extensions. picologging fits the purpose better |
| Layer requiring "remote aggregation / distributed logging backend" | Explicitly out of scope in design document §11.2 |
| People looking for "Pydantic / OpenTelemetry SaaS integrated observability" | logfire fits the purpose |
| People looking for a "logging model centered on event causal chain" | Eliot fits the purpose better |
The relationship between these layers is not a competition, but an observation that the design axes do not intersect.
#### 7.11.3 Summary of layers that can coexist
This library has a structure that allows it to coexist with the following libraries:
| Coexistence destination | Coexistence pattern |
|---|---|
| structlog | Pattern A: dual stream (JSON in structlog, human text in this library) / Pattern B: unified output (event assembly in structlog → routing in this library) |
| OpenTelemetry Python | attach `LoggingHandler` to logger after `setLoggerClass()` + `contextualize(trace_id=..., span_id=...)` |
| logrotate (external rotator) | `routing_mode='none'` + `ReopenLogFiles()` |
| pytest caplog | Standard fixture works for stdlib `logging` compatibility |
| SQLAlchemy / Django / Flask / Third-party libraries | Automatic co-participation with `setLoggerClass()` |
The design attitude toward "coexistence rather than replacement" (§1.4.4/§3.9) works toward minimizing interference with existing ecosystems.
#### 7.11.4 Aggregation of positioning logic
Summarizing the above, the logical position of this library in terms of OSS release can be summarized as follows:
- **Not designed to be widely popular**: The design document §1 itself clearly states that ``the top priority is to operate it as a common base of the D ecosystem rather than to spread it widely.''
- **High degree of fit for specific operational requirements**: the six segments of Windows server operations, audit/compliance, multiprocess audit, supply-chain security focus, free-threaded migration consideration, and stdlib-conservative usage each have clear logical fit with the library’s design axes.
- **Aimed at coexistence with existing ecosystem**: Operates as a stdlib extension type and can run in parallel with structlog / OpenTelemetry / third party libraries.
- **Narrowly defined scope of responsibilities**: log shipper / metrics pipeline / distributed tracing backend / access control system are out of scope (clarified in README).
- **Clarify failure boundaries in documentation**: HMAC outside scope, meaning of `UnexplainedLost`, Writer warranty range, and What Not To Claim are actively enumerated.
---

### 7.12 Summary of positioning at OSS release
The observed facts referenced in this chapter can be summarized as follows. This is a logical summary of how the architectural characteristics of this library can provide technical value in the modern Python ecosystem.
1. **It has a logical fit with six segments**: supply-chain-security-focused users, Windows server operations, audit/compliance, free-threaded migration evaluation, stdlib-conservative users, and multiprocess audit. Each axis maps directly to a distinct architectural characteristic of the library.
2. **Observed as an option with a design axis different from other libraries on four axes**: "stdlib extension type × pure Python × zero dependencies × append-only", "parent-side writer × delivery state hierarchy classification", "SHA-256 sidecar × manifest × `sha256sum -c` compatibility", "PEP 703 explicit support × shared state explicit locking". Within the scope of this primary source survey, no project has been observed that satisfies these four axes at the same time.
3. **Difficult to reach five layers due to design purposes**: DX completely redesigned layer / speed-first layer / distributed logging backend layer / SaaS integrated observability layer / event causal chain layer. Since these are not competitors and their design axes do not intersect, it is difficult to position this library as a candidate.
4. **Can coexist with 5 libraries/operation configurations**: structlog (2 patterns) / OpenTelemetry Python (`LoggingHandler` + `contextualize`) / logrotate (`routing_mode='none'` + `ReopenLogFiles`) / pytest caplog / Third party libraries such as SQLAlchemy and Django.
5. **Common compliance axes in Japan and overseas**: Tampering detection requirements for regulated industries / Increase in supply chain requirements / stdlib `logging`-based existing asset protection / OpenTelemetry ecosystem coexistence / Free-threaded migration consideration. An axis that allows the characteristics of this library to reach across regions without regional differences.
6. **Domestic-specific support axes**: Windows business system ratio / On-premises operation in regulated industries / Japanese document compatibility. The fact that the design documents are written in Japanese serves to reduce the learning costs for domestic developers.
7. **International-market perspective**: Trend in early adoption of PEP 703 / Supply chain regulatory requirements such as Executive Order 14028 / Large-scale microservice configuration. examples / README English, Apache 2.0, zero dependencies are supported.
8. **The design purpose is clearly not “wide dissemination”**: §1 of the design document declares that the “top priority is to operate as a common foundation for the D ecosystem rather than to pursue wide adoption.” This reflects a design stance that prioritizes fit for organizations with specific operational requirements.
9. **Document operations that actively specify failure boundaries**: Threat Model of `examples/08_compliance_audit.md` / Writer does not guarantee of `examples/12_multiprocess_logging.md` / What Not To Claim of `BENCHMARK.md` / HMAC out-of-scope declaration in design document §7.6.7 / remote aggregation out-of-scope declaration in design document §11.2. These are consistent with the operational stance of ``preventing misuse due to excessive expectations.''
10. **Quality gate transparency**: 658 passed / 3 skipped on Python 3.14.3 / Windows (661 collected), coverage 87% terminal, free-threaded build test procedure, internal synchronization verification by `scripts/check_design_docs_sync.py` and `scripts/generate_api_docs.py --check`, benchmark session fixation by `benchmarks/summary/manifest.json`. The skipped count can vary by OS. These are recorded as observable quality indicators when evaluating candidate libraries for introduction.
11. **Clear distribution structure**: The wheel contains runtime package files only and includes `py.typed`. The sdist includes docs / examples / tests / benchmark summaries / selected benchmark summaries for public validation and reproducibility. Private planning materials and temporary working files are excluded.
12. **Relationship with competitors is not competition but separation of responsibilities**: structlog (front end) / OTel (emission) / Loguru (DX replacement) / picologging (speed differentiation) / logfire (SaaS) / Eliot (causal) have different responsibility axes and coexist or run in parallel with this library. Popularity indicators such as Loguru's 23.9k stars are a context independent of comparison of design dimensions.
---

### 7.13 Summary of this chapter
The positioning of D-SafeLogger v23k at the time of OSS release can be logically summarized into the following five points:
1. **Although no direct competition is observed in the scope of this primary source study, this is not a prediction of ``widespread popularity''**. Since the design purpose is "to support subset organizations with specific operational requirements," the design axis is different from the DX improvement axis such as Loguru / structlog.
2. **The six segments (supply chain / Windows / audit / free-threaded / stdlib conservative / multiprocess audit) are logical fit axes**. These structures are not independent; they overlap.
3. **There are five common response axes in Japan and overseas**: Regulated industry tampering detection / supply chain requirements / stdlib existing asset protection / OpenTelemetry coexistence / free-threaded migration consideration. It is observed as an axis with no regional differences.
4. **5 layers hard to reach by design**: DX complete redesign / speed first / distributed backend / SaaS observability / event causal chain. These are not competing design axes but non-intersecting design axes.
5. **Can coexist with 5 libraries/operational configurations**: structlog / OpenTelemetry / logrotate / pytest caplog / third party stdlib `logging` library. The result of a design attitude that aims for "coexistence rather than replacement."
These points are summarized in the next chapter, “8. Overall Evaluation,” as the final technical positioning based on the objective facts of this report as a whole.
---

> **Main references for this chapter**: Only the content referenced in Chapters 1 to 6. No new primary sources were added. `docs/design/D_SafeLogger_Specification_v23k_full.md` §1, §2, §11.2, §12.1 / `README.md` Compatibility/Non-goals section / `BENCHMARK.md` What Not To Claim section / `examples/08_compliance_audit.md` Threat Model section / `examples/12_multiprocess_logging.md` Section 3 / Section 6 All primary sources identified in chapter.
## Chapter 8 Overall Evaluation
### 8.1 Scope of this chapter
This chapter **aggregates** the observed facts organized individually in Chapters 1 to 7, and presents the position that can be described as the **reaching point** of the current v23k architecture.
#### 8.1.1 Reconfirming the scope of this document
Reiterating the overall scope of this whitepaper:
1. **Does not include improvement proposals, issue management, or future roadmaps**: This document is intended to explain and evaluate the current architecture as of v23k, and is not a replacement for the issue tracker/roadmap.
2. **Handling of competitive information**: Prioritize facts that can be confirmed from public primary sources, and do not make conclusions about matters that cannot be confirmed.
3. **OSS-release positioning**: We do not make predictions about adoption, popularity, or market response; we limit the discussion to design positioning that can be confirmed from published materials.
This chapter inherits this scope and only **organizes the goals**.
#### 8.1.2 Aggregation structure
```text
[Observational facts] (Chapters 1–7)
   ↓
[Aggregation of architectural values] (§8.3)
[Consistency of design attitude] (§8.4)
[Ecosystem position] (§8.5)
[Aggregation of bench observation facts] (§8.6)
[Documentation and operational structure] (§8.7)
   ↓
[Objective positioning] (§8.8)
[Limitations of this report] (§8.10)
```

---

### 8.2 Aggregation of observed facts
The observed facts organized in each chapter are summarized in one line.
#### 8.2.1 Summary from Chapter 1 “Design Philosophy and Concepts”
- **Position**: A logging platform that **does not replace but extends stdlib `logging`, and is designed for production operations with zero runtime external dependencies.
- **Target Python**: 3.11 or higher, CPython 3.13/3.14 free-threaded build included in the design target
- **Design purpose**: Top priority is to operate as a common platform for the D ecosystem (widespread use is secondary)
- **Safe 6 axes**: startup / file / record・context / operational / concurrency・multiprocess / failure observability
- **5 Design Principles**: Reroute, don't rotate / Fail before it breaks / Start quick, ship as-is / Zero external runtime dependencies / Be honest about multiprocess behavior
- **19 architectural advantages** can be organized into 6 groups: "Does not depend on / Does not break / Does not deteriorate silently / Makes it explainable / Extends but does not replace / Completes locally"
#### 8.2.2 Summary from Chapter 2 “Specification and Design”
- **Physical module configuration**: 25 files + `mp/` namespace, public API entrances are only 2 files: `__init__.py` and `mp/__init__.py`
- **3-layer internal architecture**: Capture (logging compatible) / Transport (hand-off) / Sink (routing/hash/manifest). Responsibility boundaries remain unchanged in single/multiprocess
- **v23 system invariants 9 items**: Writer ownership / Writer drain / append-only routing / Capture-Transport-Sink / logging compatibility / Zero dependency / fail-safe, etc.
- **Three-tier configuration pipeline**: Environment variables > INI/dict > Strict merging of arguments + Fail-Fast + Sanctuary (diagnose/sens_kws/fmt instance)
- **5+6+1 term hierarchy for delivery status**: Lifecycle 5 / Terminal 6 / Policy qualifier 1. Only `unexpected_loss` is treated as a bug
- **4 absolute defense lines**: `MAX_IPC_LOG_TIMEOUT_SECONDS=3.0`, `CONTROL_PLANE_ACK_TIMEOUT_SEC=5.0`, `WRITER_STOP_WAIT_TIMEOUT_SEC=10.0`, `ipc_log_queue_maxsize` warning threshold 100000
#### 8.2.3 Summary from Chapter 3 “Usability”
- **Minimum startup code is 3 lines**: `ConfigureLogger(...)` + `GetLogger(...)` + `logger.info(...)`
- **Default values for all 26 arguments**: Minimum startup and production audit operation are expressed in the same API parameter space
- **stdlib migration**: 50–60% reduction in setup code lines, call site unchanged, third-party libraries such as SQLAlchemy/Django can participate without modification
- **3-layer pipeline × Change subject**: Arguments (developer) / INI (DevOps) / Environment variables (operator)
- **examples 17 files**: categorized into 6 learning paths (getting started / stdlib and ecosystem integration / Windows and service operations / application / audit and incident response / multiprocess)
- **CLI 3 command**: `init` / `ls` / `tail -f` (Compensate for Append-Only weakness by following transparent file switching)
- **multiprocess usage is 3 worker_model**: process / pool / executor (ProcessPoolExecutor only)
- **Coexistence with third-party**: structlog 2 pattern / OpenTelemetry trace correlation / stdlib third-party automatic co-joining
#### 8.2.4 Consolidation from Chapter 4 “Security”
- **Structurally eliminate supply chain paths**: Zero runtime external dependencies + Vendor-Agnostic core (no vendor imports such as OTel) + Apache 2.0
- **16 or more items verified at startup**: permissions / disk space / type conversion / custom level conflicts / environment variable interpretation (fail-fast in v23h)
- **`diagnose` triple guard**: Code path (no argument) / Configuration file path (INI ignored) / Boolean value notation ("1" only)
- **`sens_kws` Sanctuary + 12 built-in languages**: Cannot be set from environment variables, only `f_locals` route works (`logger.info()` message body is clearly excluded)
- **Integrity Verification**: SHA-256 sidecar (`sha256sum -c` compatible, relative path) + manifest + `os.replace()` atomic write
- **Active Explanation of Threat Model Boundaries**: HMAC out of scope, meaning of `UnexplainedLost`, Writer does not guarantee list
- **bounded shutdown contract (v23h)**: bounded wait → visible warning → process exits (physical guarantee with daemon=True)
#### 8.2.5 Summary from Chapter 5 “Detailed Analysis by Function”
- **Append-Only Routing 9 Mode**: `none` / `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / `cyclic_weekday` / `cyclic_month`
- **`max_count` branch of `size` / `count`**: Specified = cyclic overwrite / Not specified = upper limit reached The application stops at `OverflowError`
- **Generation management + self-repairability**: Purge/archive in separate thread in `backup_count > 0`, if it fails, retry at next switching timing
- **Integrity verification lock ordering**: `family_lock → manifest_lock` (reverse ordering prohibited). HashWorker runs on `_run_in_empty_context`
- **5 state lifecycle + RLock**: unconfigured / auto / explicit / configuring / shutting_down
- **multiprocess Writer**: Centralizes file ownership, routing, hash, manifest, purge, archive, and reopen
- **7 layers of delivery status + writer_reject 6 breakdown** (v23h): route / reconstruct / close_marker / sink / policy / format
- **TrackedQueue (v23h)**: native qsize fallback in OS name independent exception probe
- **free-threaded support**: GIL independent explicit lock + `f_locals` repr'd snapshot + empty Context start of internal thread
#### 8.2.6 Summary from Chapter 6 “Competitive Project Comparison”
- **No direct conflicts observed in the scope of this primary source investigation**: Design axes do not completely intersect with any of stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OpenTelemetry
- **Only 2 zero dependencies**: D-SafeLogger and picologging. **D-SafeLogger alone if limited to pure Python**
- **append-only routing**: No precedent in the Python ecosystem (present as options in Logback / Log4j2)
- **Integrity verification (SHA-256 sidecar + manifest)**: Not observed by other projects within the scope of this primary source investigation
- **Delivery status 7 layer classification**: Not observed in other projects within the scope of this primary source investigation
- **Explicit declaration of PEP 703 free-threaded support**: D-SafeLogger alone in the scope of this primary source investigation
- **Systematic merging rules for three-layer configuration pipeline**: D-SafeLogger alone in the scope of this primary source investigation
- **Direct response to known constraints stdlib official document**: Windows rename impossible (`logging.handlers` WatchedFileHandler clause) / multiprocess single file not supported (cookbook)
#### 8.2.7 Summary from Chapter 7 “Positioning at OSS Release”
- **Logical fit with six segments**: supply-chain focus / Windows server operations / audit and compliance / free-threaded migration consideration / stdlib-conservative usage / multiprocess audit
- **Options with four design axes that are different from other libraries**: "stdlib extension × pure Python × zero dependencies × append-only" / "parent-side writer × delivery state hierarchy classification" / "SHA-256 sidecar × manifest × `sha256sum -c` compatibility" / "PEP 703 explicit support × shared state explicit locking"
- **5 layers hard to reach due to design purposes**: DX complete redesign / speed first / distributed logging backend / SaaS observability / event causal chain
- **Can coexist with 5 configurations**: structlog / OpenTelemetry / logrotate / pytest caplog / third party stdlib `logging` library
- **5 common support axes in Japan and overseas**: Regulated industry tampering detection / supply chain requirements / stdlib existing asset protection / OpenTelemetry coexistence / free-threaded migration consideration
---

### 8.3 Synthesis of architectural value
The characteristics observed in Chapters 1 to 7 are organized into seven units of architectural value. This is not a list of individual functions, but a unit of value created by combining a group of functions.
#### 8.3.1 Value 1: Stable as an extension point for stdlib `logging`
Drop-in expansion via `logging.setLoggerClass()`, no use of `addLevelName()`, unchanged `record.levelname`, complete override of `QueueHandler.prepare()`, non-destructive handling of `logging.LogRecord`. By combining these, **the existing stdlib `logging`-based assets will not lose their prerequisites due to the existence of this library**.
#### 8.3.2 Value 2: Strengthen below file boundaries
Append-only routing, 9-mode routing strategy, generation management + self-healing, integrity verification, external rotation coexistence. These are responsible for the "layer below the handler entrance of stdlib `logging`" and **add production operation functions without changing the call site**.
#### 8.3.3 Value 3: Classify failures and make them explainable
7 layers of delivery status, `writer_reject` 6 breakdown, rate-limited stderr warning, Writer exit code, shutdown summary, bounded shutdown contract. These transform log missing into "explainable facts" rather than "silent gaps". The design in which only `unexpected_loss` is treated as a bug clarifies the operational alarm granularity.
#### 8.3.4 Value 4: Avoid structurally establishing accident patterns
`diagnose` triple guard, `sens_kws` sanctuary, `pg_name` sanitization, strict filename filtering, INI type conversion Fail-Fast, 5-state lifecycle, `mp.ConfigureLogger()` same process second `RuntimeError`, registry hash SHA-256 verification, bootstrap payload picklable spec limited. These prevent accident patterns such as "inadvertent mixing," "setting errors," and "ID diversion" from being established at the design level.
#### 8.3.5 Value 5: Protect host process with the absolute line of defense
`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0` / `ipc_log_queue_maxsize` warning threshold 100000. These internal constants cannot be overwritten by the user, and the logging mechanism structurally guarantees an upper limit on the length at which the host process is irreversibly hardened. In combination with daemon=True, "process exits" are made fail-safe.
#### 8.3.6 Value 6: Narrow the scope of responsibility and isolate it to external tools
HMAC is delegated to external tools, sidecar verification uses `sha256sum -c`, external rotation coexists with `logrotate`, log shipping is delegated to Fluent Bit / Vector / Filebeat, distributed tracing backend is out of scope. **Boundaries are actively drawn between the responsibilities that the library should take on and those that should be delegated to the OS/external tools**.
#### 8.3.7 Value 7: Extend but don't replace
structlog coexistence (2 patterns), OpenTelemetry trace correlation (`contextualize` + `LoggingHandler`), stdlib third party automatic co-joining, empty Context start of internal thread, `addLevelName()` not used. These can be observed as a combination of design attitudes that aim to be neutral towards other frameworks and other code.
---

### 8.4 Consistency of Design Attitude
When we summarize the "design attitude" observed individually in Chapters 1 to 7, the following eight axes are consistently observed throughout the entire library.
| Axis | Content | Observed location |
|---|---|---|
| **Structurally excluded** | "Accident patterns are not structurally established" | `diagnose` No argument / sens_kws No environment variable / pg_name Sanitize / 5-state life cycle / mp 2nd time `RuntimeError` |
| **Responsibility Separation** | "Keep responsibility boundaries harder than process boundaries" | Capture/Transport/Sink 3-layer separation / Responsibility unchanged with single-mp / Do not re-execute Capture semantics on the Writer side |
| **Failure classification** | "Classify abnormalities and do not allow silent failure" | Delivery status 7 layers / writer_reject 6 breakdown / rate-limited warning / shutdown summary |
| **Absolute line of defense** | "Protect host process with internal constants that cannot be overwritten by the user" | 4 timeout / queue size constants / daemon=True backstop |
| **Clarification of opt-in boundaries** | "Do not silently mix semantics in the same API" | Specify per-message visibility revocation in `writer_flush_batch>=2` |
| **Actively clarifying boundaries** | "Declaration of warranty and non-guarantee scope in advance in document" | HMAC outside scope / Meaning of `UnexplainedLost` / Writer does not guarantee / What Not To Claim |
| **Maintain standardness** | "Do not break the semantics of stdlib" | addLevelName() not used / record.levelname unchanged / QueueHandler.prepare() complete override |
| **Responsibility delegation** | "Separate the responsibility to the OS/external tools instead of keeping it in the library" | HMAC external delegation / `sha256sum -c` compatible / logrotate coexistence / log shipping is external |
These eight axes are not a coincidence of the v23k single edition, but are observed as a system of design decisions derived from the absolute conditions of Design Document §1 (``Complete compliance with the standard library'' and ``zero external dependencies'') and the Writer invariants of §12.1 (``Avoid silent loss/hang/fallback'').
---

### 8.5 Ecosystem position
Based on the summaries in Chapters 6 and 7, this library’s ecosystem position can be expressed in four propositions.
#### 8.5.1 Proposition 1: Direct competition is not observed.
As a result of checking the primary source for each design axis of the 8 major projects (stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OpenTelemetry SDK), we did not observe any project whose function/responsibility axis completely overlaps with this library. Each project champions a different axis (DX / structured front end / velocity differentiation / causal chain / SaaS integration / standard observability).
#### 8.5.2 Proposition 2: This library occupies the niche of "stdlib extension type × functional differentiation"
picologging is the same "stdlib extension type" but has different speed, and this library has different design (append-only / integrity verification / multiprocess writer / delivery status classification). Loguru/Logbook is a replacement type, structlog is a parallel type, and logfire/OTel is a bridge type, so the location of this library is unique within the scope of this primary source investigation.
#### 8.5.3 Proposition 3: stdlib is a direct response to formal known constraints
The WatchedFileHandler clause of `docs.python.org/3/library/logging.handlers.html` (Windows cannot be renamed) and `docs.python.org/3/howto/logging-cookbook.html` (multiprocess single file not supported, QueueListener separate process recommended) are restrictions and recommendations that are clearly stated in the official Python docs themselves. This library's append-only routing and parent-side Writer are positioned as a direct response to these.
#### 8.5.4 Proposition 4: Aim for coexistence rather than competition
structlog (coexist in 2 patterns) / OpenTelemetry Python (via `LoggingHandler`) / logrotate (`routing_mode='none'` + `ReopenLogFiles()`) / pytest caplog (stdlib compatible) / 3rd party `logging.getLogger()` library (auto co-join with `setLoggerClass`). All of these have structures that allow them to be used together, and their consistent design stance is "coexistence, not replacement."
---

### 8.6 Benchmark observation summary
Objectively organize the performance characteristics of this library from the selection session of `BENCHMARK.md` and `benchmarks/summary/`. **It is not an evaluation but an aggregation of observed values**.
#### 8.6.1 Single-process async (Python 3.14/GIL enabled, selected session)
- text: **51,554 msg/s**, p50 **16.7 µs**, p99 **39.6 µs**
- JSON: **52,081 msg/s**, p50 **16.7 µs**, p99 **36.8 µs**
#### 8.6.2 Single-process cell-winners (16 cells)
- D-SafeLogger async ranks first in throughput 8/16
- D-SafeLogger async is p50 1st place 12/16
- D-SafeLogger async outperforms D-SafeLogger sync in both throughput and p50 for all 16 cells
#### 8.6.3 Multi-process integrity profile
- 3 backend (D-SafeLogger / stdlib logging / loguru) × 96 raw runs with missing=0 / duplicates=0 / JSON parse failure=0 / route mismatch=0
- Under normal conditions, all 3 backends delivered the expected records without loss
#### 8.6.4 Multi-process performance profile
- D-SafeLogger sync has **63–75%** throughput of stdlib logging sync (75% on `root_p8`)
- stdlib logging ranks first in all throughput cells
- D-SafeLogger does not precede raw multiprocess throughput (clarified as a difference in specifications)
#### 8.6.5 Multi-process resilience profile
- D-SafeLogger generates classified loss/reject/drop fields in 12/12 summary line
- D-SafeLogger classifies and explains 12/12 summary line
- stdlib logging / loguru rows marked with `observability_gap` (contractually unclassifiable)
#### 8.6.6 What To Claim / What Not To Claim (`BENCHMARK.md`)
Boundaries that public bench analysis actively enumerates:
**What To Claim**:
- D-SafeLogger has zero runtime dependencies
- D-SafeLogger provides append-only file handling without rename/truncate rotation
- D-SafeLogger supports structured JSON logging and stdlib-compatible logger integration
- D-SafeLogger async is competitive in single-process logging and leads several low-latency cells
- D-SafeLogger multiprocess mode centralizes sink ownership in a Writer runtime
- D-SafeLogger multiprocess resilience profiling exposes classified delivery-state counters
**What Not To Claim**:
- Do not claim D-SafeLogger is always the fastest backend
- Do not claim D-SafeLogger multiprocess mode beats stdlib logging on raw throughput
- Do not claim multiprocess logging can never lose records under operational failure
- Do not claim sink outage, worker crash, or hard process termination is made impossible
- Do not mix diagnostic benchmark results with normal logging throughput results
**Observation**: The scope of bench performance claims and non-claims is **actively enumerated** in the document, and there is a consistent operational stance of avoiding excessive claims.
---

### 8.7 Documentation and operational structure
#### 8.7.1 Documentation structure
| Axis | Document | Number of lines (reference) |
|---|---|---|
| Entrance | `README.md` / `README_ja.md` | 217 lines each |
| Learning | `examples/01_*.md`〜`examples/17_*.md` | 17 files |
| Design | `docs/design/D_SafeLogger_Specification_v23k_full.md` | 2,477 lines |
| Design | `docs/design/D-SafeLogger_DetailedDesign_v23k.md` | 4,258 lines |
| Design | `docs/design/D-SafeLogger_TestDesign_v23k.md` | 135 lines |
| API | `docs/api/dsafelogger*.md` | Automatically generated |
| Operation | `TESTING.md` / `BENCHMARK.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | — |
#### 8.7.2 Quality Gate
- Official test baseline: 658 passed / 3 skipped (661 collected, `uv run pytest tests -v`, Python 3.14.3 / Windows). The skipped count can vary by OS because fork E2E tests are POSIX-only and Windows spawn E2E tests are Windows-only.
- Coverage: terminal total 87%, XML line-rate 88.97%, branch-rate 81.46%
- multiprocess tests / OTel/structlog coexistence tests are included in the official quality gate
- Type validation: public validation includes `mypy src`, `pyright src`, `pyright tests/typing_smoke`, and a 100% `pyright --verifytypes dsafelogger --ignoreexternal` completeness gate against the built wheel
- free-threaded build test procedure included (`PYTHON_GIL=0 uvx ...`)
- Internal synchronization verification on `scripts/check_design_docs_sync.py` and `scripts/generate_api_docs.py --check`
- Fixed public representative session with `benchmarks/summary/manifest.json`
#### 8.7.3 Release operation
- distribution name: `d-safelogger` (PyPI normalization)
- import name: `dsafelogger`
- License: Apache License 2.0
- `py.typed` included
- `pyproject.toml` Zero runtime dependency
- Distribution target is only under `src/dsafelogger/`
- Release target version: 0.2.1
- Latest pre-release review results: GO-with-fixes (2026-05-07)
#### 8.7.4 Characteristics of document operation
- Multilingual: README in Japanese and English, design document in Japanese, examples/API/operation guide in English
- Manually edited BENCHMARK.md (avoiding the "accident of automatic promotion of the last benchmark" by prohibiting automatic regeneration from runner)
- Public validation is separated into `TESTING.md`, benchmark interpretation into `BENCHMARK.md`, and contribution guidance into `CONTRIBUTING.md`.
---

### 8.8 Objective positioning
Based on the observed facts in this report as a whole, we have summarized the objectively descriptive position into 10 items.
#### 8.8.1 Architectural positioning
1. **Libraries that satisfy the combination of "stdlib extended type × pure Python × zero runtime dependency × append-only routing × integrity verification × parent-side multiprocess writer × delivery state 7-layer classification × free-threaded explicit support × 3-layer configuration pipeline" are not observed in the scope of this primary source investigation**.
2. **Design purpose is not "widespread dissemination" but "conformity to specific operational requirements"**: §1 of the design document clearly states that ``the top priority is to operate as a common base for the D ecosystem rather than the purpose of wide dissemination,'' and the multiprocess scope specification in §11.2 explicitly excludes remote aggregation / network protocols. This is consistent with a design attitude that prioritizes support for subset organizations.
3. **Although no direct feature conflicts are observed, this does not mean ``the strongest''**: Each major conflict (Loguru / structlog / picologging / Eliot / logfire / OpenTelemetry) champions a different axis and can coexist because their responsibility axes do not intersect. This library is positioned as a "champion of a specific axis."
#### 8.8.2 Consistency of design attitude
4. **The 8-axis design attitude is consistent throughout the library**: structural exclusion / separation of responsibilities / failure classification / absolute line of defense / opt-in boundary definition / active boundary definition / standardness maintenance / responsibility delegation. These are not a coincidence of the v23k single edition, but are observed as a system of design decisions derived from the absolute conditions of design document §1 and the Writer invariant conditions of §12.1.
5. **Guaranteed scope and non-guaranteed scope are actively specified in the document**: The HMAC outside scope, meaning of `UnexplainedLost`, Writer does not guarantee, and What Not To Claim sections are observed as an operational attitude to "prevent misuse due to excessive expectations."
#### 8.8.3 Supporting stdlib formal constraints
6. **Designed to directly respond to the known constraints stdlib official document**: Append-only routing and parent-side Writer function as direct responses to the inability to rename active logs on Windows (`logging.handlers` WatchedFileHandler clause) and non-support for multiprocess single files (cookbook).
#### 8.8.4 Summary of benchmark observations
7. **Single-process async selected session numbers**: text 51,554 msg/s, p50 16.7 µs / JSON 52,081 msg/s, p50 16.7 µs on Python 3.14 / GIL enabled. Out of 16 cells, throughput 1st place 8/16, p50 1st place 12/16.
8. **Multiprocess raw throughput is led by stdlib logging**: In `root_p8`, D-SafeLogger reaches 63-75% of stdlib throughput. `BENCHMARK.md` states this clearly as a design tradeoff reflecting fixed costs in the specification (IPC + Writer dispatch). The multiprocess value of this library is not raw throughput, but delivery-state observability.
9. **Classifies and explains 12/12 rows in the multiprocess resilience profile**: stdlib / loguru rows are marked with `observability_gap`. Delivery-state explainability is recorded as observability specific to this library.
#### 8.8.5 Documentation/quality operations
10. **Quality gate and internal synchronization verification scripts are in place**: 658 passed / 3 skipped on Python 3.14.3 / Windows (661 collected), coverage 87%, `mypy` / `pyright` / typing smoke / `pyright --verifytypes` 100% completeness gate, internal synchronization verification by `scripts/check_design_docs_sync.py` and `scripts/generate_api_docs.py --check`, public representative session fixation by `benchmarks/summary/manifest.json`. The skipped count can vary by OS. These are recorded as observable quality indicators when evaluating candidate libraries for introduction.
---

### 8.9 Summary of this chapter
D-SafeLogger v23k can be organized into the following overall picture:
1. **The units of architectural value are summarized in 7**: stdlib Stable as an extension point / Strengthen below the file boundary / Classify and explain failures / Prevent accident patterns from being established structurally / Protect the host process with an absolute line of defense / Narrowly divide the scope of responsibility into external tools / Extend but do not replace.
2. **The 8-axis design attitude is consistent throughout the library**: structural exclusion / separation of responsibilities / failure classification / absolute line of defense / opt-in boundary definition / active boundary definition / standardness maintenance / responsibility delegation.
3. **Position in the ecosystem can be summarized into 4 propositions**: Direct competition is not observed / stdlib extended type × Occupies a functionally differentiated niche / stdlib Direct response to known constraints of the official formula / Aiming for coexistence rather than competition.
4. **Benchmark observation facts are based on observability rather than raw throughput**: single-process async has competitive numbers, multiprocess is inferior to stdlib in raw throughput, but provides unique observability in terms of explainability of delivery status.
5. **Documentation/operation structure is maintained with internal synchronization verification and active definition of boundaries**: Over 9,547 lines of public documentation + automatically generated API + multilingual README + manifest fixed benchmark + quality gate test matrix.
These are a collection of observations that show that the absolute condition of design document §1, ``Complete compliance with the standard library, while achieving diagnostic capabilities that surpass third-party libraries (such as Loguru) and robustness that avoids fatal file locking problems in Windows environments, with zero external dependencies,'' has been reached in a consistent form across all layers of specification, design, implementation, testing, documentation, and benchmarking as of v23k.
---

### 8.10 Limitations of this report
This report has the following limitations. These are not deficiencies in this report, but items that were intentionally left outside the scope of the evaluation policy.
#### 8.10.1 Items not evaluated
- **Adoption/popularity prediction**: This white paper does not predict adoption rate, popularity, or response.
- **Improvement suggestions/Identification of issues**: This document is intended to explain and evaluate the current architecture as of v23k, and is not a replacement for the issue tracker/roadmap.
- **Predicting adoption rate**: Same as above.
- **GitHub stars / PyPI download Comparison of superiority and inferiority**: Although the popularity index was cited as a fact, it was not used for comparison on the design axis.
#### 8.10.2 Scope of primary source verification
- Competitive analysis (Chapter 6) is based on checking PyPI / GitHub / official docs / PEP as of **2026-05-09**. The situation may change due to future updates of each project.
- In particular, support for PEP 703 free-threaded is being rolled out in stages, and it is possible that other libraries will declare support for it in the next 6 months to 2 years (this chapter does not predict this).
#### 8.10.3 Technical areas not covered by this report
- **Details of the code quality of this library**: The implementation quality of individual functions and the presence or absence of bugs are separate code review areas, and this report is limited to the observed facts of public design documents, public benches, examples, and public API documents.
- **Details of behavior specific to a specific OS/specific Python version**: Only the scope specified in the public materials was covered.
- **Future version design prediction**: The direction of v24+ is not covered as the policy is to take the current v23k architecture as a given.
#### 8.10.4 Checking the scope of this report
- The purpose of this document is to organize and evaluate the **D-SafeLogger v23k architecture**. It (a) does not include improvement proposals or issue management, (b) limits competitive information to facts that can be confirmed from public primary sources, and (c) avoids predicting adoption rates, popularity, or reactions.
- Private planning materials were not referenced in all chapters, and `docs/design/` was used as the primary design document.
---

> **Main reference materials for this chapter**: Only the content referenced in Chapters 1 to 7 of this document. No new primary sources were added.

---

## Appendix A. Reference Policy
This white paper has been prepared in accordance with the following reference policy.
### A.1 Can be referenced (official/publicly available)
| Classification | Path |
|---|---|
| Public README | `README.md` / `README_ja.md` |
| Public bench analysis | `BENCHMARK.md` |
| Public bench raw data | `benchmarks/summary/*.md`, `benchmarks/summary/manifest.json`, `benchmarks/results/<selected>/summary.{md,json}` |
| Public design document | `docs/design/D_SafeLogger_Specification_v23k_full.md` (2,477 lines) |
| Public design document | `docs/design/D-SafeLogger_DetailedDesign_v23k.md` (4,258 lines) |
| Public design document | `docs/design/D-SafeLogger_TestDesign_v23k.md` (135 lines) |
| Public API Documentation | `docs/api/dsafelogger*.md` |
| Publication Guide | `TESTING.md` / `CONTRIBUTING.md` / `CHANGELOG.md` |
| License | `LICENSE` (Apache License 2.0) |
| Metadata | `pyproject.toml`, `MANIFEST.in`, `uv.lock` |
| Public examples | `examples/01_*.md` ~ `examples/17_*.md` (17 files) |
| Implementation body | `src/dsafelogger/*.py` (25 files + `mp/`) |
| Public test | `tests/test_*.py` |
### A.2 Cannot be referenced (handled as unofficial/deleted)
- Private planning materials
- `BENCHMARK_anomaly_*.md` / `BENCHMARK_legacy_*.md` (old version save file)
- `*.zip` / `_*_extracted/` (scratch/expanded directory)
- `App.log` / `dist/` / `src/D_SafeLogger.egg-info/` (runtime/build artifacts)
### A.3 Primary Source Matching Policy (Chapter 6)
For the latest specifications and status of competing projects, the following primary source is obtained from `WebFetch` / `WebSearch`, and the URL is specified in the text (confirmed date 2026-05-09):
- **PyPI** (`pypi.org/project/<name>/`): Latest version, dependencies, metadata
- **GitHub**: README・Last release date・Issue status
- **Official docs** (Read the Docs / Official for each project)
- **PEP** (`peps.python.org/pep-XXXX/`): Specifications
- **CPython doc** (`docs.python.org/3/library/logging.html` and others)
Claims that cannot be corroborated by primary sources are not accepted.
---

## Appendix B. Primary Source List (as of 2026-05-09)
Enumerate all primary source URLs referenced in Chapter 6.
### B.1 D-SafeLogger Publication materials
-`docs/design/D_SafeLogger_Specification_v23k_full.md`
-`docs/design/D-SafeLogger_DetailedDesign_v23k.md`
-`docs/design/D-SafeLogger_TestDesign_v23k.md`
- `docs/api/dsafelogger*.md`
- `README.md` / `README_ja.md`
-`BENCHMARK.md`
- `TESTING.md` / `CONTRIBUTING.md` / `CHANGELOG.md`
- `examples/01_*.md` ~ `examples/17_*.md`
- `LICENSE` / `pyproject.toml` / `MANIFEST.in`
### B.2 PyPI (Package Metadata)
- `pypi.org/pypi/loguru/json` — Loguru 0.7.3 (2024-12-06)
- `pypi.org/pypi/structlog/json` — structlog 25.5.0 (2025-10-27)
- `pypi.org/pypi/picologging/json` — picologging 0.9.3
- `pypi.org/pypi/eliot/json` — Eliot 1.18.0 (2026-05-07)
- `pypi.org/pypi/Logbook/json` — Logbook 1.9.2
- `pypi.org/pypi/logfire/json` — logfire 4.32.1
- `pypi.org/pypi/opentelemetry-sdk/json` — OpenTelemetry SDK 1.41.1
### B.3 Official Documentation
- `docs.python.org/3/library/logging.html` — Python 3.14 logging module
- `docs.python.org/3/library/logging.handlers.html` — handlers (Windows constraints of WatchedFileHandler, etc.)
- `docs.python.org/3/howto/logging-cookbook.html` — multiprocess recommended pattern
- `docs.python.org/3/whatsnew/3.13.html` — Python 3.13 What's New
- `loguru.readthedocs.io/en/stable/index.html` — Loguru official docs
- `www.structlog.org` — structlog official docs
- `eliot.readthedocs.io/en/stable/` — Eliot official docs
- `logbook.readthedocs.io/en/stable/` — Logbook official docs
- `microsoft.github.io/picologging/` — picologging official docs
- `pydantic.dev/docs/logfire/` — logfire official docs
- `opentelemetry.io/docs/specs/otel/logs/` — OpenTelemetry Logs Specification
- `opentelemetry.io/docs/languages/python/instrumentation/` — OpenTelemetry Python instrumentation
### B.4 GitHub repository
- `github.com/Delgan/loguru` — Loguru
- `github.com/hynek/structlog` — structlog
- `github.com/microsoft/picologging` — picologging
- `github.com/itamarst/eliot` — Eliot
- `github.com/getlogbook/logbook` — Logbook
- `github.com/pydantic/logfire` — logfire
- `github.com/open-telemetry/opentelemetry-python` — OpenTelemetry Python SDK
### B.5 PEP
- `peps.python.org/pep-0703/` — PEP 703: Making the Global Interpreter Lock Optional in CPython (Accepted 2023-10-24)
---

## Appendix C. Glossary
We will organize the D-SafeLogger-specific terms that frequently appear in this white paper.
### C.1 Architecture
| Terminology | Meaning |
|---|---|
| **Capture / Transport / Sink 3 layers** | Internal architectural responsibility separation. Capture = log generation (logging compatible), Transport = forwarding, Sink = output (routing/hash/manifest) |
| **Append-Only Routing** | A method of switching generations by opening a new file name without rename / truncate |
| **Drop-in Replacement** | An API-compatible replacement method that replaces the standard `logging.Logger` with `DSafeLogger` from this library using `logging.setLoggerClass()` |
| **Vendor-Agnostic Principle** | Design principle of not including vendor-specific imports in the core module (`src/dsafelogger/`) |
### C.2 Concurrency/Multiprocess
| Terminology | Meaning |
|---|---|
| **`dsafelogger.mp`** | Multiprocess public API namespace |
| **client process** | Process that makes log calls (including both main and worker) |
| **Writer runtime** | Internal process that owns the file sink. Receive `LogEvent` from client via IPC |
| **`ctx`** | Opaque and picklable bootstrap object for client to attach to Writer |
| **log plane** | Unidirectional path carrying normal log `LogEvent` (based on `multiprocessing.Queue`) |
| **control plane** | request/ack route handling reopen / attach / detach / stop / status |
| **active client registry** | List of client processes being attached managed on the Writer side |
| **TrackedQueue** | log plane queue implementation. `super().qsize()` native fallback with exception probe (v23h) |
### C.3 Delivery status (§12.3)
| Terminology | Meaning |
|---|---|
| `attempted` | Log call passed by user code to logger |
| `accepted` | Level judgment and client filter passed, and transport assumed delivery responsibility |
| `enqueued` | accepted log submitted to queue |
| `delivered_per_sink` | Pass the completion point of the flush contract on target sink |
| `delivered` | `delivered_per_sink` is established for all required sink set |
| `rejected` | Reject before accepting delivery responsibility (timeout / closed / writer unavailable, etc.) |
| `dropped` | Discarded after accepted or at local queue stage (reflected in counter / warning / summary) |
| `writer_reject` | Determined as undeliverable by route / sink / writer-side policy after reaching Writer |
| `partial_delivered` | Only part of the required sink set is reached |
| `unexpected_loss` | accepted The state where it was done but disappeared for no reason. **Treat as a design or implementation bug** |
| `overload_shed` | qualifier for explicit destruction based on bounded queue / timeout policy |
### C.4 Internal constants (absolute line of defense)
| Constant | Value | Meaning |
|---|---|---|
| `MAX_IPC_LOG_TIMEOUT_SECONDS` | 3.0 seconds | Absolute upper limit for waiting to send to log plane queue |
| `CONTROL_PLANE_ACK_TIMEOUT_SEC` | 5.0 seconds | control plane ACK wait upper limit |
| `WRITER_STOP_WAIT_TIMEOUT_SEC` | 10.0 seconds | bounded wait for log_thread / control_thread join during shutdown |
| `ipc_log_queue_maxsize` warning threshold | 100000 | stderr warning if specified above (initialization continues) |
### C.5 5 State Life Cycle
| Status | Meaning |
|---|---|
| `unconfigured` | Initial state |
| `auto` | `GetLogger()` Preceding auto-fire initialized state |
| `explicit` | State where `ConfigureLogger()` is explicitly called from application code |
| `configuring` | `ConfigureLogger` Internal state during execution (`_lifecycle_lock` held) |
| `shutting_down` | `_shutdown()` Internal state during execution |
### C.6 Safe 6 Axis (README)
| Axis | Contents |
|---|---|
| **Startup safety** | Reject invalid settings and unwritable paths during setup |
| **File safety** | append-only routing without rename/truncate + SHA-256 sidecar |
| **Record / context safety** | Snapshot at hand-off on the producer side; `sens_kws` masking during diagnostic snapshots and Writer-side formatting |
| **Operational control** | Overriding without rebuilding with environment variables |
| **Concurrency / multiprocess safety** | parent-side Writer owns sink, bounded queue + explicit timeout |
| **Failure observability** | Classification of `KnownRejected` / `KnownDropped` / `UnexplainedLost` |
---

## Appendix D. Document Preparation
This white paper is based on public primary sources such as `README.md` / `README_ja.md`, public design documents (`docs/design/`), tests, benchmark artifacts of `examples/`, `BENCHMARK.md`, `benchmarks/summary/`, package metadata of `pyproject.toml`, etc. Created using assisted analysis.
The final content has been confirmed and adopted by the project maintainer, and the original specifications, behavior, and verification results are the following artifacts:
- Source code: `src/dsafelogger/`
- Test: `tests/`
- Public design document: `docs/design/D_SafeLogger_Specification_v23k_full.md` / `D-SafeLogger_DetailedDesign_v23k.md` / `D-SafeLogger_TestDesign_v23k.md`
- Public benchmark artifacts: `BENCHMARK.md`, `benchmarks/summary/*.md`, `benchmarks/results/<selected>/`
- Public API reference: `docs/api/`
If there is a discrepancy between this document and those originals, the originals take precedence.
### Document Provenance (English)
This whitepaper was prepared with AI-assisted analysis based on the public project sources, including `README.md` / `README_ja.md`, the public design documents under `docs/design/`, the test suite, the `examples/` directory, `BENCHMARK.md`, the benchmark artifacts under `benchmarks/summary/`, and package metadata such as `pyproject.toml`.
The final content was reviewed and accepted by the project maintainer. The source code, tests, design documents, and benchmark artifacts remain the source of truth. In case of any discrepancy between this whitepaper and those primary artifacts, the primary artifacts take precedence.
---

## end of document
This document organizes and evaluates the current architecture as of D-SafeLogger v23k.
- **Does not include improvement suggestions**: This document is intended to explain and evaluate the architecture as of v23k, and is not a replacement for the issue tracker/roadmap.
- **Competitive information is based on public primary sources**: Primary source confirmed as of 2026-05-09. The situation may change with future updates.
- **Do not predict adoption rate, popularity, or response**: Limited to organizing design positioning.
Design predictions for future versions (v24+), implementation quality reviews of individual functions, and detailed behavior specific to specific OS/Python versions are outside the scope of this document.
---

> This white paper is published under the Apache License 2.0. This is the same license as this library itself.
> © 2026 D-SafeLogger contributors

## v23k Multiprocess Observability Note

The v23k multiprocess API covers not only Writer-owned sinks but also delivery-state accountability in environments where stderr is unavailable. `runtime_warning_path` preserves runtime and transport warnings as JSONL, and `shutdown_report_path` preserves the final accounting snapshot as JSON. `mp.GetDeliveryStatus()` exposes an in-process `DeliveryStatus` snapshot through the public API.

This observability layer is separated from the application log pipeline. Sink failures and control-plane failures are not re-injected into application handlers; a dedicated warning queue and fallback JSONL files avoid recursive logging. `diagnose` remains application-record diagnostics, runtime warnings describe logging-runtime failures, and delivery status/report describe delivery accounting.

The multiprocess runtime assumes Writer and workers use the same installed package version. It does not claim impossible durability under every abnormal failure; instead it makes delivery state observable through accepted, delivered, partial, known rejected, known dropped, unexplained lost, and source-separated breakdown fields.
