"""Runnable scenario for examples/07_long_running_service.md."""

from __future__ import annotations

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def test_long_running_service_uses_append_only_size_routing(tmp_path, clean_env):
    log_dir = tmp_path / "logs"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="LongRun",
        console_out=False,
        routing_mode="size",
        max_bytes=180,
        suffix_digits=3,
        fmt="%(message)s",
    )

    logger = GetLogger("service")
    for idx in range(12):
        logger.info("service event %02d with enough payload to switch files", idx)
    _shutdown()

    log_files = sorted(log_dir.glob("LongRun_*.log"))
    assert len(log_files) >= 2
    assert not (log_dir / "LongRun.log.1").exists()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in log_files)
    assert "service event 00" in combined
    assert "service event 11" in combined
