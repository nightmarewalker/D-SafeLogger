# Color Console

**Module**: `dsafelogger._color`

ANSI color console handler for D-SafeLogger.

## Functions

### `_enable_windows_vt100() -> 'None'`

Enable ANSI escape sequences on Windows 10+.

## Classes

### `ColorStreamHandler(stream=None, color_enabled: 'bool' = True, color_overrides: 'dict[str, str] | None' = None) -> 'None'`

StreamHandler with ANSI color codes for log levels.

Uses _DisplayRecordProxy to apply colourised levelname without mutating
the original LogRecord, so ANSI codes never leak to other handlers
(e.g., file handlers) that share the same record.

A separate _proxy_tls (distinct from DSafeFormatter._proxy_tls) is used
so that when DSafeFormatter is the formatter on this handler the two
classes never share the same proxy instance.

v23h: classified as a *best-effort / diagnostic* sink
(`_ds_required = False`).  Failures are stderr-warned (rate-limited)
but do not contribute to `_writer_sink_reject`, `_writer_policy_reject`,
`_writer_partial_delivered`, or `_reject_counter`. See §12.3.

Public methods:

- `emit(self, record: 'logging.LogRecord') -> 'None'`
