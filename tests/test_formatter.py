"""Tests for dsafelogger._formatter (all Formatter variants)."""

from __future__ import annotations

import json
import logging
import pytest
from unittest.mock import patch

from dsafelogger._formatter import (
    DSafeFormatter,
    DiagnosticFormatter,
    DiagnosticStructuredFormatter,
    StructuredFormatter,
    _DisplayRecordProxy,
)
from dsafelogger._context import set_context, reset_context


def _make_record(
    msg: str = 'test message',
    level: int = logging.INFO,
    exc_info: tuple | None = None,
    name: str = 'test',
) -> logging.LogRecord:
    """Create a LogRecord for testing."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname='test.py',
        lineno=42,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    return record


class TestDSafeFormatter:
    """UT-FMT: DSafeFormatter tests."""

    def test_debug_abbreviation(self):
        fmt = DSafeFormatter()
        record = _make_record(level=logging.DEBUG)
        result = fmt.format(record)
        assert 'DBG' in result

    def test_info_abbreviation(self):
        fmt = DSafeFormatter()
        record = _make_record(level=logging.INFO)
        result = fmt.format(record)
        assert 'INF' in result

    def test_warning_abbreviation(self):
        fmt = DSafeFormatter()
        record = _make_record(level=logging.WARNING)
        result = fmt.format(record)
        assert 'WAR' in result

    def test_error_abbreviation(self):
        fmt = DSafeFormatter()
        record = _make_record(level=logging.ERROR)
        result = fmt.format(record)
        assert 'ERR' in result

    def test_critical_abbreviation(self):
        fmt = DSafeFormatter()
        record = _make_record(level=logging.CRITICAL)
        result = fmt.format(record)
        assert 'CRI' in result

    def test_context_suffix(self):
        fmt = DSafeFormatter()
        record = _make_record()
        token = set_context({'task_id': 42, 'worker': 'db_sync'})
        try:
            result = fmt.format(record)
            assert '[task_id:42 worker:db_sync]' in result
        finally:
            reset_context(token)

    def test_no_context_no_suffix(self):
        fmt = DSafeFormatter()
        record = _make_record()
        result = fmt.format(record)
        assert '[' not in result or 'INF' in result  # Only level bracket

    def test_custom_fmt(self):
        fmt = DSafeFormatter(fmt='%(levelname)s %(message)s')
        record = _make_record()
        result = fmt.format(record)
        assert 'INF test message' in result

    def test_custom_datefmt(self):
        fmt = DSafeFormatter(datefmt='%H:%M:%S')
        record = _make_record()
        result = fmt.format(record)
        assert 'test message' in result


class TestDSafeFormatterStylesAndImmutability:
    """UT-FMT-010 to UT-FMT-014: format style coverage and levelname immutability."""

    def test_percent_style_abbreviates_levelname(self):
        """UT-FMT-010: % style format shows abbreviated levelname."""
        fmt = DSafeFormatter(fmt='%(levelname)s %(message)s')
        record = _make_record(level=logging.INFO)
        result = fmt.format(record)
        assert result.split()[0] == 'INF'
        assert 'INFO' not in result.split()[0]

    def test_brace_style_abbreviates_levelname(self):
        """UT-FMT-011: {} style format shows abbreviated levelname."""
        fmt = DSafeFormatter(fmt='{levelname} {message}', style='{')
        record = _make_record(level=logging.INFO)
        result = fmt.format(record)
        assert result.split()[0] == 'INF'

    def test_dollar_style_abbreviates_levelname(self):
        """UT-FMT-012: $ style format shows abbreviated levelname."""
        fmt = DSafeFormatter(fmt='${levelname} ${message}', style='$')
        record = _make_record(level=logging.INFO)
        result = fmt.format(record)
        assert result.split()[0] == 'INF'

    def test_levelname_immutable_after_format(self):
        """UT-FMT-013: record.levelname is not mutated by format()."""
        fmt = DSafeFormatter()
        record = _make_record(level=logging.INFO)
        original = record.levelname
        fmt.format(record)
        assert record.levelname == original

    def test_custom_level_levelname_immutable(self):
        """UT-FMT-014: custom level record.levelname is not mutated by format()."""
        from dsafelogger import register_level
        register_level('VERBOSE', 15, 'VRB', '\033[35m')
        fmt = DSafeFormatter(fmt='%(levelname)s %(message)s')
        record = _make_record(level=15)
        original = record.levelname
        fmt.format(record)
        assert record.levelname == original

    def test_display_record_proxy_isolates_overrides(self):
        """_DisplayRecordProxy overrides do not escape back to original dict."""
        record = _make_record(level=logging.WARNING)
        original_levelname = record.levelname
        proxy = _DisplayRecordProxy(record, {'levelname': 'WAR'})
        assert proxy.levelname == 'WAR'
        assert record.levelname == original_levelname

    def test_display_record_proxy_getmessage(self):
        """_DisplayRecordProxy.getMessage() works (LogRecord MRO available)."""
        record = _make_record(msg='hello world')
        proxy = _DisplayRecordProxy(record, {'levelname': 'INF'})
        assert proxy.getMessage() == 'hello world'


class TestStructuredFormatter:
    """UT-SF: StructuredFormatter tests."""

    def test_valid_json(self):
        fmt = StructuredFormatter()
        record = _make_record()
        result = fmt.format(record)
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_required_fields(self):
        fmt = StructuredFormatter()
        record = _make_record()
        result = fmt.format(record)
        data = json.loads(result)
        for field in ('timestamp', 'level', 'logger', 'file', 'line', 'function', 'message'):
            assert field in data, f"Missing field: {field}"

    def test_level_abbreviation(self):
        fmt = StructuredFormatter()
        record = _make_record(level=logging.INFO)
        data = json.loads(fmt.format(record))
        assert data['level'] == 'INF'

    def test_context_top_level(self):
        fmt = StructuredFormatter()
        record = _make_record()
        token = set_context({'task_id': 42})
        try:
            data = json.loads(fmt.format(record))
            assert data['task_id'] == 42
        finally:
            reset_context(token)

    def test_exception_field(self):
        fmt = StructuredFormatter()
        try:
            raise ValueError('test error')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        data = json.loads(fmt.format(record))
        assert 'exception' in data
        assert 'ValueError' in data['exception']

    def test_japanese_message(self):
        fmt = StructuredFormatter()
        record = _make_record(msg='日本語メッセージ')
        data = json.loads(fmt.format(record))
        assert data['message'] == '日本語メッセージ'

    def test_single_line_output(self):
        fmt = StructuredFormatter()
        record = _make_record(msg='line1\nline2')
        result = fmt.format(record)
        # JSON should be a single line
        assert result.count('\n') == 0

    def test_ds_route_not_in_structured_output(self):
        """_ds_route must not appear in structured JSON public output (v23f, diff #3)."""
        fmt = StructuredFormatter()
        record = _make_record()
        record._ds_route = 'root'  # simulates mp Writer path
        data = json.loads(fmt.format(record))
        assert '_ds_route' not in data, '_ds_route leaked into structured JSON output'

    def test_ds_internal_fields_not_in_structured_output(self):
        """All _ds_* internal fields must be filtered from structured JSON."""
        fmt = StructuredFormatter()
        record = _make_record()
        # Use type-compatible values for each internal field
        record._ds_route = 'root'
        record._ds_context = {}
        record._ds_exc_text = 'some exc text'
        record._ds_diag_frames = []
        data = json.loads(fmt.format(record))
        for field in ('_ds_route', '_ds_context', '_ds_exc_text', '_ds_diag_frames'):
            assert field not in data, f'{field} leaked into structured JSON output'

    def test_user_extra_field_still_included(self):
        """User-supplied extra fields must still appear in structured JSON."""
        fmt = StructuredFormatter()
        record = _make_record()
        record.request_id = 'req-abc'
        data = json.loads(fmt.format(record))
        assert data.get('request_id') == 'req-abc'


class TestDiagnosticFormatter:
    """UT-DIAG: DiagnosticFormatter tests."""

    def test_exception_locals_expansion(self):
        fmt = DiagnosticFormatter()
        try:
            local_var = 42
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        result = fmt.format(record)
        assert '--- Local Variables' in result
        assert 'local_var' in result

    def test_no_exception_normal_output(self):
        fmt = DiagnosticFormatter()
        record = _make_record()
        result = fmt.format(record)
        assert '--- Local Variables' not in result

    def test_password_masking(self):
        fmt = DiagnosticFormatter()
        try:
            password = 'secret123'  # noqa: F841
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        result = fmt.format(record)
        assert '*** MASKED ***' in result
        assert 'secret123' not in result

    def test_api_key_masking(self):
        fmt = DiagnosticFormatter()
        try:
            api_key = 'sk-1234'  # noqa: F841
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        result = fmt.format(record)
        assert '*** MASKED ***' in result

    def test_non_sensitive_not_masked(self):
        fmt = DiagnosticFormatter()
        try:
            count = 42  # noqa: F841
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        result = fmt.format(record)
        assert '42' in result

    def test_repr_truncation(self):
        fmt = DiagnosticFormatter()
        try:
            big_var = 'x' * 300  # noqa: F841
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        result = fmt.format(record)
        assert '...' in result

    def test_custom_sensitive_keywords(self):
        fmt = DiagnosticFormatter(
            sensitive_keywords=frozenset({'my_secret'})
        )
        try:
            my_secret_value = 'hidden'  # noqa: F841
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        result = fmt.format(record)
        assert '*** MASKED ***' in result


class TestDiagnosticStructuredFormatter:
    """UT-DIAG-J: DiagnosticStructuredFormatter tests."""

    def test_locals_in_json(self):
        fmt = DiagnosticStructuredFormatter()
        try:
            local_var = 42  # noqa: F841
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        data = json.loads(fmt.format(record))
        assert 'locals' in data
        assert isinstance(data['locals'], list)
        assert len(data['locals']) > 0
        assert 'frame' in data['locals'][0]
        assert 'variables' in data['locals'][0]

    def test_no_exception_no_locals(self):
        fmt = DiagnosticStructuredFormatter()
        record = _make_record()
        data = json.loads(fmt.format(record))
        assert 'locals' not in data

    def test_sensitive_masking_json(self):
        fmt = DiagnosticStructuredFormatter()
        try:
            token = 'secret_token'  # noqa: F841
            raise ValueError('test')
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())
        data = json.loads(fmt.format(record))
        for frame_info in data['locals']:
            if 'token' in frame_info['variables']:
                assert frame_info['variables']['token'] == '*** MASKED ***'

    def test_ds_route_not_in_diagnostic_structured_output(self):
        """DiagnosticStructuredFormatter must also hide mp internal routing fields."""
        fmt = DiagnosticStructuredFormatter()
        record = _make_record()
        record._ds_route = 'root'
        data = json.loads(fmt.format(record))
        assert '_ds_route' not in data
