# Sink Configuration

**Module**: `dsafelogger._sink`

Sink layer abstractions for D-SafeLogger.

FileSink, ConsoleSink, and SinkGroup are the Writer-side output abstractions
used by WriterRuntime in the multiprocess namespace (dsafelogger.mp).

Single-process mode continues to use AppendOnlyFileHandler via Transport;
these classes provide the parallel abstraction for the Writer/runtime side.

## Classes

### `ConsoleSink(handler: 'logging.Handler') -> 'None'`

Writer-side console sink.

Public methods:

- `close(self) -> 'None'`
- `emit(self, record: 'logging.LogRecord') -> 'None'`
- `flush(self) -> 'None'`

### `FileSink(handler: 'AppendOnlyFileHandler') -> 'None'`

Writer-side file sink.

Wraps AppendOnlyFileHandler and owns the file lifecycle
(open/switch/reopen/maintenance) on behalf of WriterRuntime.

Public methods:

- `close(self) -> 'None'`
- `emit(self, record: 'logging.LogRecord') -> 'None'`
- `flush(self) -> 'None'`
- `reopen(self) -> 'None'`

### `SinkGroup(file_sink: 'FileSink | None' = None, console_sink: 'ConsoleSink | None' = None) -> 'None'`

Groups FileSink and ConsoleSink for a single route.

Used by WriterRuntime to dispatch a LogRecord to all sinks
associated with a named route ('root' or 'module:<name>').

Public methods:

- `close(self) -> 'None'`
- `emit(self, record: 'logging.LogRecord') -> 'None'`
- `flush(self) -> 'None'`
- `reopen(self) -> 'None'`
