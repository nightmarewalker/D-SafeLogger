"""ANSI color console handler for D-SafeLogger."""

from __future__ import annotations

import logging
import os
import sys

import threading

from dsafelogger._formatter import _DisplayRecordProxy, _make_proxy_tls
from dsafelogger._levels import get_all_color_map, get_all_level_map


class ColorStreamHandler(logging.StreamHandler):
    """StreamHandler with ANSI color codes for log levels.

    Uses _DisplayRecordProxy to apply colourised levelname without mutating
    the original LogRecord, so ANSI codes never leak to other handlers
    (e.g., file handlers) that share the same record.

    A separate _proxy_tls (distinct from DSafeFormatter._proxy_tls) is used
    so that when DSafeFormatter is the formatter on this handler the two
    classes never share the same proxy instance.

    v23h: classified as a *best-effort / diagnostic* sink
    (`_ds_required = False`).  Failures are stderr-warned (rate-limited)
    but do not contribute to `_writer_sink_reject`, `_writer_policy_reject`,
    `_writer_partial_delivered`, or `_reject_counter`. See §12.3.
    """

    RESET = '\033[0m'
    _proxy_tls: threading.local = _make_proxy_tls()
    _ds_required: bool = False

    def __init__(
        self,
        stream=None,
        color_enabled: bool = True,
        color_overrides: dict[str, str] | None = None,
    ) -> None:
        super().__init__(stream or sys.stderr)
        self._color_enabled = color_enabled
        self.COLOR_MAP = get_all_color_map(overrides=color_overrides)
        self._level_map = get_all_level_map()

    def emit(self, record: logging.LogRecord) -> None:
        if self._color_enabled:
            resolved_level = self._level_map.get(record.levelname, record.levelname)
            color = self.COLOR_MAP.get(resolved_level, '')
            if color:
                # Reuse per-thread proxy to avoid per-call allocation.
                # Original record is never mutated, preventing ANSI codes
                # from leaking to other handlers sharing the same LogRecord.
                coloured_level = f'{color}{resolved_level}{self.RESET}'
                proxy = getattr(self._proxy_tls, 'instance', None)
                if proxy is None:
                    proxy = object.__new__(_DisplayRecordProxy)
                    self._proxy_tls.instance = proxy
                proxy.__dict__.clear()
                proxy.__dict__.update(record.__dict__)
                proxy.__dict__['levelname'] = coloured_level
                super().emit(proxy)
                return
        super().emit(record)


def _enable_windows_vt100() -> None:
    """Enable ANSI escape sequences on Windows 10+."""
    if sys.platform == 'win32':
        os.system('')
