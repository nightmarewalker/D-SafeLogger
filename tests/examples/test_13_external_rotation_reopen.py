"""Runnable scenario for examples/13_external_rotation_reopen.md."""

from __future__ import annotations

from dsafelogger import ConfigureLogger, GetLogger, ReopenLogFiles, _shutdown


def test_external_rotation_reopen_requires_none_routing_and_keeps_logging(tmp_path, clean_env):
    log_dir = tmp_path / "logs"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="myapp",
        routing_mode="none",
        console_out=False,
        fmt="%(message)s",
    )

    logger = GetLogger("myapp")
    logger.info("service started")
    ReopenLogFiles()
    logger.info("log files reopened after external rotation")
    _shutdown()

    output = (log_dir / "myapp.log").read_text(encoding="utf-8")
    assert "service started" in output
    assert "log files reopened after external rotation" in output
