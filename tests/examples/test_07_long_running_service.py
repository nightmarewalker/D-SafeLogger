"""Runnable scenario for examples/07_long_running_service.md."""

from __future__ import annotations

import re

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def test_long_running_service_uses_daily_retention_archive_config(tmp_path, clean_env):
    log_dir = tmp_path / "logs"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="DemoService",
        console_out=False,
        routing_mode="daily",
        backup_count=7,
        archive_mode=True,
        fmt="%(message)s",
    )

    logger = GetLogger("service")
    logger.info("DemoService starting up")
    logger.warning("Slow query detected: 2.3s")
    logger.info("DemoService shutting down")
    _shutdown()

    log_files = sorted(log_dir.glob("DemoService_*.log"))
    assert len(log_files) == 1
    assert re.fullmatch(r"DemoService_\d{8}\.log", log_files[0].name)
    assert not (log_dir / "DemoService.log.1").exists()
    output = log_files[0].read_text(encoding="utf-8")
    assert "DemoService starting up" in output
    assert "Slow query detected: 2.3s" in output
