"""Sink layer abstractions for D-SafeLogger.

FileSink, ConsoleSink, and SinkGroup are the Writer-side output abstractions
used by WriterRuntime in the multiprocess namespace (dsafelogger.mp).

Single-process mode continues to use AppendOnlyFileHandler via Transport;
these classes provide the parallel abstraction for the Writer/runtime side.
"""
from __future__ import annotations

import logging

from dsafelogger._handler import AppendOnlyFileHandler


class FileSink:
    """Writer-side file sink.

    Wraps AppendOnlyFileHandler and owns the file lifecycle
    (open/switch/reopen/maintenance) on behalf of WriterRuntime.
    """

    def __init__(self, handler: AppendOnlyFileHandler) -> None:
        self._handler = handler

    def emit(self, record: logging.LogRecord) -> None:
        self._handler.handle(record)

    def reopen(self) -> None:
        """Re-open after external log rotation.

        Raises:
            ValueError: If the underlying strategy is not NoneStrategy.
        """
        self._handler.reopen()

    def flush(self) -> None:
        self._handler.flush()

    def close(self) -> None:
        self._handler.close()

    @property
    def handler(self) -> AppendOnlyFileHandler:
        return self._handler


class ConsoleSink:
    """Writer-side console sink."""

    def __init__(self, handler: logging.Handler) -> None:
        self._handler = handler

    def emit(self, record: logging.LogRecord) -> None:
        self._handler.handle(record)

    def flush(self) -> None:
        self._handler.flush()

    def close(self) -> None:
        self._handler.close()

    @property
    def handler(self) -> logging.Handler:
        return self._handler


class SinkGroup:
    """Groups FileSink and ConsoleSink for a single route.

    Used by WriterRuntime to dispatch a LogRecord to all sinks
    associated with a named route ('root' or 'module:<name>').
    """

    def __init__(
        self,
        file_sink: FileSink | None = None,
        console_sink: ConsoleSink | None = None,
    ) -> None:
        self._file_sink = file_sink
        self._console_sink = console_sink

    def emit(self, record: logging.LogRecord) -> None:
        if self._file_sink is not None:
            self._file_sink.emit(record)
        if self._console_sink is not None:
            self._console_sink.emit(record)

    def reopen(self) -> None:
        """Reopen file sink after external log rotation.

        Raises:
            ValueError: If the file sink's strategy is not NoneStrategy.
        """
        if self._file_sink is not None:
            self._file_sink.reopen()

    def flush(self) -> None:
        if self._file_sink is not None:
            self._file_sink.flush()
        if self._console_sink is not None:
            self._console_sink.flush()

    def close(self) -> None:
        if self._file_sink is not None:
            self._file_sink.close()
        if self._console_sink is not None:
            self._console_sink.close()

    @property
    def file_sink(self) -> FileSink | None:
        return self._file_sink

    @property
    def console_sink(self) -> ConsoleSink | None:
        return self._console_sink
