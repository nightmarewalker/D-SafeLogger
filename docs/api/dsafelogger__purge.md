# Purge / Archive Workers

**Module**: `dsafelogger._purge`

Purge and archive workers for D-SafeLogger.

## Functions

### `_get_family_lock(directory: 'Path', pg_name: 'str') -> 'threading.Lock'`

Return shared lock for a given (directory, pg_name) family.

### `_list_log_files(directory: 'Path', pg_name: 'str') -> 'list[Path]'`

List log files matching pattern, sorted oldest first.

## Classes

### `ArchiveWorker(directory: 'Path', pg_name: 'str', backup_count: 'int', switched_file: 'Path | None' = None, enable_hash: 'bool' = False, manifest_path: 'str | None' = None, unregister_fn: 'object' = None) -> 'None'`

Archive old log files to ZIP beyond backup_count.

If enable_hash is True, generates hash for the switched file
and includes .sha256 sidecar in the ZIP.

Public methods:

- `run(self) -> 'None'`

### `PurgeWorker(directory: 'Path', pg_name: 'str', backup_count: 'int', switched_file: 'Path | None' = None, enable_hash: 'bool' = False, manifest_path: 'str | None' = None, unregister_fn: 'object' = None) -> 'None'`

Delete old log files beyond backup_count.

If enable_hash is True, generates hash for the switched file
before purging.

Public methods:

- `run(self) -> 'None'`

## Constants

| Name | Type | Value |
|---|---|---|
| `MIN_FREE_SPACE_BYTES` | `int` | `10485760` |
