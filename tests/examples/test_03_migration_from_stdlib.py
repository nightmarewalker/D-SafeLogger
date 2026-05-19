"""Runnable scenario for examples/03_migration_from_stdlib.md."""

from __future__ import annotations

import logging

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def test_migration_from_stdlib_keeps_existing_call_sites(tmp_path, clean_env):
    log_dir = tmp_path / "logs"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="MyApp",
        console_out=False,
        fmt="%(levelname)s:%(name)s:%(message)s",
    )

    legacy_logger = logging.getLogger("legacy.module")
    new_logger = GetLogger("mymodule.new")

    legacy_logger.info("legacy call site still works")
    with new_logger.contextualize(request_id="abc-123"):
        new_logger.info("new code gains contextualize")
    _shutdown()

    output = (log_dir / "MyApp.log").read_text(encoding="utf-8")
    assert "INF:legacy.module:legacy call site still works" in output
    assert "INF:mymodule.new:new code gains contextualize" in output
    assert "request_id:abc-123" in output
