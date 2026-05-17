# Test Execution Guide

D-SafeLogger's official quality gate is the full test suite with the `dev` dependency group installed. The library runtime remains dependency-free; tests intentionally use development dependencies such as `pytest`, `pytest-timeout`, OpenTelemetry, and structlog.

## Prerequisites

Install [uv](https://docs.astral.sh/uv/):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install the development dependency group:

```bash
uv sync --group dev
```

## Official Test Command

```bash
uv run pytest tests -v
```

Current v23j local validation on Python 3.14.3 / Windows:

```text
651 passed, 3 skipped
654 collected
```

The collected test count is the baseline. The number of skipped tests is platform-dependent because fork E2E tests are POSIX-only and Windows spawn E2E tests are Windows-only.

Latest coverage validation generated `coverage.xml` on Python 3.14.3 / Windows:

```text
TOTAL coverage: 86%
XML line-rate: 88.49%
XML branch-rate: 80.53%
```

`coverage.xml`, `.coverage`, and `htmlcov/` are local/CI artifacts and are ignored by `.gitignore`; keep coverage numbers in documentation, not the generated files themselves.

OpenTelemetry and structlog coexistence tests are part of the official full test run. They are not skipped silently when the official `dev` dependency group is installed.

## Concise Local Run

```bash
uv run pytest tests -q
```

## Coverage

```bash
uv run pytest tests -v --cov=dsafelogger --cov-report=term-missing
uv run pytest tests --cov=dsafelogger --cov-report=xml:coverage.xml
uv run pytest tests --cov=dsafelogger --cov-report=html:htmlcov
```

## Optional Integration Marker

OpenTelemetry and structlog tests carry the `optional_integration` marker for diagnostic selection only.

Official release quality is based on the full test run, not on a reduced marker selection.

```bash
# Run only optional integration tests
uv run pytest tests -v -m optional_integration

# Temporarily exclude optional integration tests for local troubleshooting
uv run pytest tests -v -m "not optional_integration"
```

## Targeted Test Examples

```bash
# Single file
uv run pytest tests/test_mp_runtime.py -v

# Single class
uv run pytest tests/test_routing.py::TestSizeStrategy -v

# Single test
uv run pytest tests/test_routing.py::TestSizeStrategy::test_overflow_error -v

# Keyword filter
uv run pytest tests -k "mp_context" -v

# Stop on first failure
uv run pytest tests -x -v
```

## Test Areas

| Area | Representative files |
|---|---|
| Async and transport | `tests/test_async.py`, `tests/test_transport.py` |
| CLI | `tests/test_cli.py` |
| Configuration pipeline | `tests/test_configure.py`, `tests/test_ini_loader.py`, `tests/test_env_parser.py`, `tests/test_merge.py` |
| Context and logger API | `tests/test_context.py`, `tests/test_getlogger.py`, `tests/test_logger.py` |
| Formatting and structured output | `tests/test_formatter.py`, `tests/test_mp_formatter.py` |
| File handling and routing | `tests/test_handler.py`, `tests/test_routing.py`, `tests/test_reopen.py` |
| Integrity and retention | `tests/test_integrity.py`, `tests/test_purge.py` |
| Diagnostics and masking | `tests/test_diagnose.py` |
| Custom levels | `tests/test_levels.py` |
| Multiprocess unit tests | `tests/test_mp_attach.py`, `tests/test_mp_configure.py`, `tests/test_mp_control.py`, `tests/test_mp_runtime.py` |
| Multiprocess E2E | `tests/test_mp_integration.py`, `tests/test_mp_fork.py`, `tests/test_mp_spawn_windows.py` |
| Third-party coexistence | `tests/test_opentelemetry.py`, `tests/test_structlog.py` |
| Branch coverage edge cases | `tests/test_coverage_boost.py` |

## Multiprocess Test Policy

`dsafelogger.mp` is a formal feature, so multiprocess tests are part of the standard quality gate.

Important expectations:

- Spawn E2E tests must use the same `multiprocessing` context for `mp.ConfigureLogger(..., mp_context=ctx)` and worker creation.
- Fork E2E tests are POSIX-only and are skipped on Windows.
- Windows spawn tests are Windows-only and are skipped elsewhere.
- Tests must not rely on `multiprocessing.Queue.empty()` for correctness. Use timeout-based `get()` or fake/recording queues instead.
- CloseMarker drain, control-plane ACKs, backpressure, reject counters, partial delivery, and bounded shutdown warning paths are covered by MP tests.

## Free-Threaded Python

GitHub Actions runs Ubuntu free-threaded CPython `3.13t` and `3.14t` jobs with `PYTHON_GIL=0`.
Windows and macOS free-threaded validation remains a manual compatibility check for now.

For local CPython free-threaded builds, run with GIL disabled where available:

```powershell
# PowerShell
$env:PYTHON_GIL = "0"
uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v
```

```bash
# Bash
PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v
```

OpenTelemetry SDK dependencies may not be safe on every free-threaded build. The OpenTelemetry test module contains a module-level skip for known unsafe free-threaded imports.

## CI Matrix

GitHub Actions runs the full dev-group test suite across:

- OS: Ubuntu, Windows, macOS
- Python: 3.11, 3.12, 3.13, 3.14

GitHub Actions also runs a free-threaded compatibility job on Ubuntu:

- Python: 3.13t, 3.14t
- Environment: `PYTHON_GIL=0`

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

The CI workflow also runs publication checks on Ubuntu/Python 3.13:

```bash
uv run python scripts/generate_api_docs.py --check
uv run python scripts/check_design_docs_sync.py
uv run python benchmarks/update_summary.py --check
uv build
```

The publish workflow repeats these checks, verifies the git tag matches the package version, runs the full test suite, and only then publishes.

## Documentation Checks

Regenerate API docs after public API or docstring changes:

```bash
uv run python scripts/generate_api_docs.py
uv run python scripts/generate_api_docs.py --check
```

Public design documents live under `docs/design/`. Verify the selected v23j design documents with:

```bash
uv run python scripts/check_design_docs_sync.py
```

## Benchmark Checks

Benchmarks are not part of the normal pytest suite.

```bash
uv sync --group benchmark
uv run python benchmarks/run_benchmark.py
uv run python benchmarks/run_multiprocess_compare_v23a.py --repo-root . --profile resilience_profile --messages 100 --repeat 1
```

Published benchmark summaries are generated from the selected-session manifest:

```bash
uv run python benchmarks/update_summary.py
uv run python benchmarks/update_summary.py --check
```

`BENCHMARK.md` is manually edited and is not generated by benchmark runners.
