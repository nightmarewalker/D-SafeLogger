"""Tests for dsafelogger._validator."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from unittest import mock

import pytest
from dsafelogger._validator import PathValidator


class TestPathValidator:

    def test_validate_writable_success(self, tmp_path):
        """Directory exists and is writable."""
        assert PathValidator.validate_writable(tmp_path) is None

    def test_validate_writable_creates_directory(self, tmp_path):
        """Directory does not exist, should be created."""
        target_dir = tmp_path / "new_logs"
        assert not target_dir.exists()
        
        PathValidator.validate_writable(target_dir)
        
        assert target_dir.exists()
        assert target_dir.is_dir()

    def test_validate_writable_permission_denied_mkdir(self, tmp_path):
        """PermissionError on mkdir."""
        target_dir = tmp_path / "readonly_dir" / "new_logs"
        
        # Patch Path.mkdir to raise PermissionError
        with mock.patch("pathlib.Path.mkdir", side_effect=PermissionError("Mocked Permission Denied")):
            with pytest.raises(PermissionError, match="permission denied"):
                PathValidator.validate_writable(target_dir)

    def test_validate_writable_os_error_mkdir(self, tmp_path):
        """OSError on mkdir."""
        target_dir = tmp_path / "os_error_dir"
        
        # Patch Path.mkdir to raise OSError
        with mock.patch("pathlib.Path.mkdir", side_effect=OSError("Disk Full")):
            with pytest.raises(OSError, match="Cannot create log directory"):
                PathValidator.validate_writable(target_dir)

    def test_validate_writable_permission_denied_write(self, tmp_path):
        """PermissionError when writing test file."""
        target_dir = tmp_path / "noperm"
        target_dir.mkdir()
        
        with mock.patch("pathlib.Path.write_text", side_effect=PermissionError("Mocked write err")):
            with pytest.raises(PermissionError, match="is not writable"):
                PathValidator.validate_writable(target_dir)

    def test_validate_writable_os_error_write(self, tmp_path):
        """OSError when writing test file."""
        target_dir = tmp_path / "osnoperm"
        target_dir.mkdir()
        
        with mock.patch("pathlib.Path.write_text", side_effect=OSError("I/O Err")):
            with pytest.raises(OSError, match="Cannot write to log directory"):
                PathValidator.validate_writable(target_dir)

    def test_cleanup_failure_ignored(self, tmp_path):
        """If unlink fails, it should be ignored."""
        target_dir = tmp_path / "cleanup"
        target_dir.mkdir()
        
        with mock.patch("pathlib.Path.unlink", side_effect=Exception("Cannot delete")):
            # Should not raise
            PathValidator.validate_writable(target_dir)
