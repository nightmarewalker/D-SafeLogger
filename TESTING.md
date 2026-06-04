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

Current v23k local validation on Python 3.14.3 / Windows:

```text
749 passed, 3 skipped
752 collected
```

The collected test count is the baseline. The number of skipped tests is platform-dependent because fork E2E tests are POSIX-only and Windows spawn E2E tests are Windows-only.

Latest coverage validation generated `coverage.xml` on Python 3.14.3 / Windows:

```text
TOTAL coverage: 87%
XML line-rate: 89.17%
XML branch-rate: 82.02%
```

`coverage.xml`, `.coverage`, and `htmlcov/` are local/CI artifacts and are ignored by `.gitignore`; keep coverage numbers in documentation, not the generated files themselves.

OpenTelemetry and structlog coexistence tests are part of the official full test run. They are not skipped silently when the official `dev` dependency group is installed.

Examples 18-20 use optional ecosystem packages (`tqdm`, Rich, and Sentry SDK).
They are skipped by `pytest.importorskip` in a dev-only environment and are
officially guaranteed by the dedicated examples dependency group:

```bash
uv sync --group dev --group examples
uv run pytest tests/examples/test_18_console_progress_coexistence.py tests/examples/test_19_sentry_coexistence.py tests/examples/test_20_testing_and_warnings.py -v
```

The Qt GUI example is optional and has a separate dependency group because
PySide6 is large and GUI event-loop support is platform-sensitive:

```bash
uv sync --group dev --group gui
uv run pytest tests/examples/test_23_gui_logging_qt.py -v --timeout=30
```

Example 22 is docs-only. Remote cloud delivery depends on credentials,
network access, quota state, and backend ingestion, so it is documented with
`<!-- example-test: docs-only; ... -->` markers instead of a pytest module.

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
| Multiprocess observability | `tests/test_runtime_warning.py`, `tests/test_shutdown_report.py`, `tests/test_delivery_status_api.py` |
| Third-party coexistence | `tests/test_opentelemetry.py`, `tests/test_structlog.py` |
| Branch coverage edge cases | `tests/test_coverage_boost.py` |

Diagnostic masking coverage must include both component-level checks and
configuration-to-output integration checks. In particular, `sens_kws` and
`sens_kws_replace` are validated through `ConfigureLogger(...)` into sync text,
sync structured, async snapshot, and multiprocess Writer formatter paths.

## Multiprocess Test Policy

`dsafelogger.mp` is a formal feature, so multiprocess tests are part of the standard quality gate.

Important expectations:

- Spawn E2E tests must use the same `multiprocessing` context for `mp.ConfigureLogger(..., mp_context=ctx)` and worker creation.
- Fork E2E tests are POSIX-only and are skipped on Windows.
- Windows spawn tests are Windows-only and are skipped elsewhere.
- Tests must not rely on `multiprocessing.Queue.empty()` for correctness. Use timeout-based `get()` or fake/recording queues instead.
- CloseMarker drain, control-plane ACKs, backpressure, reject counters, partial delivery, runtime warning JSON Lines/fallback files, shutdown report JSON, delivery status snapshots, and bounded shutdown warning paths are covered by MP tests.

## Example Documentation Policy

When an example markdown file (`examples/*.md`) adds or changes an executable code block that represents a supported user workflow, update the matching `tests/examples/test_*.py` file in the same change. Existing example tests passing is not sufficient when the changed code path is new.

Checklist for reviewers:

- Does `examples/*.md` have a new or changed code block?
- If yes, is the corresponding `tests/examples/test_*.py` updated?
- If the code block is illustrative only (not a runnable workflow), is that marked with `<!-- example-test: docs-only; <reason> -->`?

The `<!-- example-test: ... -->` marker format uses the following pattern for future automated checking:

```python
# re.compile(
#     r'<!--\s*example-test:\s*'
#     r'(?P<target>docs-only|[\w/.\-]+\.py(?:::[\w]+)?)'
#     r'(?:\s*;\s*(?P<reason>.+?))?'
#     r'\s*-->'
# )
```

## Type Validation

`D-SafeLogger` ships with `py.typed` (PEP 561), so source typing and public type completeness are part of the standard quality gate. CI runs `mypy`, `pyright`, a typing smoke test, and a 100% `pyright --verifytypes` gate on every push.

### Tooling

- `mypy>=2.1` — strict-ish config (`disallow_untyped_defs = true`, `warn_unused_ignores = true`, `warn_return_any = true`).
- `pyright>=1.1.409` — `typeCheckingMode = "basic"` with `include = ["src"]`.

### Required commands (PR pre-flight)

```bash
uv sync --group dev
uv run pyright --version    # record first
uv run mypy src             # → 0 errors
uv run pyright src          # → 0 errors
uv run pyright tests/typing_smoke # → 0 errors
```

Local green (`0 errors` from both tools) is the precondition for pushing. CI runs the same commands and treats any error as a hard fail.

Package-level type completeness is checked from the built wheel, not the editable source tree:

```bash
uv build
uv run python scripts/install_built_wheel.py
uv run --no-sync python scripts/check_type_completeness.py --min-score 100
uv sync --reinstall
```

Use `uv run --no-sync` for the completeness check so the wheel install is not replaced by the editable project before `pyright --verifytypes` runs.

### Latest local validation (2026-05-23 / Python 3.14.3 / Windows)

| Tool | Version | Result |
|---|---|---|
| `mypy` | 2.1.0 | `Success: no issues found in 29 source files` |
| `pyright` | 1.1.409 | `0 errors, 0 warnings, 0 informations` |
| `pyright --verifytypes dsafelogger --ignoreexternal` | 1.1.409 | `Type completeness score: 100%` |

### Package name vs. type checker target

D-SafeLogger uses three name forms — be careful when invoking type tools:

- PyPI metadata: `D-SafeLogger`
- Python import / `verifytypes` target: `dsafelogger`
- Wheel filename: `d_safelogger-*.whl`

For `pyright --verifytypes`, always pass `dsafelogger` (the import name).

### Private module surface policy

Names starting with a leading underscore (`_constants.MASK_STRING`, `_constants._resolved_sensitive_keywords`, `_pipeline.ResolvedConfig`, `_async.DSafeQueueHandler`, etc.) are **private** even though `py.typed` exposes them to user type checkers. Library consumers MUST NOT depend on private symbols; they may change without notice in PATCH or MINOR releases. Only names re-exported from `dsafelogger` / `dsafelogger.mp` `__init__.py` are public.

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

GitHub Actions also runs an examples coexistence job on Ubuntu and Windows:

- Dependencies: `uv sync --group dev --group examples`
- Scope: `tests/examples/test_18_console_progress_coexistence.py`, `test_19_sentry_coexistence.py`, and `test_20_testing_and_warnings.py`

Optional GUI tests run in a separate workflow:

- Trigger: weekly schedule, manual dispatch, or pull requests touching the GUI example/test/workflow/dependency files
- Dependencies: `uv sync --group dev --group gui`
- Scope: `tests/examples/test_23_gui_logging_qt.py`
- Policy: Ubuntu must pass; Windows is allow-failure

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

The CI workflow also runs publication checks on Ubuntu/Python 3.13:

```bash
uv run pyright --version
uv run mypy src
uv run pyright src
uv run pyright tests/typing_smoke
uv run python scripts/generate_api_docs.py --check
uv run python scripts/check_design_docs_sync.py
uv run python benchmarks/update_summary.py --check
uv build
uv run python scripts/check_distribution_contents.py
uv run python scripts/install_built_wheel.py
uv run --no-sync python scripts/check_type_completeness.py --min-score 100
uv sync --reinstall --group dev
```

The publish workflow repeats release document, benchmark, build, distribution-content, metadata, and full-suite checks, verifies the git tag matches the package version, and only then publishes.

## Documentation Checks

Regenerate API docs after public API or docstring changes:

```bash
uv run python scripts/generate_api_docs.py
uv run python scripts/generate_api_docs.py --check
```

Public design documents live under `docs/design/`. Verify the selected v23k design documents with:

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
