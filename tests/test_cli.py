"""Tests for dsafelogger._cli (CLI tool)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from dsafelogger._cli import cmd_init, cmd_ls, INI_TEMPLATE


class TestCmdInit:
    """CLI init subcommand tests."""

    def test_outputs_template(self, capsys):
        cmd_init()
        captured = capsys.readouterr()
        assert '[global]' in captured.out
        assert 'default_level' in captured.out
        assert 'routing_mode' in captured.out

    def test_template_contains_module_example(self, capsys):
        cmd_init()
        captured = capsys.readouterr()
        assert 'dsafelogger:' in captured.out

    def test_template_no_trailing_newline(self):
        # Template should not end with double newline
        assert not INI_TEMPLATE.endswith('\n\n')


class TestCmdLs:
    """CLI ls subcommand tests."""

    def test_no_log_files(self, tmp_path, capsys):
        cmd_ls(str(tmp_path))
        captured = capsys.readouterr()
        assert 'No log files found' in captured.out

    def test_list_log_files(self, tmp_path, capsys):
        (tmp_path / 'MyApp_20260403.log').write_text('test\n', encoding='utf-8')
        time.sleep(0.01)
        (tmp_path / 'MyApp_20260404.log').write_text('test2\n', encoding='utf-8')
        cmd_ls(str(tmp_path))
        captured = capsys.readouterr()
        assert 'MyApp' in captured.out

    def test_nonexistent_dir(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            cmd_ls(str(tmp_path / 'nonexistent'))


class TestCmdMain:
    """CLI main entry point tests."""

    def test_init_subcommand(self, capsys):
        from dsafelogger._cli import main
        with patch('sys.argv', ['dsafelogger', 'init']):
            main()
        captured = capsys.readouterr()
        assert '[global]' in captured.out

    def test_no_subcommand_error(self):
        from dsafelogger._cli import main
        with patch('sys.argv', ['dsafelogger']):
            with pytest.raises(SystemExit):
                main()
