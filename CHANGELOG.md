# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Multiprocess observability artifacts: `mp.GetDeliveryStatus()` / `DeliveryStatus`, `runtime_warning_path` JSON Lines output with per-pid worker fallback files, and `shutdown_report_path` JSON shutdown reports.
- Tests for runtime warning output, shutdown report generation, public delivery-status snapshots, writer/worker accounting invariants, and runtime-vs-shutdown missing-detach semantics.
- v23k public design documents and supplements for delivery status schema, runtime warning design, and multiprocess observability test coverage.

### Changed
- Multiprocess resilience benchmark summaries now use the public `mp.GetDeliveryStatus()` schema, keep `partial_delivered` separate from `known_rejected`, include writer/worker drop/reject breakdowns, and record runtime warning fallback files plus shutdown-report crash fields.
- Public multiprocess docs now describe console-less observability through status snapshots, runtime warning JSON Lines, and shutdown report JSON instead of relying on stderr-only guidance.

## [0.2.2] - 2026-05-21

### Added
- Type validation as a CI quality gate: `mypy` and `pyright` are now required dev dependencies; `publication-checks` runs `uv run mypy src` and `uv run pyright src` on every push.
- `scripts/install_built_wheel.py` — helper for installing the freshly built wheel into the uv-managed venv before running `pyright --verifytypes` against the packaged module (rather than the editable source tree).
- `scripts/check_type_completeness.py` — threshold gate for `pyright --verifytypes dsafelogger --ignoreexternal`; CI now requires 100% public type completeness from the built wheel.
- `scripts/check_distribution_contents.py` — standalone script replacing the inline heredoc in `publish.yml`; adds `dsafelogger/py.typed` (wheel) and `src/dsafelogger/py.typed` (sdist) to required-path checks. Also wired into `ci.yml` `publication-checks`.
- `tests/typing_smoke/public_api_smoke.py` — pyright-only smoke test covering `ConfigureLogger`, `GetLogger`, `contextualize`, and `mp.ConfigureLogger` / `mp.GetWorkerInitializer` from a user import perspective. The directory is named `typing_smoke` (not `typing`) to avoid shadowing the stdlib `typing` module in spawn child processes. Not collected by pytest (filename does not match `test_*.py`); checked by `uv run pyright tests/typing_smoke` in `publication-checks`.
- `dsafelogger._handler.ReopenableHandler` — `@runtime_checkable` Protocol that narrows `logging.Handler` references to those exposing `reopen()`; replaces internal `hasattr(h, 'reopen')` checks for static type checking.

### Changed
- `dsafelogger._pipeline.ResolvedConfig.sensitive_keywords` now defaults to `BUILTIN_SENSITIVE_KEYWORDS` directly (previously `field(default_factory=frozenset)`). Behaviour is preserved by the existing `or BUILTIN_SENSITIVE_KEYWORDS` consumer fallback; the API docs now show the concrete default value rather than `<factory>`.
- `dsafelogger._mp_protocol.LogEvent` TypedDict fields `process`, `processName`, `thread`, `threadName` are now `int | None` / `str | None`, aligning with stdlib `logging.LogRecord` semantics (None is a legal value for these attributes).
- `dsafelogger._formatter.DSafeFormatter.__init__` `style` parameter is now typed `Literal['%', '{', '$']` instead of `str`, matching `logging.Formatter`.

### Fixed
- `dsafelogger._routing.NoneStrategy.advance()` now returns the current path instead of implicitly returning `None`, satisfying its `Path` return-type contract (no observable behaviour change; `should_switch()` always returns `False` so the method is unreachable in production).
- `dsafelogger._cli` tail follow loop asserts that the open file handle is non-`None` before reuse (defensive narrowing; the assert is unreachable in normal execution).
- `dsafelogger._shutdown()` acquires the root logger reference before the `try` block so the `finally` block always has it available, even if an exception is raised before the original assignment site.

### Internal
- Removed 19 stale `# type: ignore[...]` comments that mypy 2.1 no longer requires.
- Annotated 4 previously untyped functions (`_levels._make_log_method`, `_color.ColorStreamHandler.__init__`, `_transport.TransportFactory.create`).
- `dsafelogger._mp_queue.TrackedQueue.__getstate__` / `__setstate__` are now explicitly marked `# type: ignore[override]` with a comment documenting the intentional `_QueueState` extension; cross-platform `qsize()` and `empty()` are coerced via `int(...)` / `bool(...)` to satisfy `warn_return_any`.
- `dsafelogger._mp_attach._validate_attach_ack` and `dsafelogger.mp._validate_bootstrap_ready_ack` now accept `ControlAck` TypedDict directly (previously `dict[str, Any]` / `dict[str, object]`).
- `pyproject.toml` adds `[tool.pyright]` (basic mode, `include = ["src"]`).
- `TESTING.md` gains a Type Validation section describing the local-green-before-push policy, recorded versions, and the private module surface rule.
- `README.md` / `README_ja.md` typing bullet updated to mention the CI type-check gate.
- `CONTRIBUTING.md` adds `uv run mypy src` / `uv run pyright src` to the required PR pre-flight commands and documents the private module surface policy.
- Public v23j design documents now describe the 0.2.2 type-validation gate, including source typing, `tests/typing_smoke`, built-wheel verifytypes, and the stdlib `typing` shadowing guard.
- API docs regenerated for `_color`, `_formatter`, `_handler`, `_mp_attach`, `_pipeline`.

## [0.2.1] - 2026-05-20

### Fixed
- Apply resolved `sens_kws` / `sens_kws_replace` to diagnostic local-variable snapshots across sync text, sync structured, async snapshot, and multiprocess Writer formatter paths.
- Preserve async producer-side diagnostic frame snapshots in text diagnostic output.
- Align daily routing examples with the implemented `YYYYMMDD` filename suffix.

### Changed
- Updated example tests to match the documented runnable examples for migration, web API, long-running service, compliance audit, production debugging, async performance, multiprocess logging, CLI operations, OpenTelemetry, structlog, and container collector coexistence scenarios.
- Updated public docs, API docs, and test/coverage baselines for the 0.2.1 patch release.

### Verified
- Full local validation on Python 3.14.3 / Windows: `658 passed, 3 skipped` (`661` collected).
- Coverage validation regenerated `coverage.xml`: terminal total `87%`, line-rate `88.97%`, branch-rate `81.46%`.
- API docs, design-doc sync, and whitespace checks pass; `git diff --check` reports only CRLF/LF warnings.

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
