"""Tests for dsafelogger._purge (PurgeWorker and ArchiveWorker)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from dsafelogger._purge import ArchiveWorker, PurgeWorker


def _create_log_files(directory: Path, pg_name: str, count: int) -> list[Path]:
    """Create numbered log files for testing."""
    import time
    files = []
    for i in range(count):
        f = directory / f'{pg_name}_{i:03d}.log'
        f.write_bytes(f'content {i}\n'.encode('utf-8'))
        time.sleep(0.01)  # Ensure different mtime
        files.append(f)
    return files


class TestPurgeWorker:
    """UT-PW: PurgeWorker tests."""

    def test_purge_old_files(self, tmp_path):
        _create_log_files(tmp_path, 'App', 5)
        worker = PurgeWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=5)

        remaining = list(tmp_path.glob('App_*.log'))
        assert len(remaining) == 3

    def test_no_purge_when_under_limit(self, tmp_path):
        _create_log_files(tmp_path, 'App', 2)
        worker = PurgeWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=5)

        remaining = list(tmp_path.glob('App_*.log'))
        assert len(remaining) == 2

    def test_no_files_to_purge(self, tmp_path):
        worker = PurgeWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=5)
        # Should not raise

    def test_daemon_thread(self, tmp_path):
        worker = PurgeWorker(tmp_path, 'App', backup_count=3)
        assert worker.daemon is True

    def test_sidecar_cleanup(self, tmp_path):
        """Test that .sha256 sidecars are deleted along with log files."""
        files = _create_log_files(tmp_path, 'App', 5)
        for f in files:
            sidecar = f.with_suffix('.log.sha256')
            sidecar.write_text('hash  file\n', encoding='utf-8')

        worker = PurgeWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=5)

        remaining_logs = list(tmp_path.glob('App_*.log'))
        remaining_sha = list(tmp_path.glob('App_*.log.sha256'))
        assert len(remaining_logs) == 3
        assert len(remaining_sha) <= 3

    def test_sidecar_missing_ok(self, tmp_path):
        """No error if .sha256 doesn't exist."""
        _create_log_files(tmp_path, 'App', 5)
        worker = PurgeWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=5)
        # No error expected


class TestArchiveWorker:
    """UT-AW: ArchiveWorker tests."""

    def test_archive_old_files(self, tmp_path):
        _create_log_files(tmp_path, 'App', 5)
        worker = ArchiveWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=10)

        remaining_logs = list(tmp_path.glob('App_*.log'))
        zip_files = list(tmp_path.glob('App_*.log.zip'))
        assert len(remaining_logs) == 3
        assert len(zip_files) == 2

    def test_zip_content_matches(self, tmp_path):
        files = _create_log_files(tmp_path, 'App', 4)
        original_content = files[0].read_bytes()

        worker = ArchiveWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=10)

        zip_files = list(tmp_path.glob('App_*.log.zip'))
        assert len(zip_files) == 1

        with zipfile.ZipFile(zip_files[0], 'r') as zf:
            names = zf.namelist()
            assert any(name.endswith('.log') for name in names)
            for name in names:
                if name.endswith('.log'):
                    content = zf.read(name)
                    assert content == original_content

    def test_no_archive_when_under_limit(self, tmp_path):
        _create_log_files(tmp_path, 'App', 2)
        worker = ArchiveWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=5)

        zip_files = list(tmp_path.glob('App_*.log.zip'))
        assert len(zip_files) == 0

    def test_daemon_thread(self, tmp_path):
        worker = ArchiveWorker(tmp_path, 'App', backup_count=3)
        assert worker.daemon is True

    def test_no_files(self, tmp_path):
        worker = ArchiveWorker(tmp_path, 'App', backup_count=3)
        worker.start()
        worker.join(timeout=5)
        # Should not raise
