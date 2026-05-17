"""Generate benchmark summary documents from the selected-session manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks._benchmark_report import write_benchmark_summaries


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate benchmarks/summary/*.md from benchmarks/summary/manifest.json"
    )
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated summary files differ from the current files",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    paths = write_benchmark_summaries(Path(args.repo_root).resolve(), check=args.check)
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
