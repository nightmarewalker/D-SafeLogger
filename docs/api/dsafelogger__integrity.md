# Integrity Verification

**Module**: `dsafelogger._integrity`

File integrity verification for D-SafeLogger.

## Functions

### `_get_manifest_lock(path: 'Path') -> 'threading.Lock'`

Return shared lock for a given manifest path.

### `append_manifest(file_path: 'Path', manifest_path: 'Path') -> 'None'`

Append hash entry to manifest file.

Creates manifest directory if needed. Thread-safe via per-path lock.

### `compute_sha256(file_path: 'Path') -> 'str'`

Compute SHA-256 hash of a file using 64KB chunks.

### `write_sidecar(file_path: 'Path') -> 'None'`

Generate .sha256 sidecar file (sha256sum -c compatible).

Uses temp file + os.replace() for atomic write.

## Classes

### `HashWorker(file_path: 'Path', manifest_path: 'Path | None' = None, register_fn: 'object' = None, unregister_fn: 'object' = None) -> 'None'`

Fire-and-forget hash generation worker thread.

Used when enable_hash=True and backup_count=0 (no purge/archive worker).
When backup_count > 0, hashing is done within PurgeWorker/ArchiveWorker.

Public methods:

- `run(self) -> 'None'`

## Constants

| Name | Type | Value |
|---|---|---|
| `SHA256_CHUNK_SIZE` | `int` | `65536` |
