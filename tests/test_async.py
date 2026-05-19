"""Tests for dsafelogger._async (DSafeQueueHandler, DSafeQueueListener, shutdown)."""

from __future__ import annotations

import copy
import logging
import queue
import sys
import threading
from unittest.mock import patch

import pytest
import dsafelogger
from dsafelogger._async import DSafeQueueHandler, DSafeQueueListener
from dsafelogger._handler import AppendOnlyFileHandler
from dsafelogger._context import get_context, reset_context, set_context


class TestDSafeQueueHandler:
    """UT-QH: DSafeQueueHandler tests."""

    def test_prepare_does_not_call_super(self):
        """prepare() should NOT call super().prepare() (no destructive formatting)."""
        q = queue.Queue()
        handler = DSafeQueueHandler(q)

        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, 'msg', (), None,
        )
        prepared = handler.prepare(record)
        # Should be a copy, not the original
        assert prepared is not record

    def test_prepare_context_snapshot(self):
        q = queue.Queue()
        handler = DSafeQueueHandler(q)

        token = set_context({'request_id': 'abc'})
        try:
            record = logging.LogRecord(
                'test', logging.INFO, 'test.py', 1, 'msg', (), None,
            )
            prepared = handler.prepare(record)
            assert prepared._ds_context == {'request_id': 'abc'}
        finally:
            reset_context(token)

    def test_prepare_fast_path_no_diagnose(self):
        """Without diagnose, only context snapshot is made."""
        from dsafelogger import _constants
        _constants._diagnose_enabled = False
        q = queue.Queue()
        handler = DSafeQueueHandler(q)

        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, 'msg', (), None,
        )
        prepared = handler.prepare(record)
        assert hasattr(prepared, '_ds_context')
        assert not hasattr(prepared, '_ds_diag_frames')

    def test_prepare_diagnose_path(self):
        """With diagnose=True and exception, snapshot frames."""
        from dsafelogger import _constants
        _constants._diagnose_enabled = True
        q = queue.Queue()
        handler = DSafeQueueHandler(q)

        try:
            raise ValueError('test error')
        except ValueError:
            record = logging.LogRecord(
                'test', logging.ERROR, 'test.py', 1, 'msg', (), sys.exc_info(),
            )
            prepared = handler.prepare(record)
            assert hasattr(prepared, '_ds_exc_text')
            assert hasattr(prepared, '_ds_diag_frames')
            assert isinstance(prepared._ds_diag_frames, list)

    def test_prepare_diagnose_masks_custom_sensitive_keywords(self):
        """Diagnose snapshots must be masked before async handoff."""
        from dsafelogger import _constants
        original_diagnose = _constants._diagnose_enabled
        original_keywords = _constants._resolved_sensitive_keywords
        _constants._diagnose_enabled = True
        _constants._resolved_sensitive_keywords = frozenset({'credit_card'})
        q = queue.Queue()
        handler = DSafeQueueHandler(q)

        try:
            try:
                credit_card = '4111-1111-1111-1111'  # noqa: F841
                public_value = 'visible-value'  # noqa: F841
                raise ValueError('test error')
            except ValueError:
                record = logging.LogRecord(
                    'test', logging.ERROR, 'test.py', 1, 'msg', (), sys.exc_info(),
                )
                prepared = handler.prepare(record)
        finally:
            _constants._diagnose_enabled = original_diagnose
            _constants._resolved_sensitive_keywords = original_keywords

        variables = {}
        for frame in prepared._ds_diag_frames:
            variables.update(frame['variables'])
        assert variables['credit_card'] == '*** MASKED ***'
        assert variables['public_value'] == "'visible-value'"
        assert '4111-1111-1111-1111' not in repr(prepared._ds_diag_frames)


class TestDSafeQueueListener:
    """UT-QL: DSafeQueueListener tests."""

    def test_start_and_stop(self):
        q = queue.Queue()
        handler = logging.StreamHandler()
        listener = DSafeQueueListener(q, handler)
        listener.start()
        listener.stop_with_timeout(1.0)


class TestShutdown:
    """UT-SD: Shutdown tests."""

    def test_shutdown_idempotent(self, tmp_path, clean_env):
        from dsafelogger import ConfigureLogger, _shutdown
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        _shutdown()
        _shutdown()  # Second call should be no-op
        assert dsafelogger._configure_state == 'shutting_down'

    def test_shutdown_from_unconfigured(self):
        from dsafelogger import _shutdown
        _shutdown()  # Should be no-op when unconfigured

    def test_shutdown_closes_async_listener_handlers(self, tmp_path, clean_env):
        from dsafelogger import ConfigureLogger, GetLogger, _shutdown

        closed_handlers: list[AppendOnlyFileHandler] = []
        original_close = AppendOnlyFileHandler.close

        def tracking_close(self):
            closed_handlers.append(self)
            return original_close(self)

        with patch.object(AppendOnlyFileHandler, 'close', tracking_close):
            ConfigureLogger(log_path=str(tmp_path), console_out=False, is_async=True)
            logger = GetLogger('demo')
            logger.info('hello')
            _shutdown()

        assert len(closed_handlers) == 1


class TestStateTransitions:
    """UT-SS: State transition safety tests."""

    def test_configuring_blocks_reconfigure(self, tmp_path, clean_env):
        """Concurrent ConfigureLogger during 'configuring' should not double-init."""
        from dsafelogger import ConfigureLogger
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        # Should be no-op
        ConfigureLogger(log_path=str(tmp_path), default_level='DEBUG', console_out=False)
        # State should remain 'explicit'
        assert dsafelogger._configure_state == 'explicit'

    def test_shutting_down_blocks_configure(self, tmp_path, clean_env):
        from dsafelogger import ConfigureLogger, _shutdown
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        _shutdown()
        # After shutdown, ConfigureLogger should be no-op
        ConfigureLogger(log_path=str(tmp_path), default_level='DEBUG', console_out=False)
        assert dsafelogger._configure_state == 'shutting_down'
