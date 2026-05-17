# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-05

### Added
- Formal multiprocess public API under `dsafelogger.mp`, including `ConfigureLogger`, `AttachCurrentProcess`, `DetachCurrentProcess`, `GetLogger`, `GetWorkerInitializer`, and `ReopenLogFiles`.
- Writer-runtime multiprocess architecture with separate log plane and control plane, CloseMarker-based drain, explicit attach/detach, and bounded shutdown behavior.
- Classified multiprocess delivery-state counters for route/reconstruct/close-marker/sink/policy rejects, partial delivery, best-effort failures, timeout drops, overload shed, and drain-deadline loss.
- `TrackedQueue` for qsize-visible multiprocess log queues with platform fallback.
- Multiprocess comparison benchmark runner at `benchmarks/run_multiprocess_compare_v23a.py` with integrity, performance, overload, and resilience profiles.
- Benchmark summary manifest workflow via `benchmarks/summary/manifest.json` and `benchmarks/update_summary.py`.
- Generated benchmark summary documents under `benchmarks/summary/` while keeping `BENCHMARK.md` manually edited.
- `optional_integration` pytest marker for OpenTelemetry and structlog coexistence tests while keeping them in the official full test run.
- v23j public design documents under `docs/design/` reflecting formal MP, dev full-test policy, manifest-based benchmark publication, and strict invalid-configuration handling.
- Shared v23j configuration validation for single-process, module-specific, and multiprocess file sinks.
- Generated API documentation under `docs/api/` with `scripts/generate_api_docs.py --check`.
- Public design-document readiness check via `scripts/check_design_docs_sync.py`.
- Multiprocess and external-rotation tutorials covering `dsafelogger.mp` and `ReopenLogFiles()`.

### Changed
- Updated `README.md`, `README_ja.md`, `TESTING.md`, and `BENCHMARK.md` to describe the current v23j design, test policy, benchmark interpretation, and formal multiprocess support.
- Invalid routing/generation/hash combinations are now fail-fast `ValueError` cases instead of warnings or silent no-ops.
- `structured=True` is mutually exclusive with `fmt`, `file_fmt`, and `console_fmt` after all config layers are merged.
- `file_fmt` and `console_fmt` are now accepted by the single-process API and INI/config_dict loader, matching the public design docs.
- Multiprocess module-specific levels are propagated to attached worker loggers.
- Multiprocess spawn integration tests now use the same multiprocessing context for Writer IPC primitives and worker process creation.
- Multiprocess log queue creation now classifies platform-rejected `ipc_log_queue_maxsize` values as `ValueError` before Writer sinks are started, while preserving runtime errors for non-validation OS failures.
- Tests no longer depend on `multiprocessing.Queue.empty()` for correctness.
- Benchmark runners now write session artifacts only; they no longer regenerate top-level `BENCHMARK.md`.
- Official testing policy is now `uv sync --group dev` followed by the full `uv run pytest tests -v` run.
- Package metadata version and public `dsafelogger.__version__` are both `0.2.0`; project classifier is now Beta.
- Package license metadata now uses SPDX `license = "Apache-2.0"` and `license-files = ["LICENSE"]`.
- GitHub CI now checks generated API docs, design-document sync, benchmark summaries, and package build output.
- PyPI publish workflow now verifies tag/version consistency and repeats publication preflight checks before publishing.
- GitHub CI now includes Ubuntu free-threaded CPython `3.13t` and `3.14t` test jobs with `PYTHON_GIL=0`.

### Verified
- Full local v23j validation on Python 3.14.3 / Windows: `651 passed, 3 skipped` (`654` collected). Skip counts can vary by platform because fork tests are POSIX-only and Windows spawn tests are Windows-only.
- Targeted v23j configuration validation: `256 passed` across configure, routing, INI, reopen, and MP integration tests.
- Coverage validation regenerated `coverage.xml`: terminal total `86%`, line-rate `88.49%`, branch-rate `80.53%`.
- Targeted regression validation for MP runtime, MP integration, OpenTelemetry, and structlog tests: `91 passed`.
- Benchmark summary manifest generation and `--check` verification pass.

## [0.1.0] - 2026-04-03

### Added
- Initial release
- 3-layer configuration pipeline (Environment → INI/Dict → Arguments)
- 9 routing strategies (none, daily, hourly, min_interval, startup_interval, size, count, cyclic_weekday, cyclic_month)
- Append-only file handler (Windows lock-safe)
- SHA-256 integrity verification with sidecar files and manifest
- Structured JSON Lines output
- Diagnostic formatter with f_locals expansion and sensitive data masking
- ANSI color console output with customizable palette
- Async logging mode with context-preserving QueueHandler
- Custom log level registration with `register_level()`
- `contextualize()` context manager for structured log context
- CLI tool (`dsafelogger init/ls/tail -f`)
- Free-threaded Python (3.13t/3.14t) support with explicit locks
- Per-module log level and file routing
- INI file and dict-based configuration
- Safe shutdown with worker thread join
- Complete standard library `logging` compatibility
