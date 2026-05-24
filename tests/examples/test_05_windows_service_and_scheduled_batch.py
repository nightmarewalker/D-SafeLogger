"""Runnable scenario for examples/05_windows_service_and_scheduled_batch.md."""

from __future__ import annotations

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown


def _run_service_iteration(logger, item: int) -> None:
    logger.info("service heartbeat", extra={"item": item})


def _run_scheduled_batch(logger) -> None:
    for item in range(8):
        logger.info("processed scheduled item", extra={"item": item})


def test_windows_service_and_scheduled_batch(tmp_path, clean_env):
    log_dir = tmp_path / "windows-job"
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="WinBatch",
        console_out=False,
        routing_mode="size",
        max_bytes=160,
        suffix_digits=2,
    )

    logger = GetLogger("windows.job")
    for item in range(4):
        _run_service_iteration(logger, item)
    _run_scheduled_batch(logger)
    SafeShutdown()

    routed_files = sorted(p.name for p in log_dir.glob("WinBatch_*.log"))
    assert len(routed_files) >= 2
    assert "WinBatch.log" not in routed_files
    assert any("processed scheduled item" in p.read_text(encoding="utf-8") for p in log_dir.glob("*.log"))
