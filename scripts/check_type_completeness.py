"""Check pyright --verifytypes completeness against a configured threshold.

PRECONDITION: the packaged dsafelogger wheel must be installed into the active
environment (see scripts/install_built_wheel.py). Callers must use
``uv run --no-sync python scripts/check_type_completeness.py ...`` so uv does
not re-sync the project and restore the editable install before verifytypes.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-score", type=float, default=100.0)
    args = parser.parse_args()

    if not (0.0 <= args.min_score <= 100.0):
        print(f"--min-score must be 0-100, got {args.min_score}", file=sys.stderr)
        return 2

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyright",
            "--verifytypes",
            "dsafelogger",
            "--ignoreexternal",
            "--outputjson",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    completeness: float | None = None
    try:
        data = json.loads(result.stdout)
        completeness = data.get("typeCompleteness", {}).get("completenessScore")
    except json.JSONDecodeError:
        # pyright 1.1.409 can emit unescaped Windows paths in --outputjson output.
        # The score field is still machine-readable, so use it as a narrow fallback.
        match = re.search(r'"completenessScore"\s*:\s*([0-9]+(?:\.[0-9]+)?)', result.stdout)
        if match is not None:
            completeness = float(match.group(1))

    if completeness is None:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print("could not find typeCompleteness.completenessScore", file=sys.stderr)
        return 1

    if completeness <= 1.0:
        completeness *= 100.0

    print(f"type completeness: {completeness:.2f}%")
    print(f"required minimum:  {args.min_score:.2f}%")
    if completeness < args.min_score:
        print("public type completeness below required threshold", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
