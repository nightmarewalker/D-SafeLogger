"""Install the freshly built wheel into the current uv-managed environment.

Required by ``pyright --verifytypes`` which must inspect the **packaged**
``dsafelogger`` (site-packages copy), not the editable source tree. After
running this script, callers MUST use ``uv run --no-sync ...`` for the next
type check invocation; a bare ``uv run`` would re-sync the project and undo
the ``--force-reinstall``. Restore the editable state afterwards with
``uv sync --reinstall``.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    dist = Path("dist")
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        print(
            f"expected exactly one wheel in dist/, found {len(wheels)}: {wheels}",
            file=sys.stderr,
        )
        print(
            "hint: remove old wheels before running 'uv build' "
            "(rm -rf dist/ on bash, Remove-Item dist -Recurse -Force on PowerShell).",
            file=sys.stderr,
        )
        return 1

    wheel = wheels[0]
    print(f"Installing {wheel.name} into the current uv environment (force-reinstall).")
    print(
        "Editable install will be overwritten for package-level type validation. "
        "Use `uv run --no-sync ...` for the immediate next type check, then "
        "`uv sync --reinstall` to restore the editable state."
    )

    # uv-managed venvs often lack pip; prefer `uv pip install` for portability.
    if shutil.which("uv") is None:
        print(
            "error: `uv` not found on PATH. This script requires uv to install the "
            "wheel into the project-managed venv. Falling back to `python -m pip` is "
            "not supported because uv venvs do not include pip by default.",
            file=sys.stderr,
        )
        return 1

    subprocess.check_call(["uv", "pip", "install", "--force-reinstall", str(wheel)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
