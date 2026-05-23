"""Validate wheel and sdist contents for the D-SafeLogger distribution.

Faithfully migrated from the inline heredoc in publish.yml (A6=Z1: faithful
migration only). Additions over the original include ``py.typed`` checks and
current observability/design/benchmark artifacts that must ship in sdist/wheel.

Exit code 0 = OK, non-zero = error details printed to stderr.
"""
from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path


def _normalized_sdist_names(path: Path) -> set[str]:
    with tarfile.open(path, "r:gz") as archive:
        names = []
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if len(parts) > 1:
                names.append("/".join(parts[1:]))
    return set(names)


def main() -> int:
    dist = Path("dist")
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))

    if len(wheels) != 1:
        print(f"expected exactly one wheel, found {len(wheels)}", file=sys.stderr)
        return 1
    if len(sdists) != 1:
        print(f"expected exactly one sdist, found {len(sdists)}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = set(archive.namelist())
    sdist_names = _normalized_sdist_names(sdists[0])

    wheel_forbidden = (
        "tests/",
        "docs/",
        "examples/",
        "benchmarks/",
        "plan/",
        "for_chat/",
        ".github/",
        "dist/",
    )
    sdist_forbidden = (
        "plan/",
        "for_chat/",
        ".git/",
        ".github/",
        "docs/design/old/",
        "dist/",
        "build/",
    )
    wheel_required = {
        "dsafelogger/_runtime_warning.py",
        "dsafelogger/_shutdown_report.py",
        "dsafelogger/py.typed",
    }
    sdist_required = {
        "LICENSE",
        "README.md",
        "README_ja.md",
        "CHANGELOG.md",
        "TESTING.md",
        "BENCHMARK.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "MANIFEST.in",
        "pyproject.toml",
        "src/dsafelogger/__init__.py",
        "src/dsafelogger/_runtime_warning.py",
        "src/dsafelogger/_shutdown_report.py",
        "src/dsafelogger/py.typed",
        "tests/conftest.py",
        "docs/design/D_SafeLogger_Specification_v23k_full.md",
        "docs/design/D_SafeLogger_Specification_v23k_full_en.md",
        "docs/design/D-SafeLogger_DetailedDesign_v23k.md",
        "docs/design/D-SafeLogger_TestDesign_v23k.md",
        "docs/design/D-SafeLogger_v23k_WhitePaper.md",
        "docs/design/D-SafeLogger_v23k_WhitePaper_en.md",
        "docs/design/v23k_supplements/delivery_status_schema.md",
        "docs/design/v23k_supplements/mp_observability_test_matrix.md",
        "docs/design/v23k_supplements/runtime_warning_design.md",
        "examples/01_quick_start.md",
        "examples/17_container_collector_coexistence.md",
        "benchmarks/_benchmark_report.py",
        "benchmarks/update_summary.py",
        "benchmarks/summary/index.md",
        "benchmarks/summary/manifest.json",
        "benchmarks/results/benchmark_20260506_180018/summary.json",
        "benchmarks/results/benchmark_20260506_180018/summary.md",
        "benchmarks/results/benchmarks_multi_integ_20260506_185947/summary.json",
        "benchmarks/results/benchmarks_multi_integ_20260506_185947/summary.md",
        "benchmarks/results/benchmarks_multi_perf_20260506_190518/summary.json",
        "benchmarks/results/benchmarks_multi_perf_20260506_190518/summary.md",
        "benchmarks/results/benchmarks_multi_resilience_20260523_084326/summary.json",
        "benchmarks/results/benchmarks_multi_resilience_20260523_084326/summary.md",
    }

    errors: list[str] = []

    bad_wheel = sorted(name for name in wheel_names if name.startswith(wheel_forbidden))
    if bad_wheel:
        errors.append(f"wheel contains forbidden paths: {bad_wheel[:20]}")

    missing_wheel = sorted(wheel_required - wheel_names)
    if missing_wheel:
        errors.append(f"wheel is missing required paths: {missing_wheel}")

    bad_sdist = sorted(name for name in sdist_names if name.startswith(sdist_forbidden))
    if bad_sdist:
        errors.append(f"sdist contains forbidden paths: {bad_sdist[:20]}")

    missing_sdist = sorted(sdist_required - sdist_names)
    if missing_sdist:
        errors.append(f"sdist is missing required paths: {missing_sdist}")

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        return 1

    print("distribution contents verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
