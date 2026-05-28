"""Runnable scenario for examples/09_debugging_production.md."""

from __future__ import annotations

import os

from dsafelogger import ConfigureLogger, GetLogger, _shutdown, RegisterLevel


def _process_order() -> None:
    api_key = "sk_live_should_be_masked"
    credit_card = "4111-1111-1111-1111"
    ssn = "123-45-6789"
    amount = 15000.0
    if amount > 10000:
        raise ValueError(f"Amount exceeds daily limit: {amount}")
    assert api_key and credit_card and ssn


def _checkout() -> None:
    api_key = "sk_live_should_be_masked"
    credit_card = "4111-1111-1111-1111"
    ssn = "123-45-6789"
    amount = 15000.0
    if amount > 10000:
        raise ValueError(f"Checkout amount exceeds limit: {amount}")
    assert api_key and credit_card and ssn


def test_debugging_production_masks_diagnostic_locals_and_custom_level(tmp_path, clean_env):
    os.environ["D_LOG_DIAGNOSE"] = "1"
    os.environ["D_LOG_LEVEL"] = "TRACE"
    log_dir = tmp_path / "logs"

    RegisterLevel("TRACE", 5, "TRC", "\033[90m")
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


def test_debugging_production_redirects_suspect_module_to_incident_file_with_diagnostics(
    tmp_path, monkeypatch, clean_env
):
    log_dir = tmp_path / "logs"
    incident_path = tmp_path / "incidents" / "checkout_trace.log"

    RegisterLevel("TRACE", 5, "TRC", "\033[90m")
    monkeypatch.setenv("D_LOG_MODULES", f"myapp.checkout:TRACE:{incident_path}")
    monkeypatch.setenv("D_LOG_DIAGNOSE", "1")

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="OrderService",
        console_out=False,
        default_level="INFO",
        sens_kws=["credit_card", "ssn"],
    )

    checkout_logger = GetLogger("myapp.checkout")
    other_logger = GetLogger("myapp.other")

    checkout_logger.trace("checkout step trace evidence")
    try:
        _checkout()
    except ValueError:
        checkout_logger.exception("Checkout failed")

    # Unrelated module stays at the global INFO default.
    other_logger.debug("unrelated debug should not be collected")
    _shutdown()

    assert incident_path.exists()
    incident_log = incident_path.read_text(encoding="utf-8")
    main_log = (log_dir / "OrderService.log").read_text(encoding="utf-8")

    # Global stays at INFO while the suspect module is redirected at TRACE.
    assert "[TRC]" in incident_log
    assert "checkout step trace evidence" in incident_log
    assert "Checkout failed" in incident_log

    # Diagnostic local-variable snapshot is collected, with masking applied.
    assert "api_key = *** MASKED ***" in incident_log
    assert "credit_card = *** MASKED ***" in incident_log
    assert "ssn = *** MASKED ***" in incident_log
    assert "sk_live_should_be_masked" not in incident_log
    assert "4111-1111-1111-1111" not in incident_log
    assert "123-45-6789" not in incident_log

    # Unrelated logger output does not leak into the incident file or vice versa.
    assert "unrelated debug should not be collected" not in incident_log
    assert "checkout step trace evidence" not in main_log
