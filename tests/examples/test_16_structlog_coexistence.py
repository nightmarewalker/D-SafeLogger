"""Runnable scenario for examples/16_structlog_coexistence.md."""

from __future__ import annotations

import json
import logging
import re

import pytest

from dsafelogger import ConfigureLogger, _shutdown

pytestmark = pytest.mark.optional_integration


def test_structlog_frontend_dsafelogger_json_backend(tmp_path, clean_env):
    structlog = pytest.importorskip("structlog")
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="MyApp",
        routing_mode="daily",
        console_out=False,
        structured=True,
        is_async=True,
    )

    try:
        structlog.configure(
            processors=[
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.stdlib.render_to_log_kwargs,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        log = structlog.get_logger("chk_api").bind(session_id="xy-123", tenant="acme")
        log.info("checkout_completed", status="success")
        _shutdown()
    finally:
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()

    log_files = sorted(tmp_path.glob("MyApp_*.log"))
    assert len(log_files) == 1
    assert re.fullmatch(r"MyApp_\d{8}\.log", log_files[0].name)
    record = json.loads(log_files[0].read_text(encoding="utf-8").strip())
    assert record["logger"] == "chk_api"
    assert record["message"] == "checkout_completed"
    assert record["session_id"] == "xy-123"
    assert record["tenant"] == "acme"
    assert record["status"] == "success"
