"""Purge and archive workers for D-SafeLogger."""

from __future__ import annotations

import os
import shutil
import sys
import threading
import zipfile
from pathlib import Path

from dsafelogger._constants import MIN_FREE_SPACE_BYTES
from dsafelogger._integrity import append_manifest, write_sidecar


# ── Family lock management (per directory + pg_name) ──
_family_lock_guard = threading.Lock()
_family_locks: dict[tuple[Path, str], threading.Lock] = {}


def _get_family_lock(directory: Path, pg_name: str) -> threading.Lock:
    """Return shared lock for a given (directory, pg_name) family."""
    key = (directory.resolve(), pg_name)
    with _family_lock_guard:
        lock = _family_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _family_locks[key] = lock
        return lock


def _list_log_files(directory: Path, pg_name: str) -> list[Path]:
    """List log files matching pattern, sorted oldest first."""
    files = sorted(
        directory.glob(f'{pg_name}_*.log'),
        key=lambda p: p.stat().st_mtime,
    )
    return files


class PurgeWorker(threading.Thread):
    """Delete old log files beyond backup_count.

    If enable_hash is True, generates hash for the switched file
    before purging.
    """

    def __init__(
        self,
        directory: Path,
        pg_name: str,
        backup_count: int,
        switched_file: Path | None = None,
        enable_hash: bool = False,
        manifest_path: str | None = None,
        unregister_fn: object = None,
    ) -> None:
        super().__init__(daemon=True, name=f'PurgeWorker-{pg_name}')
        self._directory = directory
        self._pg_name = pg_name
        self._backup_count = backup_count
        self._switched_file = switched_file
        self._enable_hash = enable_hash
        self._manifest_path = manifest_path
        self._unregister_fn = unregister_fn

    def run(self) -> None:
        try:
            family_lock = _get_family_lock(self._directory, self._pg_name)
            with family_lock:
                # Hash generation before purge (if enabled)
                if self._enable_hash and self._switched_file and self._switched_file.exists():
                    try:
                        write_sidecar(self._switched_file)
                        if self._manifest_path:
                            append_manifest(self._switched_file, Path(self._manifest_path))
                    except OSError as e:
                        print(
                            f'[D-SafeLogger] Hash generation failed for '
                            f'{self._switched_file.name}: {e}',
                            file=sys.stderr,
                        )

                # Purge old files
                files = _list_log_files(self._directory, self._pg_name)
                if len(files) <= self._backup_count:
                    return

                to_delete = files[:len(files) - self._backup_count]
                for f in to_delete:
                    try:
                        f.unlink()
                        # Also delete sidecar if exists
                        sidecar = f.with_suffix(f.suffix + '.sha256')
                        if sidecar.exists():
                            sidecar.unlink()
                    except OSError as e:
                        print(
                            f'[D-SafeLogger] Failed to delete {f.name}: {e}',
                            file=sys.stderr,
                        )

        except Exception as e:
            print(
                f'[D-SafeLogger] PurgeWorker error: {e}',
                file=sys.stderr,
            )
        finally:
            if self._unregister_fn and callable(self._unregister_fn):
                self._unregister_fn(self)


class ArchiveWorker(threading.Thread):
    """Archive old log files to ZIP beyond backup_count.

    If enable_hash is True, generates hash for the switched file
    and includes .sha256 sidecar in the ZIP.
    """

    def __init__(
        self,
        directory: Path,
        pg_name: str,
        backup_count: int,
        switched_file: Path | None = None,
        enable_hash: bool = False,
        manifest_path: str | None = None,
        unregister_fn: object = None,
    ) -> None:
        super().__init__(daemon=True, name=f'ArchiveWorker-{pg_name}')
        self._directory = directory
        self._pg_name = pg_name
        self._backup_count = backup_count
        self._switched_file = switched_file
        self._enable_hash = enable_hash
        self._manifest_path = manifest_path
        self._unregister_fn = unregister_fn

    def run(self) -> None:
        try:
            family_lock = _get_family_lock(self._directory, self._pg_name)
            with family_lock:
                # Hash generation before archive (if enabled)
                if self._enable_hash and self._switched_file and self._switched_file.exists():
                    try:
                        write_sidecar(self._switched_file)
                        if self._manifest_path:
                            append_manifest(self._switched_file, Path(self._manifest_path))
                    except OSError as e:
                        print(
                            f'[D-SafeLogger] Hash generation failed for '
                            f'{self._switched_file.name}: {e}',
                            file=sys.stderr,
                        )

                # Archive old files
                files = _list_log_files(self._directory, self._pg_name)
                if len(files) <= self._backup_count:
                    return

                to_archive = files[:len(files) - self._backup_count]

                # Check free space
                try:
                    usage = shutil.disk_usage(self._directory)
                    if usage.free < MIN_FREE_SPACE_BYTES:
                        print(
                            f'[D-SafeLogger] Insufficient disk space for archiving. '
                            f'Free: {usage.free:,} bytes, required: {MIN_FREE_SPACE_BYTES:,} bytes.',
                            file=sys.stderr,
                        )
                        return
                except OSError:
                    pass  # Continue even if we can't check

                for f in to_archive:
                    try:
                        zip_path = f.with_suffix('.log.zip')
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                            zf.write(f, f.name)
                            # Include sidecar if exists
                            sidecar = f.with_suffix(f.suffix + '.sha256')
                            if sidecar.exists():
                                zf.write(sidecar, sidecar.name)
                                sidecar.unlink()
                        f.unlink()
                    except OSError as e:
                        print(
                            f'[D-SafeLogger] Failed to archive {f.name}: {e}',
                            file=sys.stderr,
                        )

        except Exception as e:
            print(
                f'[D-SafeLogger] ArchiveWorker error: {e}',
                file=sys.stderr,
            )
        finally:
            if self._unregister_fn and callable(self._unregister_fn):
                self._unregister_fn(self)
