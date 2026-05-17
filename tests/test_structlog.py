"""Tests for structlog coexistence with D-SafeLogger."""

import json
import logging
from pathlib import Path

import pytest
import structlog
from dsafelogger import ConfigureLogger, GetLogger

pytestmark = pytest.mark.optional_integration

@pytest.fixture(autouse=True)
def _reset_structlog_and_dsafelogger() -> None:
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()
    yield
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def test_pattern_a_dual_output(tmp_path: Path) -> None:
    """Test Pattern A: structlog handles JSON, D-SafeLogger handles text stream."""
    machine_log_file = tmp_path / "machine.jsonl"
    human_log_file = tmp_path / "App.log"

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="App",
        routing_mode="none",
        console_out=False,
    )
    human_logger = GetLogger("human.app")

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.WriteLoggerFactory(
            file=machine_log_file.open("a", encoding="utf-8")
        ),
    )
    machine_logger = structlog.get_logger("machine.app")

    human_logger.info("Order processed", extra={"order_id": 1042, "user_id": "alice"})
    machine_logger.bind(order_id=1042, user_id="alice").info("order_processed", status="success")

    with machine_log_file.open("r", encoding="utf-8") as f:
        machine_content = f.read()
    data = json.loads(machine_content.strip())
    assert data["order_id"] == 1042
    assert data["user_id"] == "alice"
    assert data["status"] == "success"

    with human_log_file.open("r", encoding="utf-8") as f:
        human_content = f.read()
    assert "[INF]" in human_content
    assert "Order processed" in human_content


def test_pattern_b_1_text_wrapping(tmp_path: Path) -> None:
    """Test Pattern B-1: structlog provides context, D-SafeLogger prints as text."""
    app_log_file = tmp_path / "App.log"
    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="App",
        routing_mode="none",
        console_out=False,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.KeyValueRenderer(
                key_order=["event"], drop_missing=True
            ),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    log = structlog.get_logger("chk.api")
    log = log.bind(order_id=2000, user_id="bob")
    log.info("payment_authorized", amount=5000, currency="USD")

    with app_log_file.open("r", encoding="utf-8") as f:
        output = f.read()
    assert "[INF]" in output
    assert "event='payment_authorized'" in output
    assert "amount=5000" in output
    assert "order_id=2000" in output
    assert "currency='USD'" in output


def test_pattern_b_2_json_integration(tmp_path: Path) -> None:
    """Test Pattern B-2: structlog passes kwargs, D-SafeLogger JSON formatter extracts effortlessly."""
    app_log_file = tmp_path / "App.log"
    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="App",
        routing_mode="none",
        console_out=False,
        structured=True,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.render_to_log_kwargs,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    log = structlog.get_logger("json.api")
    log = log.bind(session_id="xy-123", tenant="acme")
    log.info("login_success", method="oauth")

    with app_log_file.open("r", encoding="utf-8") as f:
        output = f.read()
    data = json.loads(output.strip())

    assert data["level"] == "INF"
    assert data["logger"] == "json.api"
    assert data["message"] == "login_success"
    assert data["session_id"] == "xy-123"
    assert data["tenant"] == "acme"
    assert data["method"] == "oauth"
