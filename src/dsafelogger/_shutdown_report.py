"""Atomic shutdown report writer for multiprocess delivery accounting."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ShutdownReportWriter:
    """Write a single JSON shutdown report using same-directory replace."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def write(self, report: dict[str, Any]) -> None:
        parent = self._path.parent
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=parent,
                prefix=f'.{self._path.name}.',
                suffix='.tmp',
                delete=False,
            ) as tmp:
                tmp_path = tmp.name
                json.dump(report, tmp, ensure_ascii=False, sort_keys=True, indent=2)
                tmp.write('\n')
            os.replace(tmp_path, self._path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


__all__ = ['ShutdownReportWriter']
