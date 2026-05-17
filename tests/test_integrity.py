"""Tests for dsafelogger._integrity (hash, sidecar, manifest)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from dsafelogger._integrity import (
    HashWorker,
    append_manifest,
    compute_sha256,
    write_sidecar,
)


class TestComputeSha256:
    def test_known_content(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'hello world\n')
        result = compute_sha256(f)
        expected = hashlib.sha256(b'hello world\n').hexdigest()
        assert result == expected

    def test_empty_file(self, tmp_path):
        f = tmp_path / 'empty.log'
        f.write_bytes(b'')
        result = compute_sha256(f)
        expected = hashlib.sha256(b'').hexdigest()
        assert result == expected

    def test_large_file(self, tmp_path):
        f = tmp_path / 'large.log'
        content = b'x' * (128 * 1024)  # 128KB (> chunk size)
        f.write_bytes(content)
        result = compute_sha256(f)
        expected = hashlib.sha256(content).hexdigest()
        assert result == expected


class TestWriteSidecar:
    def test_sidecar_created(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'content\n')
        write_sidecar(f)

        sidecar = f.with_suffix('.log.sha256')
        assert sidecar.exists()

    def test_sidecar_format(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'content\n')
        write_sidecar(f)

        sidecar = f.with_suffix('.log.sha256')
        content = sidecar.read_text(encoding='utf-8')
        # Format: hash  filename\n
        parts = content.strip().split('  ')
        assert len(parts) == 2
        assert len(parts[0]) == 64  # SHA-256 hex digest
        assert parts[1] == 'test.log'

    def test_sidecar_atomic_overwrite(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'first\n')
        write_sidecar(f)

        f.write_bytes(b'second\n')
        write_sidecar(f)

        sidecar = f.with_suffix('.log.sha256')
        content = sidecar.read_text(encoding='utf-8')
        expected_hash = hashlib.sha256(b'second\n').hexdigest()
        assert expected_hash in content


class TestAppendManifest:
    def test_manifest_created(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'content\n')
        manifest = tmp_path / 'manifest.txt'

        append_manifest(f, manifest)
        assert manifest.exists()

    def test_manifest_format(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'content\n')
        manifest = tmp_path / 'manifest.txt'

        append_manifest(f, manifest)
        content = manifest.read_text(encoding='utf-8')
        # Format: [timestamp] hash  filename\n
        assert content.startswith('[')
        assert 'test.log' in content
        assert ']' in content

    def test_manifest_append(self, tmp_path):
        f1 = tmp_path / 'a.log'
        f1.write_bytes(b'a\n')
        f2 = tmp_path / 'b.log'
        f2.write_bytes(b'b\n')
        manifest = tmp_path / 'manifest.txt'

        append_manifest(f1, manifest)
        append_manifest(f2, manifest)

        lines = manifest.read_text(encoding='utf-8').strip().split('\n')
        assert len(lines) == 2

    def test_manifest_auto_create_dir(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'content\n')
        manifest = tmp_path / 'sub' / 'dir' / 'manifest.txt'

        append_manifest(f, manifest)
        assert manifest.exists()


class TestHashWorker:
    def test_creates_sidecar(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'content\n')

        worker = HashWorker(f)
        worker.start()
        worker.join(timeout=5)

        assert f.with_suffix('.log.sha256').exists()

    def test_creates_manifest(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'content\n')
        manifest = tmp_path / 'manifest.txt'

        worker = HashWorker(f, manifest_path=manifest)
        worker.start()
        worker.join(timeout=5)

        assert manifest.exists()

    def test_daemon_thread(self, tmp_path):
        f = tmp_path / 'test.log'
        f.write_bytes(b'x')
        worker = HashWorker(f)
        assert worker.daemon is True

    def test_missing_file_no_crash(self, tmp_path):
        f = tmp_path / 'nonexistent.log'
        worker = HashWorker(f)
        worker.start()
        worker.join(timeout=5)
        # Should not raise (stderr warning only)
