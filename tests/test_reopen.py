"""Tests for ReopenLogFiles() and AppendOnlyFileHandler.reopen().

Covers:
    UT-REOPEN-001 to UT-REOPEN-007  (§29.9)
    UT-AH-015                        (§7 handler reopen contract)
"""
from __future__ import annotations

import logging
import signal
import threading
import time

import pytest

import dsafelogger
from dsafelogger._handler import AppendOnlyFileHandler
from dsafelogger._routing import DailyStrategy, NoneStrategy, create_strategy


# ── UT-AH-015: AppendOnlyFileHandler.reopen() contract ───────────────────────


class TestHandlerReopen:

    def test_reopen_none_strategy_succeeds(self, tmp_path):
        """reopen() with NoneStrategy closes and reopens the file handle."""
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        rec = logging.makeLogRecord({'msg': 'before', 'levelno': logging.INFO})
        handler.emit(rec)

        handler.reopen()

        rec2 = logging.makeLogRecord({'msg': 'after', 'levelno': logging.INFO})
        handler.emit(rec2)
        handler.close()

        content = (tmp_path / 'Test.log').read_text(encoding='utf-8')
        assert 'before' in content
        assert 'after' in content

    def test_reopen_non_none_strategy_raises_value_error(self, tmp_path):
        """UT-AH-015: reopen() on non-NoneStrategy handler raises ValueError."""
        strategy = create_strategy(
            routing_mode='daily',
            base_dir=tmp_path,
            pg_name='Test',
        )
        handler = AppendOnlyFileHandler(strategy=strategy)
        with pytest.raises(ValueError, match='routing_mode'):
            handler.reopen()
        handler.close()

    def test_reopen_self_exclusive(self, tmp_path):
        """UT-REOPEN-007: concurrent emit() and reopen() do not corrupt output."""
        strategy = NoneStrategy(tmp_path, 'Concurrent')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        stop_flag = threading.Event()
        errors: list[Exception] = []

        def emit_loop():
            while not stop_flag.is_set():
                try:
                    rec = logging.makeLogRecord({'msg': 'ping', 'levelno': logging.INFO})
                    handler.emit(rec)
                except Exception as exc:
                    errors.append(exc)

        t = threading.Thread(target=emit_loop, daemon=True)
        t.start()
        for _ in range(5):
            try:
                handler.reopen()
            except Exception as exc:
                errors.append(exc)
        stop_flag.set()
        t.join(timeout=2.0)
        handler.close()
        assert errors == [], f'Errors during concurrent reopen: {errors}'


# ── UT-REOPEN: dsafelogger.ReopenLogFiles() contract ────────────────────────


class TestReopenLogFiles:

    def test_unconfigured_raises_runtime_error(self):
        """UT-REOPEN-001: unconfigured state raises RuntimeError."""
        # reset_logger_state fixture ensures unconfigured state
        with pytest.raises(RuntimeError, match='ConfigureLogger'):
            dsafelogger.ReopenLogFiles()

    def test_none_strategy_reopens_file_sink(self, tmp_path):
        """UT-REOPEN-002: routing_mode='none' file sink is reopened once."""
        dsafelogger.ConfigureLogger(
            log_path=str(tmp_path),
            routing_mode='none',
            console_out=False,
        )
        dsafelogger.ReopenLogFiles()  # must not raise

    def test_module_specific_path_both_reopened(self, tmp_path):
        """UT-REOPEN-003: root and module-specific file sinks both reopened."""
        mod_dir = tmp_path / 'mod'
        mod_dir.mkdir()
        dsafelogger.ConfigureLogger(
            log_path=str(tmp_path),
            routing_mode='none',
            console_out=False,
            config_dict={
                'global': {},
                'myapp.db': {'path': str(mod_dir / 'db.log')},
            },
        )
        dsafelogger.ReopenLogFiles()  # must not raise

    def test_no_file_sinks_raises_runtime_error(self, tmp_path):
        """UT-REOPEN-004: pipeline with no file sinks raises RuntimeError."""
        from unittest.mock import patch
        dsafelogger.ConfigureLogger(
            log_path=str(tmp_path),
            routing_mode='none',
            console_out=True,
        )
        # Mock reopen_file_sinks to return 0 (simulate console-only pipeline)
        with patch.object(
            dsafelogger._active_pipeline, 'reopen_file_sinks', return_value=0
        ):
            with pytest.raises(RuntimeError, match='no file sinks'):
                dsafelogger.ReopenLogFiles()

    def test_console_only_raises_runtime_error(self, tmp_path, monkeypatch):
        """Console-only configuration has no file sinks to reopen."""
        monkeypatch.chdir(tmp_path)
        dsafelogger.ConfigureLogger(console_out='only')
        with pytest.raises(RuntimeError, match='no file sinks'):
            dsafelogger.ReopenLogFiles()

    def test_routing_mode_non_none_raises_value_error(self, tmp_path):
        """UT-REOPEN-005: routing_mode='daily' raises ValueError."""
        dsafelogger.ConfigureLogger(
            log_path=str(tmp_path),
            routing_mode='daily',
            console_out=False,
        )
        with pytest.raises(ValueError):
            dsafelogger.ReopenLogFiles()

    def test_no_signal_handler_registered(self, tmp_path):
        """UT-REOPEN-006: ConfigureLogger does not install signal handlers."""
        import signal as _signal
        before = _signal.getsignal(_signal.SIGTERM)
        dsafelogger.ConfigureLogger(
            log_path=str(tmp_path),
            routing_mode='none',
            console_out=False,
        )
        assert _signal.getsignal(_signal.SIGTERM) == before
