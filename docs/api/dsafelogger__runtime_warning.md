# dsafelogger._runtime_warning

**Module**: `dsafelogger._runtime_warning`

Independent runtime warning JSONL writer for multiprocess observability.

## Functions

### `_fallback_path(path: 'str | os.PathLike[str]', pid: 'int | None' = None) -> 'Path'`

### `_now_iso() -> 'str'`

### `_stderr_fallback(message: 'str') -> 'None'`

### `make_runtime_warning_payload(*, component: 'str', event: 'str', level: 'str' = 'warning', classification: 'str | None' = None, reason: 'str | None' = None, counter_name: 'str | None' = None, counter_value: 'int | None' = None, context: 'dict[str, Any] | None' = None, pid: 'int | None' = None) -> 'dict[str, Any]'`

## Classes

### `RuntimeWarningSink(path: 'str | os.PathLike[str]') -> 'None'`

Append-only JSONL sink that never routes through application logging.

Public methods:

- `write(self, *, component: 'str', event: 'str', level: 'str' = 'warning', classification: 'str | None' = None, reason: 'str | None' = None, counter_name: 'str | None' = None, counter_value: 'int | None' = None, context: 'dict[str, Any] | None' = None, pid: 'int | None' = None) -> 'bool'`
- `write_payload(self, payload: 'dict[str, Any]') -> 'bool'`

## Constants

| Name | Type | Value |
|---|---|---|
| `RUNTIME_WARNING_SCHEMA_VERSION` | `int` | `1` |
