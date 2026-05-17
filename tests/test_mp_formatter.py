"""Tests for FormatterSpec freeze / rebuild (UT/IT-MP-FMT).

Covers:
    UT-MP-FMT-001 to UT-MP-FMT-005  (§29.6a)
"""
from __future__ import annotations

import logging

import pytest

from dsafelogger._formatter import (
    DSafeFormatter,
    DiagnosticFormatter,
    DiagnosticStructuredFormatter,
    StructuredFormatter,
)
from dsafelogger._mp_protocol import _serialize_record
from dsafelogger._writer_formatter import freeze_formatter, rebuild_formatter


# ── freeze_formatter ──────────────────────────────────────────────────────────

class TestFreezeFormatter:

    def test_dsafe_formatter_kind(self):
        """UT-MP-FMT-001: DSafeFormatter freeze preserves kind, fmt, datefmt."""
        inst = DSafeFormatter(fmt='%(message)s', datefmt='%H:%M:%S')
        spec = freeze_formatter(inst)
        assert spec['kind'] == 'DSafeFormatter'
        assert spec['fmt'] == '%(message)s'
        assert spec['datefmt'] == '%H:%M:%S'

    def test_dsafe_formatter_percent_style(self):
        """UT-MP-FMT-002: % style preserved."""
        inst = DSafeFormatter(fmt='%(message)s', style='%')
        spec = freeze_formatter(inst)
        assert spec['style'] == '%'

    def test_dsafe_formatter_brace_style(self):
        """UT-MP-FMT-002: { style preserved."""
        inst = DSafeFormatter(fmt='{message}', style='{')
        spec = freeze_formatter(inst)
        assert spec['style'] == '{'

    def test_diagnostic_formatter_sensitive_keywords(self):
        """UT-MP-FMT-003: DiagnosticFormatter sensitive_keywords preserved."""
        inst = DiagnosticFormatter(sensitive_keywords=frozenset({'secret', 'token'}))
        spec = freeze_formatter(inst)
        assert spec['kind'] == 'DiagnosticFormatter'
        assert set(spec['sensitive_keywords']) == {'secret', 'token'}

    def test_diagnostic_formatter_no_style_key(self):
        """DiagnosticFormatter spec does not include style (constructor rejects it)."""
        inst = DiagnosticFormatter(fmt='%(message)s')
        spec = freeze_formatter(inst)
        assert 'style' not in spec

    def test_diagnostic_structured_formatter_sensitive_keywords(self):
        """UT-MP-FMT-004: DiagnosticStructuredFormatter sensitive_keywords preserved."""
        inst = DiagnosticStructuredFormatter(sensitive_keywords=frozenset({'pwd'}))
        spec = freeze_formatter(inst)
        assert spec['kind'] == 'DiagnosticStructuredFormatter'
        assert set(spec['sensitive_keywords']) == {'pwd'}

    def test_logging_formatter_defaults(self):
        """UT-MP-FMT-005: logging.Formatter freeze captures fmt and defaults."""
        inst = logging.Formatter(fmt='%(message)s', defaults={'foo': 'bar'})
        spec = freeze_formatter(inst)
        assert spec['kind'] == 'logging.Formatter'
        assert spec['fmt'] == '%(message)s'
        # Python 3.14 stores defaults on _style._defaults; verify it's captured
        assert spec.get('defaults') == {'foo': 'bar'}

    def test_structured_formatter_kind_only(self):
        """UT-MP-FMT-005: StructuredFormatter freeze captures only kind."""
        inst = StructuredFormatter()
        spec = freeze_formatter(inst)
        assert spec['kind'] == 'StructuredFormatter'

    def test_custom_subclass_raises_type_error(self):
        """Custom subclass raises TypeError."""
        class MyFmt(logging.Formatter):
            pass

        with pytest.raises(TypeError, match='allow-list'):
            freeze_formatter(MyFmt())


# ── rebuild_formatter ─────────────────────────────────────────────────────────

class TestRebuildFormatter:

    def test_rebuild_logging_formatter(self):
        inst = logging.Formatter(fmt='%(message)s', datefmt='%H:%M:%S')
        spec = freeze_formatter(inst)
        rebuilt = rebuild_formatter(spec)
        assert isinstance(rebuilt, logging.Formatter)
        assert rebuilt._fmt == '%(message)s'
        assert rebuilt.datefmt == '%H:%M:%S'

    def test_rebuild_dsafe_formatter(self):
        inst = DSafeFormatter(fmt='%(levelname)s: %(message)s')
        spec = freeze_formatter(inst)
        rebuilt = rebuild_formatter(spec)
        assert isinstance(rebuilt, DSafeFormatter)

    def test_rebuild_dsafe_formatter_brace_style(self):
        """UT-MP-FMT-002: rebuild with { style produces same format string."""
        inst = DSafeFormatter(fmt='{levelname}: {message}', style='{')
        spec = freeze_formatter(inst)
        rebuilt = rebuild_formatter(spec)
        rec = logging.makeLogRecord({'levelname': 'INFO', 'msg': 'hello', 'levelno': logging.INFO})
        original_output = inst.format(rec)
        rebuilt_output = rebuilt.format(rec)
        assert original_output == rebuilt_output

    def test_rebuild_diagnostic_formatter(self):
        inst = DiagnosticFormatter(
            fmt='%(message)s',
            sensitive_keywords=frozenset({'password'}),
        )
        spec = freeze_formatter(inst)
        rebuilt = rebuild_formatter(spec)
        assert isinstance(rebuilt, DiagnosticFormatter)
        assert 'password' in rebuilt._sensitive_keywords

    def test_rebuild_structured_formatter(self):
        inst = StructuredFormatter()
        spec = freeze_formatter(inst)
        rebuilt = rebuild_formatter(spec)
        assert isinstance(rebuilt, StructuredFormatter)

    def test_rebuild_diagnostic_structured_formatter(self):
        inst = DiagnosticStructuredFormatter(sensitive_keywords=frozenset({'token'}))
        spec = freeze_formatter(inst)
        rebuilt = rebuild_formatter(spec)
        assert isinstance(rebuilt, DiagnosticStructuredFormatter)
        assert 'token' in rebuilt._sensitive_keywords

    def test_rebuild_unknown_kind_raises_value_error(self):
        with pytest.raises(ValueError, match='Unknown FormatterSpec kind'):
            rebuild_formatter({'kind': 'NonExistentFormatter'})  # type: ignore[typeddict-item]

    def test_rebuild_missing_kind_raises_value_error(self):
        with pytest.raises(ValueError, match="missing"):
            rebuild_formatter({})  # type: ignore[arg-type]

    def test_diagnostic_formatter_masking_preserved(self):
        """UT-MP-FMT-003 IT: same masking result after freeze → rebuild."""
        sensitive = frozenset({'password', 'secret'})
        inst = DiagnosticFormatter(fmt='%(message)s', sensitive_keywords=sensitive)
        spec = freeze_formatter(inst)
        rebuilt = rebuild_formatter(spec)

        rec = logging.makeLogRecord({
            'msg': 'password=abc123',
            'levelno': logging.INFO,
        })
        original_out = inst.format(rec)
        rebuilt_out = rebuilt.format(rec)
        assert original_out == rebuilt_out


class TestMPSerializeInternalFields:

    def test_serialize_record_excludes_ds_route_from_extra(self):
        """Client-side serialization must not copy _ds_route into _ds_extra."""
        rec = logging.makeLogRecord({
            'msg': 'hello',
            'levelno': logging.INFO,
            '_ds_route': 'root',
            'request_id': 'req-123',
        })

        event = _serialize_record(rec, ds_route='root')

        assert event['_ds_route'] == 'root'
        assert '_ds_route' not in event['_ds_extra']
        assert event['_ds_extra']['request_id'] == 'req-123'
