"""Formatters for D-SafeLogger.

# ============================================================================
# [DESIGN GUARD] VENDOR-AGNOSTIC PRINCIPLE
# ============================================================================
# This module must NOT contain any third-party structured logging imports
# (e.g., structlog, loguru) or hardcoded dependencies on their internal structures.
# All extraction must be done via standard logging.LogRecord attributes
# and generic dictionary extractions (e.g. _extract_structured_extra_fields).
# ============================================================================
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import traceback
from typing import Any

from dsafelogger._constants import (
    DEFAULT_DATEFMT,
    DEFAULT_FMT,
    MASK_STRING,
    REPR_TRUNCATE_LIMIT,
)
from dsafelogger._context import get_context
from dsafelogger._levels import get_all_level_map

_STANDARD_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__) | {
    'message', 'asctime',
}
_DSAFE_INTERNAL_FIELDS = frozenset({
    '_ds_context', '_ds_exc_text', '_ds_diag_frames',
    '_ds_route',  # v23f: mp routing field; must not appear in structured JSON output
})


class _DisplayRecordProxy(logging.LogRecord):
    """Display-only view of a LogRecord with attribute overrides.

    Copies the original record's __dict__ and applies overrides (e.g.
    abbreviated or colourised levelname).  The original record is never
    mutated, so concurrent handlers each see the correct display value
    without interfering with one another.

    Inherits from LogRecord so that class-level methods (e.g. getMessage)
    are reachable via normal MRO lookup.  Initialisation is done entirely
    in __new__; LogRecord.__init__ is skipped.

    Hot path: formatters that call this frequently should use
    _make_proxy_tls() to reuse one proxy object per thread rather than
    constructing a new instance on every format call.
    """

    def __new__(
        cls,
        original: logging.LogRecord,
        overrides: dict[str, object],
    ) -> '_DisplayRecordProxy':
        obj = object.__new__(cls)
        obj.__dict__.update(original.__dict__)
        obj.__dict__.update(overrides)
        return obj

    def __init__(
        self,
        original: logging.LogRecord,
        overrides: dict[str, object],
    ) -> None:
        pass  # All setup is done in __new__; skip LogRecord.__init__.


def _make_proxy_tls() -> threading.local:
    """Return a new threading.local for per-thread _DisplayRecordProxy reuse.

    Usage (class level)::

        _proxy_tls: threading.local = _make_proxy_tls()

    In the hot path::

        proxy = getattr(cls._proxy_tls, 'instance', None)
        if proxy is None:
            proxy = object.__new__(_DisplayRecordProxy)
            cls._proxy_tls.instance = proxy
        proxy.__dict__.clear()
        proxy.__dict__.update(record.__dict__)
        proxy.__dict__['levelname'] = override_value

    Each thread gets its own proxy; the proxy dict is updated in-place so
    no new Python objects are allocated per call, eliminating GC pressure
    in high-throughput multi-threaded scenarios.
    """
    return threading.local()


def _extract_structured_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Collect non-standard LogRecord attributes for structured output."""
    extra_fields: dict[str, Any] = {}

    for key, value in record.__dict__.items():
        if key in _STANDARD_LOG_RECORD_FIELDS:
            continue
        if key in _DSAFE_INTERNAL_FIELDS:
            continue
        extra_fields[key] = value

    return extra_fields


class DSafeFormatter(logging.Formatter):
    """Standard D-SafeLogger formatter with level abbreviation and context suffix."""

    _proxy_tls: threading.local = _make_proxy_tls()

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: str = '%',
    ) -> None:
        # For % style, fall back to the D-SafeLogger default format when fmt is
        # omitted.  For { and $ styles, pass fmt=None so that logging picks the
        # style-appropriate minimal default ('{message}' / '${message}').
        super().__init__(
            fmt=fmt or (DEFAULT_FMT if style == '%' else None),
            datefmt=datefmt or DEFAULT_DATEFMT,
            style=style,
        )
        self._level_map = get_all_level_map()

    def format(self, record: logging.LogRecord) -> str:
        # Reuse a per-thread proxy so that no new Python object is allocated on
        # every call.  The proxy __dict__ is cleared and repopulated in-place,
        # which avoids GC pressure in high-throughput multi-threaded scenarios.
        # A separate _proxy_tls is defined at the class level so that
        # DSafeFormatter and ColorStreamHandler never share the same proxy
        # instance (which would cause self-reference corruption when
        # DSafeFormatter is used as the formatter on a ColorStreamHandler).
        abbr = self._level_map.get(record.levelname, record.levelname)
        proxy = getattr(self._proxy_tls, 'instance', None)
        if proxy is None:
            proxy = object.__new__(_DisplayRecordProxy)
            self._proxy_tls.instance = proxy
        proxy.__dict__.clear()
        proxy.__dict__.update(record.__dict__)
        proxy.__dict__['levelname'] = abbr
        result = super().format(proxy)

        # Append context suffix.
        # If _ds_context attribute is present (set by async prepare() or sync emit()),
        # treat it as authoritative regardless of whether it is empty.
        # Fall back to get_context() only when the attribute is absent (direct
        # logging.Handler path without D-SafeLogger transport).
        if hasattr(record, '_ds_context'):
            ctx = record._ds_context  # type: ignore[attr-defined]
        else:
            ctx = get_context()
        if ctx:
            suffix = ' '.join(f'{k}:{v}' for k, v in ctx.items())
            result += f' [{suffix}]'

        return result


class StructuredFormatter(logging.Formatter):
    """JSON Lines formatter for structured logging."""

    def __init__(self) -> None:
        super().__init__()
        self._level_map = get_all_level_map()

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            'timestamp': self.formatTime(record, DEFAULT_DATEFMT)
                         + f'.{int(record.msecs):03d}',
            'level': self._level_map.get(record.levelname, record.levelname),
            'logger': record.name,
            'file': record.filename,
            'line': record.lineno,
            'function': record.funcName,
            'message': record.getMessage(),
        }

        # Context as top-level fields
        if hasattr(record, '_ds_context'):
            ctx = record._ds_context  # type: ignore[attr-defined]
        else:
            ctx = get_context()
        if ctx:
            for k, v in ctx.items():
                data[k] = v

        for k, v in _extract_structured_extra_fields(record).items():
            data[k] = v

        # Exception info
        if record.exc_info and record.exc_info[1]:
            exc_text = getattr(record, '_ds_exc_text', None)
            if exc_text:
                data['exception'] = exc_text
            else:
                data['exception'] = ''.join(traceback.format_exception(*record.exc_info))

        return json.dumps(data, ensure_ascii=False, default=str)


class DiagnosticFormatter(DSafeFormatter):
    """Extended formatter that expands f_locals on exceptions.

    Used when {prefix}_DIAGNOSE=1 (sanctuary: env-only).
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        sensitive_keywords: frozenset[str] | None = None,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        from dsafelogger._constants import BUILTIN_SENSITIVE_KEYWORDS
        self._sensitive_keywords = sensitive_keywords or BUILTIN_SENSITIVE_KEYWORDS

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)

        # Use snapshot if available (from DSafeQueueHandler)
        snapshot_text = getattr(record, '_ds_exc_text', None)
        if snapshot_text:
            result += '\n' + snapshot_text
            snapshot_frames = getattr(record, '_ds_diag_frames', None)
            if snapshot_frames:
                result += '\n' + self._format_snapshot_frames(snapshot_frames)
            return result

        # Live f_locals expansion
        if record.exc_info and record.exc_info[1] is not None:
            locals_text = self._format_locals(record.exc_info)
            if locals_text:
                result += '\n' + locals_text

        return result

    def _format_locals(self, exc_info: tuple) -> str:
        """Format f_locals from all frames in the traceback chain."""
        _, exc_value, exc_tb = exc_info
        lines: list[str] = []

        tb = exc_tb
        while tb is not None:
            frame = tb.tb_frame
            lines.append(f'--- Local Variables ({frame.f_code.co_filename}:{tb.tb_lineno}) ---')
            for name, value in frame.f_locals.items():
                if self._is_sensitive(name):
                    lines.append(f'  {name} = {MASK_STRING}')
                else:
                    lines.append(f'  {name} = {self._safe_repr(value)}')
            tb = tb.tb_next

        # Follow __cause__ chain
        cause = exc_value.__cause__ if exc_value else None
        while cause is not None:
            cause_tb = cause.__traceback__
            while cause_tb is not None:
                frame = cause_tb.tb_frame
                lines.append(
                    f'--- Local Variables [cause] ({frame.f_code.co_filename}:{cause_tb.tb_lineno}) ---'
                )
                for name, value in frame.f_locals.items():
                    if self._is_sensitive(name):
                        lines.append(f'  {name} = {MASK_STRING}')
                    else:
                        lines.append(f'  {name} = {self._safe_repr(value)}')
                cause_tb = cause_tb.tb_next
            cause = cause.__cause__

        return '\n'.join(lines) if lines else ''

    @staticmethod
    def _format_snapshot_frames(frames: list[dict]) -> str:
        """Format producer-side diagnostic frame snapshots."""
        lines: list[str] = []
        for frame in frames:
            frame_name = frame.get('frame', '<unknown>')
            lines.append(f'--- Local Variables ({frame_name}) ---')
            variables = frame.get('variables', {})
            if isinstance(variables, dict):
                for name, value in variables.items():
                    lines.append(f'  {name} = {value}')
        return '\n'.join(lines)

    def _is_sensitive(self, name: str) -> bool:
        """Check if variable name contains a sensitive keyword (case-insensitive)."""
        name_lower = name.lower()
        return any(kw in name_lower for kw in self._sensitive_keywords)

    @staticmethod
    def _safe_repr(value: object) -> str:
        """Safe repr with truncation."""
        try:
            r = repr(value)
            if len(r) > REPR_TRUNCATE_LIMIT:
                return r[:REPR_TRUNCATE_LIMIT] + '...'
            return r
        except Exception:
            return '<repr failed>'


class DiagnosticStructuredFormatter(StructuredFormatter):
    """Structured JSON formatter with f_locals expansion."""

    def __init__(
        self,
        sensitive_keywords: frozenset[str] | None = None,
    ) -> None:
        super().__init__()
        from dsafelogger._constants import BUILTIN_SENSITIVE_KEYWORDS
        self._sensitive_keywords = sensitive_keywords or BUILTIN_SENSITIVE_KEYWORDS

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            'timestamp': self.formatTime(record, DEFAULT_DATEFMT)
                         + f'.{int(record.msecs):03d}',
            'level': self._level_map.get(record.levelname, record.levelname),
            'logger': record.name,
            'file': record.filename,
            'line': record.lineno,
            'function': record.funcName,
            'message': record.getMessage(),
        }

        # Context
        if hasattr(record, '_ds_context'):
            ctx = record._ds_context  # type: ignore[attr-defined]
        else:
            ctx = get_context()
        if ctx:
            for k, v in ctx.items():
                data[k] = v

        for k, v in _extract_structured_extra_fields(record).items():
            data[k] = v

        # Exception with locals
        if record.exc_info and record.exc_info[1]:
            exc_text = getattr(record, '_ds_exc_text', None)
            if exc_text:
                data['exception'] = exc_text
            else:
                data['exception'] = ''.join(traceback.format_exception(*record.exc_info))

            # Snapshot frames or live frames
            snapshot_frames = getattr(record, '_ds_diag_frames', None)
            if snapshot_frames:
                data['locals'] = snapshot_frames
            else:
                data['locals'] = self._collect_locals(record.exc_info)

        return json.dumps(data, ensure_ascii=False, default=str)

    def _collect_locals(self, exc_info: tuple) -> list[dict]:
        """Collect f_locals from all frames."""
        _, exc_value, exc_tb = exc_info
        frames: list[dict] = []

        tb = exc_tb
        while tb is not None:
            frame = tb.tb_frame
            variables: dict[str, str] = {}
            for name, value in frame.f_locals.items():
                if self._is_sensitive(name):
                    variables[name] = MASK_STRING
                else:
                    variables[name] = self._safe_repr(value)
            frames.append({
                'frame': f'{frame.f_code.co_filename}:{tb.tb_lineno}',
                'variables': variables,
            })
            tb = tb.tb_next

        return frames

    def _is_sensitive(self, name: str) -> bool:
        name_lower = name.lower()
        return any(kw in name_lower for kw in self._sensitive_keywords)

    @staticmethod
    def _safe_repr(value: object) -> str:
        try:
            r = repr(value)
            if len(r) > REPR_TRUNCATE_LIMIT:
                return r[:REPR_TRUNCATE_LIMIT] + '...'
            return r
        except Exception:
            return '<repr failed>'
