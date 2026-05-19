"""Runnable scenario for examples/09_debugging_production.md."""

from __future__ import annotations

import os

from dsafelogger import ConfigureLogger, GetLogger, _shutdown, register_level


def _process_order() -> None:
    api_key = "sk_live_should_be_masked"
    credit_card = "4111-1111-1111-1111"
    ssn = "123-45-6789"
    amount = 15000.0
    if amount > 10000:
        raise ValueError(f"Amount exceeds daily limit: {amount}")
    assert api_key and credit_card and ssn


def test_debugging_production_masks_diagnostic_locals_and_custom_level(tmp_path, clean_env):
    os.environ["D_LOG_DIAGNOSE"] = "1"
    os.environ["D_LOG_LEVEL"] = "TRACE"
    log_dir = tmp_path / "logs"

    register_level("TRACE", 5, "TRC", "\033[90m")
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="DebugDemo",
        console_out=False,
        default_level="INFO",
        sens_kws=["credit_card", "ssn"],
    )

    logger = GetLogger("demo")
    logger.trace("process_order called: user=alice, amount=15000.0")
    try:
        _process_order()
    except ValueError:
        logger.exception("Order processing failed")
    logger.info("Demo complete")
    _shutdown()

    output = (log_dir / "DebugDemo.log").read_text(encoding="utf-8")
    assert "[TRC]" in output
    assert "process_order called" in output
    assert "Order processing failed" in output
    assert "api_key = *** MASKED ***" in output
    assert "credit_card = *** MASKED ***" in output
    assert "ssn = *** MASKED ***" in output
    assert "sk_live_should_be_masked" not in output
    assert "4111-1111-1111-1111" not in output
    assert "123-45-6789" not in output
