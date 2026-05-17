"""File integrity verification for D-SafeLogger."""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from dsafelogger._constants import SHA256_CHUNK_SIZE


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file using 64KB chunks."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(SHA256_CHUNK_SIZE)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def write_sidecar(file_path: Path) -> None:
    """Generate .sha256 sidecar file (sha256sum -c compatible).

    Uses temp file + os.replace() for atomic write.
    """
    hash_value = compute_sha256(file_path)
    sidecar_path = file_path.with_suffix(file_path.suffix + '.sha256')
    temp_path = sidecar_path.with_suffix(sidecar_path.suffix + '.tmp')
    temp_path.write_text(
        f'{hash_value}  {file_path.name}\n',
        encoding='utf-8',
    )
    os.replace(temp_path, sidecar_path)


def append_manifest(file_path: Path, manifest_path: Path) -> None:
    """Append hash entry to manifest file.

    Creates manifest directory if needed. Thread-safe via per-path lock.
    """
    hash_value = compute_sha256(file_path)
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}'
    entry = f'[{timestamp}] {hash_value}  {file_path.name}\n'

    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    lock = _get_manifest_lock(manifest_path.resolve())
    with lock:
        with open(manifest_path, 'a', encoding='utf-8') as f:
            f.write(entry)


# ── Manifest lock management ──
_manifest_lock_guard = threading.Lock()
_manifest_locks: dict[Path, threading.Lock] = {}


def _get_manifest_lock(path: Path) -> threading.Lock:
    """Return shared lock for a given manifest path."""
    with _manifest_lock_guard:
        lock = _manifest_locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _manifest_locks[path] = lock
        return lock


class HashWorker(threading.Thread):
    """Fire-and-forget hash generation worker thread.

    Used when enable_hash=True and backup_count=0 (no purge/archive worker).
    When backup_count > 0, hashing is done within PurgeWorker/ArchiveWorker.
    """

    def __init__(
        self,
        file_path: Path,
        manifest_path: Path | None = None,
        register_fn: object = None,
        unregister_fn: object = None,
    ) -> None:
        super().__init__(daemon=True, name=f'HashWorker-{file_path.name}')
        self._file_path = file_path
        self._manifest_path = manifest_path
        self._unregister_fn = unregister_fn

    def run(self) -> None:
        try:
            write_sidecar(self._file_path)
            if self._manifest_path is not None:
                append_manifest(self._file_path, Path(self._manifest_path))
        except OSError as e:
            print(
                f'[D-SafeLogger] Hash generation failed for '
                f'{self._file_path.name}: {e}',
                file=sys.stderr,
            )
        finally:
            if self._unregister_fn and callable(self._unregister_fn):
                self._unregister_fn(self)
