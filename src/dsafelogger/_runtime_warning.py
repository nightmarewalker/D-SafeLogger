"""Independent runtime warning JSONL writer for multiprocess observability."""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_WARNING_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds')


def _fallback_path(path: str | os.PathLike[str], pid: int | None = None) -> Path:
    base = Path(path)
    actual_pid = os.getpid() if pid is None else pid
    return base.with_name(f'{base.name}.{actual_pid}.fallback.jsonl')


class RuntimeWarningSink:
    """Append-only JSONL sink that never routes through application logging."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def write(
        self,
        *,
        component: str,
        event: str,
        level: str = 'warning',
        classification: str | None = None,
        reason: str | None = None,
        counter_name: str | None = None,
        counter_value: int | None = None,
        context: dict[str, Any] | None = None,
        pid: int | None = None,
    ) -> bool:
        payload = make_runtime_warning_payload(
            component=component,
            event=event,
            level=level,
            classification=classification,
            reason=reason,
            counter_name=counter_name,
            counter_value=counter_value,
            context=context,
            pid=pid,
        )
        return self.write_payload(payload)

    def write_payload(self, payload: dict[str, Any]) -> bool:
        try:
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n'
            with self._lock:
                with self._path.open('a', encoding='utf-8') as f:
                    f.write(line)
            return True
        except Exception as exc:
            _stderr_fallback(
                f'[D-SafeLogger] runtime warning sink write failed: {exc!r}'
            )
            return False

    @staticmethod
    def write_fallback(
        path: str | os.PathLike[str],
        payload: dict[str, Any],
        *,
        pid: int | None = None,
    ) -> bool:
        fallback = _fallback_path(path, pid)
        try:
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n'
            with fallback.open('a', encoding='utf-8') as f:
                f.write(line)
            return True
        except Exception as exc:
            _stderr_fallback(
                f'[D-SafeLogger] runtime warning fallback write failed: {exc!r}'
            )
            return False


def make_runtime_warning_payload(
    *,
    component: str,
    event: str,
    level: str = 'warning',
    classification: str | None = None,
    reason: str | None = None,
    counter_name: str | None = None,
    counter_value: int | None = None,
    context: dict[str, Any] | None = None,
    pid: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'schema_version': RUNTIME_WARNING_SCHEMA_VERSION,
        'ts': _now_iso(),
        'pid': os.getpid() if pid is None else pid,
        'component': component,
        'event': event,
        'level': level,
    }
    if classification is not None:
        payload['classification'] = classification
    if reason is not None:
        payload['reason'] = reason
    if counter_name is not None:
        payload['counter_name'] = counter_name
    if counter_value is not None:
        payload['counter_value'] = counter_value
    if context is not None:
        payload['context'] = context
    return payload


def _stderr_fallback(message: str) -> None:
    try:
        print(message, file=sys.stderr)
    except Exception:
        pass


__all__ = [
    'RUNTIME_WARNING_SCHEMA_VERSION',
    'RuntimeWarningSink',
    'make_runtime_warning_payload',
]
