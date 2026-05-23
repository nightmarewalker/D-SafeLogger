"""Check public design-document readiness.

`plan/` is a private planning area. Public design documents live under
`docs/design/`, so CI validates that the selected public design files are present
and do not expose private planning paths or stale release-publication wording.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = REPO_ROOT / "docs" / "design"

DEFAULT_DESIGN_VERSION = "v23k"

REQUIRED_FILE_TEMPLATES = (
    "D_SafeLogger_Specification_{version}_full.md",
    "D_SafeLogger_Specification_{version}_full_en.md",
    "D-SafeLogger_DetailedDesign_{version}.md",
    "D-SafeLogger_TestDesign_{version}.md",
    "D-SafeLogger_{version}_WhitePaper.md",
    "D-SafeLogger_{version}_WhitePaper_en.md",
)

PRIVATE_PATH_PATTERNS = (
    "plan/",
    "plan\\",
    "plan/v23/",
    "plan\\v23\\",
    "plan/new_spec/",
    "plan\\new_spec\\",
)

FORBIDDEN_PUBLIC_PATTERNS = (
    ("AGENTS.md", "agent guide must not be cited as a public source"),
    ("PYTHONGIL", "use PYTHON_GIL"),
    ("wheel/sdist", "describe wheel and sdist contents separately"),
    ("配送状態 7", "use classified delivery-state counters wording"),
    ("7 階層", "use classified delivery-state counters wording"),
    ("7-tier", "use classified delivery-state counters wording"),
    ("seven-tier", "use classified delivery-state counters wording"),
    (
        "free-threaded build でのテスト実行が**公式品質ゲートに含まれる**",
        "free-threaded validation is a documented manual procedure",
    ),
    (
        "公式テストマトリックスに free-threaded build が含まれる",
        "free-threaded validation is a documented manual procedure",
    ),
    (
        "official test matrix includes free-threaded build",
        "free-threaded validation is a documented manual procedure",
    ),
    (
        "free-threaded builds are included in the official quality gate",
        "free-threaded validation is a documented manual procedure",
    ),
    (
        "backup_count=0` 相当に補正 + stderr 警告",
        "invalid overflow-error generation-management combinations must fail fast",
    ),
    (
        "corrected to be equivalent to `backup_count=0` + stderr warning",
        "invalid overflow-error generation-management combinations must fail fast",
    ),
    (
        "forced overwriting to `enable_hash=False`",
        "invalid cyclic hash combinations must fail fast",
    ),
    (
        "forcibly overwritten with `enable_hash=False`",
        "invalid cyclic hash combinations must fail fast",
    ),
    (
        "強制的に `enable_hash=False` に上書き",
        "invalid cyclic hash combinations must fail fast",
    ),
    (
        "stderr 警告 + `enable_hash=False`",
        "invalid cyclic hash combinations must fail fast",
    ),
    (
        "hashing is disabled with a warning",
        "invalid cyclic hash combinations must fail fast",
    ),
    (
        "warning のうえ hash を無効化",
        "invalid cyclic hash combinations must fail fast",
    ),
)


def _required_files(version: str) -> tuple[str, ...]:
    return tuple(
        template.format(version=version)
        for template in REQUIRED_FILE_TEMPLATES
    )


def _problems(version: str) -> list[str]:
    problems: list[str] = []
    for filename in _required_files(version):
        path = DESIGN_DIR / filename
        if not path.exists():
            problems.append(f"missing: docs/design/{filename}")
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PRIVATE_PATH_PATTERNS:
            if pattern in text:
                problems.append(f"private path reference in docs/design/{filename}: {pattern}")
        for pattern, message in FORBIDDEN_PUBLIC_PATTERNS:
            if pattern in text:
                problems.append(
                    f"forbidden wording in docs/design/{filename}: {pattern} ({message})"
                )
    return problems


def check(version: str = DEFAULT_DESIGN_VERSION) -> int:
    problems = _problems(version)
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print("Public design docs are ready")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=DEFAULT_DESIGN_VERSION,
        help=f"design document version to validate (default: {DEFAULT_DESIGN_VERSION})",
    )
    args = parser.parse_args()
    return check(args.version)


if __name__ == "__main__":
    raise SystemExit(main())
