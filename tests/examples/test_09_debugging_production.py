"""Runnable scenario for examples/09_debugging_production.md."""

from __future__ import annotations

import os

from dsafelogger import ConfigureLogger, GetLogger, _shutdown, register_level


def _process_payment() -> None:
    api_key = "sk_live_should_be_masked"
    token = "tok_live_should_be_masked"
    amount = 15000.0
    if amount > 10000:
        raise ValueError(f"Amount exceeds daily limit: {amount}")
    assert api_key and token


def test_debugging_production_masks_diagnostic_locals_and_custom_level(tmp_path, clean_env):
    os.environ["D_LOG_DIAGNOSE"] = "1"
    log_dir = tmp_path / "logs"

    register_level("AUDIT", 35, "AUD")
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="Debug",
        console_out=False,
        default_level="INFO",
    )

    logger = GetLogger("app")
    try:
        _process_payment()
    except ValueError:
        logger.exception("Payment failed")
    logger.audit("User exported PII data")
    _shutdown()

    output = (log_dir / "Debug.log").read_text(encoding="utf-8")
    assert "Payment failed" in output
    assert "api_key = *** MASKED ***" in output
    assert "token = *** MASKED ***" in output
    assert "sk_live_should_be_masked" not in output
    assert "tok_live_should_be_masked" not in output
    assert "[AUD]" in output
    assert "User exported PII data" in output
