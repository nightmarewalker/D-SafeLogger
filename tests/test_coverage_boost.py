"""Additional tests to improve coverage for low-coverage modules."""

from __future__ import annotations

import io
import logging
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import dsafelogger
from dsafelogger import ConfigureLogger, GetLogger, _merge_module_configs
from dsafelogger._color import ColorStreamHandler, _enable_windows_vt100
from dsafelogger._context import get_context, reset_context, set_context
from dsafelogger._formatter import DSafeFormatter, DiagnosticFormatter, StructuredFormatter
from dsafelogger._handler import AppendOnlyFileHandler
from dsafelogger._logger import DSafeLogger
from dsafelogger._purge import ArchiveWorker, PurgeWorker
from dsafelogger._routing import (
    CountStrategy,
    CyclicMonthStrategy,
    CyclicWeekdayStrategy,
    DailyStrategy,
    HourlyStrategy,
    MinIntervalStrategy,
    NoneStrategy,
    SizeStrategy,
    StartupIntervalStrategy,
    create_strategy,
)
from dsafelogger._validator import PathValidator


# =====================================================================
# _logger.py — contextualize (57% → target ~95%)
# =====================================================================
class TestDSafeLoggerContextualize:
    """Improve _logger.py coverage: contextualize method."""

    def test_basic_contextualize(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger('test_ctx')

        with logger.contextualize(task_id=42):
            ctx = get_context()
            assert ctx == {'task_id': 42}

        # After exit, context is cleaned
        assert get_context() == {}

    def test_nested_contextualize(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger('test_ctx2')

        with logger.contextualize(a=1):
            assert get_context() == {'a': 1}
            with logger.contextualize(b=2):
                assert get_context() == {'a': 1, 'b': 2}
            assert get_context() == {'a': 1}
        assert get_context() == {}

    def test_contextualize_override(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger('test_ctx3')

        with logger.contextualize(key='outer'):
            with logger.contextualize(key='inner'):
                assert get_context()['key'] == 'inner'
            assert get_context()['key'] == 'outer'

    def test_contextualize_with_exception(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger('test_ctx4')

        with pytest.raises(ValueError):
            with logger.contextualize(task='x'):
                raise ValueError('boom')
        # Context cleaned up even on exception
        assert get_context() == {}


# =====================================================================
# _validator.py — error paths (62% → target ~95%)
# =====================================================================
class TestPathValidatorErrors:
    """Improve _validator.py coverage: error paths."""

    def test_valid_directory(self, tmp_path):
        # Should not raise
        PathValidator.validate_writable(tmp_path)

    def test_auto_create_directory(self, tmp_path):
        new_dir = tmp_path / 'a' / 'b' / 'c'
        PathValidator.validate_writable(new_dir)
        assert new_dir.is_dir()

    def test_permission_error_mkdir(self, tmp_path):
        with patch.object(Path, 'mkdir', side_effect=PermissionError('denied')):
            with pytest.raises(PermissionError, match='Cannot create'):
                PathValidator.validate_writable(tmp_path / 'denied')

    def test_os_error_mkdir(self, tmp_path):
        with patch.object(Path, 'mkdir', side_effect=OSError('disk error')):
            with pytest.raises(OSError, match='Cannot create'):
                PathValidator.validate_writable(tmp_path / 'broken')

    def test_permission_error_write(self, tmp_path):
        with patch.object(Path, 'write_text', side_effect=PermissionError('denied')):
            with pytest.raises(PermissionError, match='not writable'):
                PathValidator.validate_writable(tmp_path)

    def test_os_error_write(self, tmp_path):
        with patch.object(Path, 'write_text', side_effect=OSError('io error')):
            with pytest.raises(OSError, match='Cannot write'):
                PathValidator.validate_writable(tmp_path)


# =====================================================================
# _cli.py — cmd_ls details, cmd_tail partial (46% → target ~75%)
# =====================================================================
class TestCmdLsDetails:
    """Improve _cli.py coverage: ls subcommand details."""

    def test_ls_with_nosuffix_file(self, tmp_path, capsys):
        from dsafelogger._cli import cmd_ls
        (tmp_path / 'MyApp.log').write_text('test\n', encoding='utf-8')
        cmd_ls(str(tmp_path))
        captured = capsys.readouterr()
        assert 'MyApp' in captured.out

    def test_ls_multiple_groups(self, tmp_path, capsys):
        from dsafelogger._cli import cmd_ls
        (tmp_path / 'AppA_001.log').write_text('a\n', encoding='utf-8')
        time.sleep(0.01)
        (tmp_path / 'AppB_001.log').write_text('b\n', encoding='utf-8')
        cmd_ls(str(tmp_path))
        captured = capsys.readouterr()
        assert 'AppA' in captured.out
        assert 'AppB' in captured.out


class TestCmdTailPartial:
    """Improve _cli.py coverage: tail subcommand (partial)."""

    def test_tail_single_read(self, tmp_path):
        """Test tail with a file that exists, quick exit via KeyboardInterrupt."""
        from dsafelogger._cli import cmd_tail
        log_file = tmp_path / 'Test_20260403.log'
        log_file.write_text('line1\nline2\nline3\n', encoding='utf-8')

        def interrupt_soon():
            time.sleep(0.3)
            import ctypes
            # Simulate keyboard interrupt via threading
            import _thread
            _thread.interrupt_main()

        t = threading.Thread(target=interrupt_soon, daemon=True)
        t.start()

        # Should catch the KeyboardInterrupt and exit cleanly
        cmd_tail(str(tmp_path), 'Test', initial_lines=10, poll_interval=0.1)
        t.join(timeout=2)

    def test_tail_no_files_yet(self, tmp_path):
        """Test tail when no files exist initially."""
        from dsafelogger._cli import cmd_tail

        def interrupt_soon():
            time.sleep(0.3)
            import _thread
            _thread.interrupt_main()

        t = threading.Thread(target=interrupt_soon, daemon=True)
        t.start()

        cmd_tail(str(tmp_path), 'Test', initial_lines=10, poll_interval=0.1)
        t.join(timeout=2)

    def test_tail_file_switch(self, tmp_path):
        """Test tail detecting file switch."""
        from dsafelogger._cli import cmd_tail
        log1 = tmp_path / 'Test_001.log'
        log1.write_text('old line\n', encoding='utf-8')

        call_count = [0]

        def interrupt_after_switch():
            time.sleep(0.2)
            # Create new file
            log2 = tmp_path / 'Test_002.log'
            log2.write_text('new line\n', encoding='utf-8')
            # Set mtime to be newer
            import os
            os.utime(log2, (time.time() + 1, time.time() + 1))
            time.sleep(0.5)
            import _thread
            _thread.interrupt_main()

        t = threading.Thread(target=interrupt_after_switch, daemon=True)
        t.start()

        cmd_tail(str(tmp_path), 'Test', initial_lines=10, poll_interval=0.1)
        t.join(timeout=3)


class TestCmdMainLs:
    """CLI main ls subcommand."""

    def test_ls_via_main(self, tmp_path, capsys):
        from dsafelogger._cli import main
        (tmp_path / 'X.log').write_text('data\n', encoding='utf-8')
        with patch('sys.argv', ['dsafelogger', 'ls', str(tmp_path)]):
            main()
        captured = capsys.readouterr()
        assert 'X' in captured.out


# =====================================================================
# __init__.py — helpers and advanced paths (68% → target ~80%)
# =====================================================================
class TestSanitizePgName:
    """Test _sanitize_pg_name helper."""

    def test_normal_name(self):
        from dsafelogger import _sanitize_pg_name
        assert _sanitize_pg_name('MyApp') == 'MyApp'

    def test_forbidden_chars(self):
        from dsafelogger import _sanitize_pg_name
        assert _sanitize_pg_name('My/App\\Test') == 'My_App_Test'

    def test_special_chars(self):
        from dsafelogger import _sanitize_pg_name
        assert _sanitize_pg_name('My:App*Test') == 'My_App_Test'


class TestWorkerRegistration:
    """Test worker registration helpers."""

    def test_register_and_unregister(self):
        from dsafelogger import _register_worker, _unregister_worker
        fake_worker = threading.Thread(name='test_worker')
        _register_worker(fake_worker)
        assert fake_worker in dsafelogger._active_workers
        _unregister_worker(fake_worker)
        assert fake_worker not in dsafelogger._active_workers

    def test_unregister_missing(self):
        from dsafelogger import _unregister_worker
        fake_worker = threading.Thread(name='not_registered')
        _unregister_worker(fake_worker)  # Should not raise


class TestManifestAndFamilyLocks:
    """Test shared lock helpers."""

    def test_manifest_lock_same_path(self, tmp_path):
        from dsafelogger import _get_manifest_lock
        lock1 = _get_manifest_lock(tmp_path / 'manifest.txt')
        lock2 = _get_manifest_lock(tmp_path / 'manifest.txt')
        assert lock1 is lock2

    def test_family_lock_same_key(self, tmp_path):
        from dsafelogger import _get_family_lock
        lock1 = _get_family_lock(tmp_path, 'MyApp')
        lock2 = _get_family_lock(tmp_path, 'MyApp')
        assert lock1 is lock2

    def test_family_lock_different_key(self, tmp_path):
        from dsafelogger import _get_family_lock
        lock1 = _get_family_lock(tmp_path, 'AppA')
        lock2 = _get_family_lock(tmp_path, 'AppB')
        assert lock1 is not lock2


class TestConfigureAdvanced:
    """Test ConfigureLogger advanced features."""

    def test_RegisterLevel_after_configure_raises(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        with pytest.raises(RuntimeError, match='must be called before'):
            dsafelogger.RegisterLevel('TRACE', 5, 'TRC')

    def test_enable_hash_none_mode_raises(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='enable_hash'):
            ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                enable_hash=True, routing_mode='none',
            )

    def test_manifest_path_without_hash_raises(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='manifest_path'):
            ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                enable_hash=False, manifest_path=str(tmp_path / 'manifest.txt'),
            )

    def test_archive_mode_zero_backup_raises(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='archive_mode'):
            ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                routing_mode='daily', archive_mode=True, backup_count=0,
            )

    def test_sens_kws_add_to_builtin(self, tmp_path, clean_env):
        ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            sens_kws=['my_secret'],
        )
        assert 'my_secret' in dsafelogger._resolved_sensitive_keywords
        assert 'password' in dsafelogger._resolved_sensitive_keywords

    def test_sens_kws_replace_mode(self, tmp_path, clean_env):
        ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            sens_kws=['only_this'], sens_kws_replace=True,
        )
        assert 'only_this' in dsafelogger._resolved_sensitive_keywords
        assert 'password' not in dsafelogger._resolved_sensitive_keywords

    def test_sens_kws_empty_item_raises(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='must not be empty'):
            ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                sens_kws=['valid', ''],
            )

    def test_sens_kws_non_str_item_raises(self, tmp_path, clean_env):
        with pytest.raises(TypeError, match='must be str'):
            ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                sens_kws=['valid', 123],  # type: ignore
            )

    def test_max_lines_negative(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='max_lines'):
            ConfigureLogger(max_lines=-1, log_path=str(tmp_path))

    def test_config_file_wrong_type(self, tmp_path, clean_env):
        with pytest.raises(TypeError, match='config_file'):
            ConfigureLogger(config_file=123, log_path=str(tmp_path))  # type: ignore

    def test_config_dict_wrong_type(self, tmp_path, clean_env):
        with pytest.raises(TypeError, match='config_dict'):
            ConfigureLogger(config_dict='not_dict', log_path=str(tmp_path))  # type: ignore

    def test_enable_hash_wrong_type(self, tmp_path, clean_env):
        with pytest.raises(TypeError, match='enable_hash'):
            ConfigureLogger(enable_hash='yes', log_path=str(tmp_path))  # type: ignore

    def test_custom_formatter_instance(self, tmp_path, clean_env):
        custom_fmt = logging.Formatter('%(message)s')
        ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            fmt=custom_fmt,
        )
        import dsafelogger
        for h in dsafelogger._active_pipeline.transport._target_handlers:
            if hasattr(h, '_strategy'):
                assert h.formatter is custom_fmt

    def test_async_mode_registers_atexit(self, tmp_path, clean_env):
        ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            is_async=True,
        )
        assert dsafelogger._atexit_registered is True
        assert dsafelogger._active_pipeline is not None

    def test_env_console_override(self, tmp_path, clean_env):
        os.environ['D_LOG_CONSOLE'] = '0'
        ConfigureLogger(log_path=str(tmp_path), console_out=True)
        import dsafelogger
        assert not any(isinstance(h, ColorStreamHandler) for h in dsafelogger._active_pipeline.transport._target_handlers)

    def test_env_hash_override(self, tmp_path, clean_env):
        os.environ['D_LOG_HASH'] = '1'
        ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            routing_mode='daily',
        )
        # Handler should have enable_hash set
        import dsafelogger
        for h in dsafelogger._active_pipeline.transport._target_handlers:
            if isinstance(h, AppendOnlyFileHandler):
                assert h._enable_hash is True

    def test_env_manifest_override(self, tmp_path, clean_env):
        manifest = str(tmp_path / 'env_manifest.txt')
        os.environ['D_LOG_MANIFEST'] = manifest
        ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            enable_hash=True, routing_mode='daily',
        )
        import dsafelogger
        for h in dsafelogger._active_pipeline.transport._target_handlers:
            if isinstance(h, AppendOnlyFileHandler):
                assert h._manifest_path == manifest

    def test_no_color_env(self, tmp_path, clean_env):
        os.environ['NO_COLOR'] = '1'
        ConfigureLogger(log_path=str(tmp_path), console_out=True)
        import dsafelogger
        for h in dsafelogger._active_pipeline.transport._target_handlers:
            if isinstance(h, ColorStreamHandler):
                assert h._color_enabled is False

    def test_color_env_override_false(self, tmp_path, clean_env):
        os.environ['D_LOG_COLOR'] = '0'
        ConfigureLogger(log_path=str(tmp_path), console_out=True)
        import dsafelogger
        for h in dsafelogger._active_pipeline.transport._target_handlers:
            if isinstance(h, ColorStreamHandler):
                assert h._color_enabled is False

    def test_overflow_mode_backup_raises(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='overflow-error'):
            ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                routing_mode='size', max_bytes=1024,
                max_count=None, backup_count=5,
            )

    def test_module_with_absolute_path(self, tmp_path, clean_env):
        mod_log_dir = tmp_path / 'mod_logs'
        mod_log_dir.mkdir()
        ini = tmp_path / 'test.ini'
        ini.write_text(
            f'[dsafelogger:mymod]\nlevel = DEBUG\npath = {mod_log_dir / "mod.log"}\n',
            encoding='utf-8',
        )
        ConfigureLogger(
            config_file=str(ini),
            log_path=str(tmp_path),
            console_out=False,
        )
        mod_logger = logging.getLogger('mymod')
        assert mod_logger.level == logging.DEBUG


# =====================================================================
# _handler.py — post-switch actions (75% → target ~90%)
# =====================================================================
class TestHandlerPostSwitch:
    """Improve _handler.py coverage: post-switch hash/purge/archive."""

    def test_handler_with_hash(self, tmp_path):
        strategy = SizeStrategy(tmp_path, 'Test', max_bytes=50, max_count=None, suffix_digits=3)
        handler = AppendOnlyFileHandler(
            strategy=strategy,
            enable_hash=True,
        )
        handler.setFormatter(logging.Formatter('%(message)s'))

        # Write enough to trigger switch
        for i in range(20):
            record = logging.LogRecord(
                'test', logging.INFO, 'test.py', 1,
                f'message {i} with padding text for size', (), None,
            )
            handler.emit(record)

        handler.close()
        time.sleep(1)  # Wait for hash workers

        # Should have created sidecar files
        sha_files = list(tmp_path.glob('*.sha256'))
        assert len(sha_files) >= 1

    def test_handler_with_purge(self, tmp_path):
        strategy = SizeStrategy(tmp_path, 'Test', max_bytes=30, max_count=None, suffix_digits=3)
        handler = AppendOnlyFileHandler(
            strategy=strategy,
            backup_count=2,
        )
        handler.setFormatter(logging.Formatter('%(message)s'))

        for i in range(50):
            record = logging.LogRecord(
                'test', logging.INFO, 'test.py', 1,
                f'message {i} with extra padding', (), None,
            )
            handler.emit(record)

        handler.close()
        time.sleep(1)

    def test_handler_flush(self, tmp_path):
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.flush()  # Should not crash

    def test_handler_cyclic_no_purge(self, tmp_path):
        """Cyclic strategies skip purge/archive."""
        strategy = CyclicWeekdayStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(
            strategy=strategy,
            backup_count=5,  # Should be ignored for cyclic
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, 'msg', (), None,
        )
        handler.emit(record)
        handler.close()


# =====================================================================
# _routing.py — advanced paths (78% → target ~90%)
# =====================================================================
class TestRoutingAdvanced:
    """Improve _routing.py coverage."""

    def test_daily_advance(self, tmp_path):
        s = DailyStrategy(tmp_path, 'MyApp')
        s._current_date = '20200101'
        new_path = s.advance()
        assert new_path is not None

    def test_hourly_advance(self, tmp_path):
        s = HourlyStrategy(tmp_path, 'MyApp')
        s._current_hour = '2020010100'
        new_path = s.advance()
        assert new_path is not None

    def test_min_interval_advance(self, tmp_path):
        s = MinIntervalStrategy(tmp_path, 'MyApp', 10)
        s._current_bucket = '00'
        new_path = s.advance()
        assert new_path is not None

    def test_startup_interval_advance(self, tmp_path):
        s = StartupIntervalStrategy(tmp_path, 'MyApp', 1)
        old = s.get_current_path()
        new_path = s.advance()
        assert new_path is not None

    def test_startup_interval_should_switch(self, tmp_path):
        from datetime import datetime, timedelta
        s = StartupIntervalStrategy(tmp_path, 'MyApp', 1)
        s._last_switch = datetime.now() - timedelta(minutes=2)  # 2 minutes ago
        assert s.should_switch() is True

    def test_size_with_max_count(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', max_bytes=100, max_count=3, suffix_digits=3)
        assert s.is_cyclic() is True

    def test_none_strategy_advance(self, tmp_path):
        s = NoneStrategy(tmp_path, 'MyApp')
        s.advance()
        result = s.get_current_path()
        assert result == tmp_path / 'MyApp.log'

    def test_cyclic_weekday_advance(self, tmp_path):
        s = CyclicWeekdayStrategy(tmp_path, 'MyApp')
        s._current_weekday = 'xxx'  # Force switch
        s.advance()
        p = s.get_current_path()
        assert p is not None

    def test_cyclic_month_advance(self, tmp_path):
        s = CyclicMonthStrategy(tmp_path, 'MyApp')
        s._current_month = 0  # Force switch
        s.advance()
        p = s.get_current_path()
        assert p is not None

    def test_create_all_strategies(self, tmp_path):
        for mode in ['none', 'daily', 'hourly', 'min_interval', 'startup_interval',
                      'size', 'count', 'cyclic_weekday', 'cyclic_month']:
            s = create_strategy(
                mode, tmp_path, 'Test',
                interval=10, max_bytes=1024, max_lines=100,
                max_count=5, suffix_digits=3,
            )
            assert s is not None

    def test_count_strategy_advance(self, tmp_path):
        s = CountStrategy(tmp_path, 'Test', 3, None, 3)
        s.advance()
        p = s.get_current_path()
        assert p is not None
        assert s._line_count == 0


# =====================================================================
# _formatter.py — edge cases (80% → target ~90%)
# =====================================================================
class TestFormatterEdgeCases:
    """Improve _formatter.py coverage."""

    def test_unknown_level_name(self):
        fmt = DSafeFormatter()
        record = logging.LogRecord(
            'test', 15, 'test.py', 1, 'msg', (), None,
        )
        result = fmt.format(record)
        # Level 15 has no abbreviation, should fallback
        assert 'msg' in result

    def test_structured_empty_context(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, 'msg', (), None,
        )
        import json
        data = json.loads(fmt.format(record))
        # No context keys in output
        assert 'task_id' not in data

    def test_diagnostic_chained_exception(self):
        fmt = DiagnosticFormatter()
        try:
            try:
                raise ValueError('cause')
            except ValueError:
                raise RuntimeError('effect') from None
        except RuntimeError:
            record = logging.LogRecord(
                'test', logging.ERROR, 'test.py', 1, 'msg', (), sys.exc_info(),
            )
        result = fmt.format(record)
        assert '--- Local Variables' in result

    def test_diagnostic_no_locals_in_frame(self):
        """Test when frame has no interesting locals."""
        fmt = DiagnosticFormatter()
        try:
            raise ValueError('test')
        except ValueError:
            record = logging.LogRecord(
                'test', logging.ERROR, 'test.py', 1, 'msg', (), sys.exc_info(),
            )
        result = fmt.format(record)
        assert '--- Local Variables' in result


# =====================================================================
# _color.py — VT100 enable (86% → target ~95%)
# =====================================================================
class TestWindowsVT100:
    """Test _enable_windows_vt100 function."""

    def test_enable_on_non_windows(self):
        """On non-Windows, _enable_windows_vt100 should be no-op."""
        if sys.platform != 'win32':
            _enable_windows_vt100()  # Should not raise

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows only')
    def test_enable_on_windows(self):
        _enable_windows_vt100()  # Should not raise


# =====================================================================
# _purge.py — hash-aware purge/archive (71% → target ~85%)
# =====================================================================
class TestPurgeWithHash:
    """Improve _purge.py coverage: hash-aware operations."""

    def test_purge_worker_oserror_hash(self, tmp_path, capsys):
        from dsafelogger._purge import PurgeWorker
        log_file = tmp_path / 'App_001.log'
        log_file.write_text('test', encoding='utf-8')
        
        with patch('dsafelogger._purge.write_sidecar', side_effect=OSError('hash error')):
            worker = PurgeWorker(tmp_path, 'App', 3, log_file, enable_hash=True, manifest_path=None)
            worker.run()
        
        captured = capsys.readouterr()
        assert 'Hash generation failed' in captured.err

    def test_purge_worker_oserror_unlink(self, tmp_path, capsys):
        from dsafelogger._purge import PurgeWorker
        for i in range(5):
            (tmp_path / f'App_{i:03d}.log').write_text('test', encoding='utf-8')
        
        with patch('pathlib.Path.unlink', side_effect=OSError('unlink error')):
            worker = PurgeWorker(tmp_path, 'App', backup_count=2, enable_hash=False)
            worker.run()
        
        captured = capsys.readouterr()
        assert 'Failed to delete' in captured.err

    def test_purge_worker_general_exception(self, tmp_path, capsys):
        from dsafelogger._purge import PurgeWorker
        with patch('dsafelogger._purge._list_log_files', side_effect=Exception('general error')):
            worker = PurgeWorker(tmp_path, 'App', backup_count=2)
            worker.run()
        captured = capsys.readouterr()
        assert 'PurgeWorker error:' in captured.err

    def test_archive_worker_oserror_hash(self, tmp_path, capsys):
        from dsafelogger._purge import ArchiveWorker
        log_file = tmp_path / 'App_001.log'
        log_file.write_text('test', encoding='utf-8')
        
        with patch('dsafelogger._purge.write_sidecar', side_effect=OSError('hash error')):
            worker = ArchiveWorker(tmp_path, 'App', 3, log_file, enable_hash=True, manifest_path=None)
            worker.run()
        
        captured = capsys.readouterr()
        assert 'Hash generation failed' in captured.err

    def test_archive_worker_oserror_zip(self, tmp_path, capsys):
        from dsafelogger._purge import ArchiveWorker
        for i in range(5):
            (tmp_path / f'App_{i:03d}.log').write_text('test', encoding='utf-8')
            
        with patch('zipfile.ZipFile', side_effect=OSError('zip error')):
            worker = ArchiveWorker(tmp_path, 'App', backup_count=2, enable_hash=False)
            worker.run()
            
        captured = capsys.readouterr()
        assert 'Failed to archive' in captured.err

    def test_archive_worker_oserror_unlink(self, tmp_path, capsys):
        from dsafelogger._purge import ArchiveWorker
        for i in range(5):
            (tmp_path / f'App_{i:03d}.log').write_text('test', encoding='utf-8')
            
        with patch('pathlib.Path.unlink', side_effect=OSError('unlink error')):
            worker = ArchiveWorker(tmp_path, 'App', backup_count=2, enable_hash=False)
            worker.run()
            
        captured = capsys.readouterr()
        assert 'Failed to archive' in captured.err
        
    def test_archive_worker_general_exception(self, tmp_path, capsys):
        from dsafelogger._purge import ArchiveWorker
        with patch('dsafelogger._purge._list_log_files', side_effect=Exception('general error')):
            worker = ArchiveWorker(tmp_path, 'App', backup_count=2)
            worker.run()
        captured = capsys.readouterr()
        assert 'ArchiveWorker error:' in captured.err

    def test_purge_with_hash_and_manifest(self, tmp_path):
        import time as t
        for i in range(5):
            f = tmp_path / f'App_{i:03d}.log'
            f.write_bytes(f'content {i}\n'.encode('utf-8'))
            sidecar = f.with_suffix('.log.sha256')
            sidecar.write_text(f'hash  App_{i:03d}.log\n', encoding='utf-8')
            t.sleep(0.01)

        manifest = tmp_path / 'manifest.txt'
        worker = PurgeWorker(
            tmp_path, 'App', backup_count=3,
            enable_hash=True,
            manifest_path=str(manifest),
        )
        worker.start()
        worker.join(timeout=5)

        remaining = list(tmp_path.glob('App_*.log'))
        assert len(remaining) == 3

    def test_archive_with_hash(self, tmp_path):
        import time as t
        for i in range(5):
            f = tmp_path / f'App_{i:03d}.log'
            f.write_bytes(f'content {i}\n'.encode('utf-8'))
            t.sleep(0.01)

        worker = ArchiveWorker(
            tmp_path, 'App', backup_count=3,
            enable_hash=True,
        )
        worker.start()
        worker.join(timeout=10)

        remaining_logs = list(tmp_path.glob('App_*.log'))
        zip_files = list(tmp_path.glob('App_*.log.zip'))
        assert len(remaining_logs) == 3
        assert len(zip_files) == 2


# =====================================================================
# _ini_loader.py — DictLoader color palette (76% → target ~85%)
# =====================================================================
class TestIniLoaderColorPalette:
    """Improve _ini_loader.py coverage: color palette parsing."""

    def test_ini_color_palette(self, tmp_path):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[global]\ndefault_level = INFO\ncolor_dbg = 90\ncolor_err = 91\n',
            encoding='utf-8',
        )
        from dsafelogger._ini_loader import IniLoader
        import configparser
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(str(ini), encoding='utf-8')
        from dsafelogger._levels import get_valid_abbreviations
        result = IniLoader._parse_color_palette(parser, get_valid_abbreviations())
        assert result.get('DBG') == '90'
        assert result.get('ERR') == '91'

    def test_dict_color_palette(self):
        from dsafelogger._ini_loader import DictLoader
        from dsafelogger._levels import get_valid_abbreviations
        config = {'global': {'color_dbg': '90', 'color_err': ''}}
        result = DictLoader._parse_color_palette(config, get_valid_abbreviations())
        assert result.get('DBG') == '90'
        assert result.get('ERR') == ''

    def test_ini_global_routing_mode(self, tmp_path):
        ini = tmp_path / 'test.ini'
        ini.write_text('[global]\nrouting_mode = daily\n', encoding='utf-8')
        from dsafelogger._ini_loader import IniLoader
        g, _ = IniLoader.load(str(ini))
        assert g['routing_mode'] == 'daily'

    def test_ini_global_all_str_keys(self, tmp_path):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[global]\nlog_path = /tmp/logs\npg_name = Test\n'
            'env_prefix = MY_LOG\nfmt = %(message)s\ndatefmt = %H:%M\n',
            encoding='utf-8',
        )
        from dsafelogger._ini_loader import IniLoader
        g, _ = IniLoader.load(str(ini))
        assert g['log_path'] == '/tmp/logs'
        assert g['pg_name'] == 'Test'
        assert g['env_prefix'] == 'MY_LOG'
        assert g['fmt'] == '%(message)s'
        assert g['datefmt'] == '%H:%M'

    def test_ini_module_all_keys(self, tmp_path):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[dsafelogger:mymod]\nlevel = DEBUG\npath = mod.log\n'
            'routing_mode = size\nmax_bytes = 1024\nmax_lines = 100\n'
            'max_count = 5\nsuffix_digits = 4\nbackup_count = 3\n'
            'archive_mode = true\n',
            encoding='utf-8',
        )
        from dsafelogger._ini_loader import IniLoader
        _, m = IniLoader.load(str(ini))
        assert m['mymod']['level'] == 'DEBUG'
        assert m['mymod']['path'] == 'mod.log'
        assert m['mymod']['routing_mode'] == 'size'
        assert m['mymod']['max_bytes'] == 1024
        assert m['mymod']['max_count'] == 5
        assert m['mymod']['backup_count'] == 3
        assert m['mymod']['archive_mode'] is True
