"""Runnable scenario for examples/14_cli_operations.md."""

from __future__ import annotations

from dsafelogger import ConfigureLogger, GetLogger, _shutdown
from dsafelogger._cli import cmd_init, cmd_ls


def test_cli_operations_init_and_ls(tmp_path, capsys, clean_env):
    cmd_init()
    init_output = capsys.readouterr().out
    assert "[global]" in init_output
    assert "pg_name" in init_output

    log_dir = tmp_path / "logs"
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="CLIDemo",
        routing_mode="daily",
        console_out=False,
        fmt="%(message)s",
    )
    logger = GetLogger("cli.demo")
    logger.info("Processing request 1")
    logger.info("All requests processed")
    _shutdown()

    cmd_ls(str(log_dir))
    ls_output = capsys.readouterr().out
    assert "CLIDemo" in ls_output
    assert ".log" in ls_output
