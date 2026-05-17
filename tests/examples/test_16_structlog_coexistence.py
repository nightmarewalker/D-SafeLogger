"""Runnable scenario for examples/16_structlog_coexistence.md."""

from __future__ import annotations

import json
import logging

import pytest

from dsafelogger import ConfigureLogger, _shutdown

pytestmark = pytest.mark.optional_integration


def test_structlog_frontend_dsafelogger_json_backend(tmp_path, clean_env):
    structlog = pytest.importorskip("structlog")
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="StructlogApp",
        routing_mode="none",
        console_out=False,
        structured=True,
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
        log.info("login_success", method="oauth")
        _shutdown()
    finally:
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()

    record = json.loads((tmp_path / "StructlogApp.log").read_text(encoding="utf-8").strip())
    assert record["logger"] == "chk_api"
    assert record["message"] == "login_success"
    assert record["session_id"] == "xy-123"
    assert record["tenant"] == "acme"
    assert record["method"] == "oauth"
