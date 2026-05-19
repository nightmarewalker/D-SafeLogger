"""Runnable scenario for examples/14_cli_operations.md."""

from __future__ import annotations

from dsafelogger import ConfigureLogger, GetLogger, _shutdown
from dsafelogger._cli import cmd_init, cmd_ls, cmd_tail


def test_cli_operations_init_ls_and_tail(tmp_path, capsys, clean_env, monkeypatch):
    cmd_init()
    init_output = capsys.readouterr().out
    assert "[global]" in init_output
    assert "pg_name" in init_output

    log_dir = tmp_path / "logs"
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="CLIDemo",
        routing_mode="daily",
        enable_hash=True,
        console_out=False,
        fmt="%(message)s",
    )
    logger = GetLogger("cli.demo")
    for idx in range(3):
        logger.info(f"Processing request {idx}")
    logger.info("All requests processed")
    _shutdown()

    cmd_ls(str(log_dir))
    ls_output = capsys.readouterr().out
    assert "CLIDemo" in ls_output
    assert ".log" in ls_output

    def stop_after_initial_read(_poll_interval: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("dsafelogger._cli.time.sleep", stop_after_initial_read)
    cmd_tail(str(log_dir), "CLIDemo", initial_lines=20, poll_interval=0.1)
    tail_output = capsys.readouterr().out
    assert "Processing request 0" in tail_output
    assert "All requests processed" in tail_output
