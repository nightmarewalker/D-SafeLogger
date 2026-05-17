"""Tests for dsafelogger._transport.py."""

from __future__ import annotations

import logging
import time
from typing import Any

from dsafelogger._transport import DirectTransport, QueueTransport, TransportFactory
from dsafelogger._context import contextualize


class _MockHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.closed = False
        self.flushed = False

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def close(self) -> None:
        self.closed = True
        super().close()  # Deregisters from logging._handlerList; prevents atexit flush errors.

    def flush(self) -> None:
        self.flushed = True


def test_direct_transport():
    h1 = _MockHandler()
    h2 = _MockHandler()
    transport = DirectTransport([h1, h2])
    
    root_handler = transport.get_root_handler()
    
    # 1. Start does nothing for direct
    transport.start()
    
    # 2. Emitting records
    record = logging.LogRecord('test', logging.INFO, 'test.py', 1, 'msg', (), None)
    with contextualize(key='val'):
        root_handler.handle(record)
    
    assert len(h1.records) == 1
    assert len(h2.records) == 1
    
    # Verify context snapshot worked
    assert h1.records[0].msg == 'msg'
    assert hasattr(h1.records[0], '_ds_context')
    assert h1.records[0]._ds_context.get('key') == 'val'
    
    # 3. Stop closes underlying handlers
    transport.stop()
    assert h1.closed
    assert h2.closed
    assert h1.flushed
    assert h2.flushed


def test_queue_transport():
    h1 = _MockHandler()
    transport = QueueTransport([h1], queue_size=10)
    root_handler = transport.get_root_handler()
    
    # 1. Start listener
    transport.start()
    
    # 2. Emit records
    record = logging.LogRecord('test', logging.INFO, 'test.py', 1, 'async msg', (), None)
    with contextualize(uid=123):
        root_handler.handle(record)
        
    # Give listener time to process
    time.sleep(0.1)
    
    assert len(h1.records) == 1
    assert getattr(h1.records[0], '_ds_context', {}).get('uid') == 123
    
    # 3. Stop
    transport.stop(timeout=1.0)
    assert h1.flushed
    assert h1.closed


def test_transport_factory():
    h1 = _MockHandler()
    
    t_sync = TransportFactory.create(is_async=False, handlers=[h1])
    assert isinstance(t_sync, DirectTransport)
    
    t_async = TransportFactory.create(is_async=True, handlers=[h1], queue_size=5)
    assert isinstance(t_async, QueueTransport)
    assert t_async._queue.maxsize == 5

def test_direct_transport_stop_errors(capsys):
    from unittest.mock import patch
    h = _MockHandler()
    t = DirectTransport([h])
    # Use patch.object so the mock is restored after the with block.
    # Direct attribute assignment (h.flush = MagicMock(...)) leaves the mock
    # on the instance indefinitely; on free-threaded Python h may still be alive
    # when logging.shutdown() runs at atexit, causing a spurious exception.
    with patch.object(h, 'flush', side_effect=Exception('flush error')):
        t.stop()
    captured = capsys.readouterr()
    assert 'DirectTransport.stop: 1 handler(s) failed' in captured.err

def test_direct_transport_emit_errors():
    from unittest.mock import patch, MagicMock
    h = _MockHandler()
    h.handle = MagicMock(side_effect=Exception('handle error'))
    t = DirectTransport([h])
    proxy = t.get_root_handler()
    
    with patch.object(proxy, 'handleError') as mock_err:
        rec = logging.LogRecord('test', logging.INFO, 'test.py', 1, 'msg', (), None)
        proxy.emit(rec)
        mock_err.assert_called_once_with(rec)

def test_queue_transport_stop_errors(capsys):
    from unittest.mock import patch
    h = _MockHandler()
    t = QueueTransport([h])
    t.start()
    # Same reasoning as test_direct_transport_stop_errors: use patch.object so
    # the mock is cleaned up after the with block and does not linger on h.
    with patch.object(h, 'flush', side_effect=Exception('flush error')):
        t.stop(timeout=0.1)
    captured = capsys.readouterr()
    assert 'QueueTransport.stop: 1 handler(s) failed' in captured.err

def test_queue_transport_listener_stop_fallback():
    from unittest.mock import MagicMock
    h = _MockHandler()
    t = QueueTransport([h])
    # Replace listener with a mock that lacks stop_with_timeout
    class MockListener:
        def start(self): pass
        def stop(self): pass
    
    t._listener = MockListener()
    t._listener.start = MagicMock()
    t._listener.stop = MagicMock()
    t.start()
    t.stop()
    t._listener.stop.assert_called_once()

