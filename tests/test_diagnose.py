"""Tests for D_LOG_DIAGNOSE (environment-only sanctuary)."""

from __future__ import annotations

import logging
import os

import pytest
import dsafelogger
from dsafelogger import ConfigureLogger
from dsafelogger._formatter import (
    DSafeFormatter,
    DiagnosticFormatter,
    DiagnosticStructuredFormatter,
    StructuredFormatter,
)


class TestDiagnoseEnvOnly:
    """UT-DD: D_LOG_DIAGNOSE tests."""

    def _get_file_handler_formatter(self):
        """Get the formatter from the file handler."""
        import dsafelogger
        h = dsafelogger._active_pipeline.transport._target_handlers[0]
        return h.formatter

    def test_diagnose_enabled(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '1'
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        import dsafelogger
        fmt = dsafelogger._active_pipeline.transport._target_handlers[0].formatter
        assert isinstance(fmt, DiagnosticFormatter)

    def test_diagnose_disabled_unset(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        fmt = self._get_file_handler_formatter()
        assert isinstance(fmt, DSafeFormatter)
        assert not isinstance(fmt, DiagnosticFormatter)

    def test_diagnose_disabled_zero(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '0'
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        fmt = self._get_file_handler_formatter()
        assert isinstance(fmt, DSafeFormatter)
        assert not isinstance(fmt, DiagnosticFormatter)

    def test_diagnose_disabled_true_string(self, tmp_path, clean_env):
        """Only "1" enables diagnose, not "true"."""
        os.environ['D_LOG_DIAGNOSE'] = 'true'
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        from dsafelogger import _constants
        assert _constants._diagnose_enabled is False

    def test_diagnose_disabled_empty(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = ''
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        from dsafelogger import _constants
        assert _constants._diagnose_enabled is False

    def test_diagnose_with_structured(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '1'
        ConfigureLogger(log_path=str(tmp_path), structured=True, console_out=False)
        import dsafelogger
        fmt = dsafelogger._active_pipeline.transport._target_handlers[0].formatter
        assert isinstance(fmt, DiagnosticStructuredFormatter)
