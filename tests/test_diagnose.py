"""Tests for D_LOG_DIAGNOSE (environment-only sanctuary)."""

from __future__ import annotations

import json
import logging
import os

import pytest
import dsafelogger
from dsafelogger import ConfigureLogger, GetLogger, _shutdown
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

    def test_sens_kws_masks_sync_text_diagnostic_output(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '1'
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DiagText',
            console_out=False,
            sens_kws=['credit_card'],
        )
        logger = GetLogger('diag.text')

        try:
            credit_card = '4111-1111-1111-1111'  # noqa: F841
            public_value = 'visible-value'  # noqa: F841
            raise RuntimeError('payment failed')
        except RuntimeError:
            logger.exception('captured payment failure')
        _shutdown()

        output = (tmp_path / 'DiagText.log').read_text(encoding='utf-8')
        assert 'credit_card = *** MASKED ***' in output
        assert '4111-1111-1111-1111' not in output
        assert 'public_value' in output
        assert 'visible-value' in output

    def test_sens_kws_replace_controls_sync_text_masking(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '1'
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DiagReplace',
            console_out=False,
            sens_kws=['customer_id'],
            sens_kws_replace=True,
        )
        logger = GetLogger('diag.replace')

        try:
            customer_id = 'cust-secret'  # noqa: F841
            token = 'token-visible-when-replaced'  # noqa: F841
            raise RuntimeError('replace mode')
        except RuntimeError:
            logger.exception('captured replace mode')
        _shutdown()

        output = (tmp_path / 'DiagReplace.log').read_text(encoding='utf-8')
        assert 'customer_id = *** MASKED ***' in output
        assert 'cust-secret' not in output
        assert "token = 'token-visible-when-replaced'" in output

    def test_sens_kws_masks_sync_structured_diagnostic_output(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '1'
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DiagJson',
            structured=True,
            console_out=False,
            sens_kws=['credit_card'],
        )
        logger = GetLogger('diag.json')

        try:
            credit_card = '4111-1111-1111-1111'  # noqa: F841
            raise RuntimeError('json failure')
        except RuntimeError:
            logger.exception('captured json failure')
        _shutdown()

        record = json.loads((tmp_path / 'DiagJson.log').read_text(encoding='utf-8'))
        variables = {}
        for frame in record['locals']:
            variables.update(frame['variables'])
        assert variables['credit_card'] == '*** MASKED ***'
        assert '4111-1111-1111-1111' not in json.dumps(record, ensure_ascii=False)

    def test_sens_kws_masks_async_text_diagnostic_output(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '1'
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DiagAsyncText',
            console_out=False,
            is_async=True,
            sens_kws=['credit_card'],
        )
        logger = GetLogger('diag.async.text')

        try:
            credit_card = '4111-1111-1111-1111'  # noqa: F841
            raise RuntimeError('async payment failed')
        except RuntimeError:
            logger.exception('captured async payment failure')
        _shutdown()

        output = (tmp_path / 'DiagAsyncText.log').read_text(encoding='utf-8')
        assert 'credit_card = *** MASKED ***' in output
        assert '4111-1111-1111-1111' not in output

    def test_sens_kws_masks_async_structured_diagnostic_output(self, tmp_path, clean_env):
        os.environ['D_LOG_DIAGNOSE'] = '1'
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DiagAsyncJson',
            structured=True,
            console_out=False,
            is_async=True,
            sens_kws=['credit_card'],
        )
        logger = GetLogger('diag.async.json')

        try:
            credit_card = '4111-1111-1111-1111'  # noqa: F841
            raise RuntimeError('async json failure')
        except RuntimeError:
            logger.exception('captured async json failure')
        _shutdown()

        record = json.loads((tmp_path / 'DiagAsyncJson.log').read_text(encoding='utf-8'))
        variables = {}
        for frame in record['locals']:
            variables.update(frame['variables'])
        assert variables['credit_card'] == '*** MASKED ***'
        assert '4111-1111-1111-1111' not in json.dumps(record, ensure_ascii=False)
