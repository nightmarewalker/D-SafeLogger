"""Transport layer for D-SafeLogger.

Isolates execution mode (sync vs async) from the Capture and Sink layers.
"""
from __future__ import annotations

import abc
import queue
import logging
import sys
from typing import Any, Sequence

from dsafelogger._constants import QUEUE_DRAIN_TIMEOUT_SEC
from dsafelogger._context import _snapshot_context


class Transport(abc.ABC):
    """Abstract base class for event transport mechanisms (v20)."""

    @abc.abstractmethod
    def start(self) -> None:
        """Start the transport."""

    @abc.abstractmethod
    def stop(self, timeout: float | None = None) -> bool:
        """Stop the transport, flushing any pending logs."""

    @abc.abstractmethod
    def get_root_handler(self) -> logging.Handler:
        """Return the logging.Handler instance to be attached to the logger."""

    def get_root_handlers(self) -> list[logging.Handler]:
        """Return all root handlers for this transport (default: single handler)."""
        return [self.get_root_handler()]

    def get_sink_handlers(self) -> list[logging.Handler]:
        """Return writer-side (file/console) handlers for reopen/close purposes.

        v22a: Used by Pipeline.reopen_file_sinks() to collect AppendOnlyFileHandler
        instances without touching the producer-side QueueHandler.
        Default returns get_root_handlers(); QueueTransport overrides to return
        listener-side handlers only.
        """
        return self.get_root_handlers()


class DirectTransport(Transport):
    """Synchronous transport that directly calls target handlers."""

    def __init__(self, handlers: Sequence[logging.Handler]) -> None:
        self._target_handlers = list(handlers)
        self._proxy_handler = self._DirectProxyHandler(self._target_handlers)

    def start(self) -> None:
        pass

    def stop(self, timeout: float | None = None) -> bool:
        errors = []
        for h in self._target_handlers:
            # flush and close are kept in separate try blocks so that a flush
            # failure never skips close().  Skipping close() would leave the
            # handler registered in logging._handlerList, causing spurious
            # exceptions in logging.shutdown() at interpreter exit.
            try:
                h.flush()
            except Exception as e:
                errors.append(e)
            try:
                h.close()
            except Exception as e:
                errors.append(e)
        if errors:
            print(f'[D-SafeLogger] DirectTransport.stop: {len(errors)} handler(s) failed', file=sys.stderr)
        return True

    def get_root_handler(self) -> logging.Handler:
        return self._proxy_handler

    def get_sink_handlers(self) -> list[logging.Handler]:
        return list(self._target_handlers)

    class _DirectProxyHandler(logging.Handler):
        def __init__(self, target_handlers: list[logging.Handler]) -> None:
            super().__init__()
            self._target_handlers = target_handlers

        def emit(self, record: logging.LogRecord) -> None:
            # Snap context on producer thread
            if not hasattr(record, '_ds_context'):
                record._ds_context = _snapshot_context()

            for h in self._target_handlers:
                # Handle error per handler
                try:
                    h.handle(record)
                except Exception:
                    self.handleError(record)


class QueueTransport(Transport):
    """Asynchronous transport using Queue."""

    def __init__(self, handlers: Sequence[logging.Handler], queue_size: int = -1) -> None:
        from dsafelogger._async import DSafeQueueHandler, DSafeQueueListener
        self._target_handlers = list(handlers)
        self._queue: queue.Queue[logging.LogRecord] = queue.Queue(queue_size)
        self._handler = DSafeQueueHandler(self._queue)
        self._listener = DSafeQueueListener(
            self._queue, *self._target_handlers, respect_handler_level=True
        )

    def start(self) -> None:
        self._listener.start()

    def stop(self, timeout: float | None = None) -> bool:
        if timeout is None:
            timeout = QUEUE_DRAIN_TIMEOUT_SEC

        # Stop listener
        if hasattr(self._listener, 'stop_with_timeout'):
            self._listener.stop_with_timeout(timeout)
        else:
            self._listener.stop()

        # Close all target handlers.  flush and close are kept in separate try
        # blocks so that a flush failure never skips close() — same reasoning
        # as DirectTransport.stop().
        errors = []
        for h in self._target_handlers:
            try:
                h.flush()
            except Exception as e:
                errors.append(e)
            try:
                h.close()
            except Exception as e:
                errors.append(e)
        if errors:
            print(f'[D-SafeLogger] QueueTransport.stop: {len(errors)} handler(s) failed', file=sys.stderr)
        return True

    def get_root_handler(self) -> logging.Handler:
        return self._handler

    def get_sink_handlers(self) -> list[logging.Handler]:
        # v22a: return listener-side handlers (the actual file/console sinks),
        # NOT the producer-side QueueHandler, for reopen purposes.
        return list(self._target_handlers)


class TransportFactory:
    """Creates the appropriate transport based on is_async flag."""

    @staticmethod
    def create(
        is_async: bool,
        handlers: Sequence[logging.Handler],
        **kwargs: Any,
    ) -> Transport:
        """Create the appropriate Transport.

        Args:
            is_async: If True, use QueueTransport; otherwise DirectTransport.
            handlers: Sink handlers.
            **kwargs: Passed to QueueTransport (e.g. queue_size).
        """
        if is_async:
            queue_size = kwargs.get('queue_size', -1)
            return QueueTransport(handlers, queue_size=queue_size)
        return DirectTransport(handlers)
