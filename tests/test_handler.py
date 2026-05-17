"""Tests for dsafelogger._handler (AppendOnlyFileHandler)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest
from dsafelogger._handler import AppendOnlyFileHandler
from dsafelogger._routing import (
    CountStrategy,
    DailyStrategy,
    NoneStrategy,
    SizeStrategy,
    create_strategy,
)


class TestAppendOnlyFileHandler:
    """UT-AH: AppendOnlyFileHandler tests."""

    def test_initial_write(self, tmp_path):
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, 'hello', (), None,
        )
        handler.emit(record)
        handler.close()

        log_file = tmp_path / 'Test.log'
        assert log_file.exists()
        assert 'hello' in log_file.read_text(encoding='utf-8')

    def test_append_mode(self, tmp_path):
        """Verify append mode (not overwrite)."""
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        for msg in ('line1', 'line2', 'line3'):
            record = logging.LogRecord(
                'test', logging.INFO, 'test.py', 1, msg, (), None,
            )
            handler.emit(record)

        handler.close()

        content = (tmp_path / 'Test.log').read_text(encoding='utf-8')
        assert 'line1' in content
        assert 'line2' in content
        assert 'line3' in content

    def test_utf8_encoding(self, tmp_path):
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, '日本語テスト', (), None,
        )
        handler.emit(record)
        handler.close()

        content = (tmp_path / 'Test.log').read_text(encoding='utf-8')
        assert '日本語テスト' in content

    def test_directory_auto_creation(self, tmp_path):
        deep_dir = tmp_path / 'a' / 'b' / 'c'
        strategy = NoneStrategy(deep_dir, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, 'deep', (), None,
        )
        handler.emit(record)
        handler.close()

        assert (deep_dir / 'Test.log').exists()

    def test_file_switch_size(self, tmp_path):
        """Test file switching when size limit is exceeded."""
        strategy = SizeStrategy(tmp_path, 'Test', max_bytes=50, max_count=None, suffix_digits=3)
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        # Write enough to trigger switch
        for i in range(10):
            record = logging.LogRecord(
                'test', logging.INFO, 'test.py', 1,
                f'message {i} with some extra padding text here', (), None,
            )
            handler.emit(record)

        handler.close()

        # Should have created multiple files
        log_files = list(tmp_path.glob('Test_*.log'))
        assert len(log_files) >= 2

    def test_file_switch_count(self, tmp_path):
        """Test file switching when line count is exceeded."""
        strategy = CountStrategy(tmp_path, 'Test', max_lines=3, max_count=None, suffix_digits=3)
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        for i in range(9):
            record = logging.LogRecord(
                'test', logging.INFO, 'test.py', 1, f'line {i}', (), None,
            )
            handler.emit(record)

        handler.close()

        log_files = list(tmp_path.glob('Test_*.log'))
        assert len(log_files) >= 3

    def test_close_flushes(self, tmp_path):
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        record = logging.LogRecord(
            'test', logging.INFO, 'test.py', 1, 'buffered', (), None,
        )
        handler.emit(record)
        handler.close()

        content = (tmp_path / 'Test.log').read_text(encoding='utf-8')
        assert 'buffered' in content

    def test_cyclic_size_mode_hashes_completed_files(self, tmp_path):
        strategy = SizeStrategy(tmp_path, 'Test', max_bytes=30, max_count=2, suffix_digits=3)
        manifest = tmp_path / 'manifest.txt'
        handler = AppendOnlyFileHandler(
            strategy=strategy,
            enable_hash=True,
            manifest_path=str(manifest),
        )
        handler.setFormatter(logging.Formatter('%(message)s'))

        for i in range(20):
            record = logging.LogRecord(
                'test', logging.INFO, 'test.py', 1,
                f'message {i} with padding', (), None,
            )
            handler.emit(record)

        handler.close()
        time.sleep(1)

        assert list(tmp_path.glob('*.sha256'))
        assert manifest.exists()

    def test_file_switch_rollback(self, tmp_path):
        """UT-SF: Verify rollback behavior if new file open fails during switch."""
        from unittest import mock
        
        strategy = SizeStrategy(tmp_path, 'Test', max_bytes=50, max_count=None, suffix_digits=3)
        handler = AppendOnlyFileHandler(strategy=strategy)
        handler.setFormatter(logging.Formatter('%(message)s'))

        # Write first line
        record1 = logging.LogRecord('test', logging.INFO, 'test.py', 1, 'initial', (), None)
        handler.emit(record1)
        
        # Next write will trigger switch. Mock open to fail.
        record2 = logging.LogRecord('test', logging.INFO, 'test.py', 1, 'very long line to trigger switch', (), None)
        
        original_open = __builtins__['open']
        def mock_open(*args, **kwargs):
            if 'Test_001.log' in str(args[0]):
                raise OSError("Mock disk full")
            return original_open(*args, **kwargs)
            
        with mock.patch('builtins.open', side_effect=mock_open):
            handler.emit(record2)
            
        handler.close()
        
        # The switch failed, but the old file 'Test_000.log' should contain BOTH lines
        # because the handler caught the OSError, called handleError, and left the stream active.
        # Wait, if switch fails, handleError is called, but it doesn't write the current record to the old stream.
        # Actually, handleError handles the exception for record2. Then it returns?
        # Let's check emit:
        # try:
        #   if should_switch():
        #       _switch_file(record) # This calls handleError and returns None. The exception was caught IN _switch_file!
        # Wait, if _switch_file catches OSError and doesn't re-raise, it returns normally!
        # And the old stream is still open!
        # So it WILL write record2 to the OLD stream.
        content = (tmp_path / 'Test_000.log').read_text(encoding='utf-8')
        assert 'initial' in content
        assert 'very long line to trigger switch' in content

    def test_stream_flush_on_emit_default_true(self, tmp_path):
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy)
        assert handler._stream_flush_on_emit is True
        handler.close()

    def test_stream_flush_on_emit_false_no_auto_flush(self, tmp_path):
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy, stream_flush_on_emit=False)
        handler.setFormatter(logging.Formatter('%(message)s'))
        assert handler._stream_flush_on_emit is False

        record = logging.LogRecord('t', logging.INFO, '', 0, 'batch_msg', (), None)
        handler.emit(record)

        # Data is in Python buffer; explicit flush brings it to the file
        handler.flush()
        content = (tmp_path / 'Test.log').read_text(encoding='utf-8')
        assert 'batch_msg' in content
        handler.close()

    def test_stream_flush_on_emit_false_close_flushes(self, tmp_path):
        strategy = NoneStrategy(tmp_path, 'Test')
        handler = AppendOnlyFileHandler(strategy=strategy, stream_flush_on_emit=False)
        handler.setFormatter(logging.Formatter('%(message)s'))

        record = logging.LogRecord('t', logging.INFO, '', 0, 'close_flush', (), None)
        handler.emit(record)
        handler.close()  # _close_stream calls flush then close

        content = (tmp_path / 'Test.log').read_text(encoding='utf-8')
        assert 'close_flush' in content
