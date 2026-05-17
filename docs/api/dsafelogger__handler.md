# File Handler

**Module**: `dsafelogger._handler`

Append-only file handler for D-SafeLogger.

## Classes

### `AppendOnlyFileHandler(strategy: 'RoutingStrategy', backup_count: 'int' = 0, archive_mode: 'bool' = False, enable_hash: 'bool' = False, manifest_path: 'str | None' = None, encoding: 'str' = 'utf-8', stream_flush_on_emit: 'bool' = True) -> 'None'`

Append-only file handler with routing strategy support.

Avoids file renaming (Windows lock safety) by using stream switching.

v23h: classified as a *required* sink (`_ds_required = True`), meaning
file delivery must succeed for the record to count as `delivered`
(§12.3 配送契約).  Failures are reflected in `_writer_sink_reject` /
`_writer_policy_reject` and contribute to `_writer_partial_delivered`
when the route has multiple required sinks.

Public methods:

- `close(self) -> 'None'`
- `emit(self, record: 'logging.LogRecord') -> 'None'`
- `flush(self) -> 'None'`
- `reopen(self) -> 'None'`
