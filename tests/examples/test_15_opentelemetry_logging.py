"""Runnable scenario for examples/15_opentelemetry_logging.md."""

from __future__ import annotations

import json
import logging
import sys

import pytest

from dsafelogger import ConfigureLogger, GetLogger, _shutdown

pytestmark = pytest.mark.optional_integration


def test_opentelemetry_logging_correlation_survives_async_handoff(tmp_path, clean_env):
    if not getattr(sys, "_is_gil_enabled", lambda: True)():
        pytest.skip("opentelemetry-sdk is not free-threaded safe in this test environment")

    otel_logging = pytest.importorskip("opentelemetry.instrumentation.logging")
    resources = pytest.importorskip("opentelemetry.sdk.resources")
    trace_sdk = pytest.importorskip("opentelemetry.sdk.trace")

    def log_hook(span, record: logging.LogRecord) -> None:
        record.checkout_stage = "authorize"
        if span and span.is_recording():
            record.from_sampled_span = span.get_span_context().trace_flags.sampled

    trace_provider = trace_sdk.TracerProvider(
        resource=resources.Resource.create({"service.name": "checkout-api"})
    )

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="CheckoutAPI",
        structured=True,
        is_async=True,
        console_out=False,
    )

    instrumentor = otel_logging.LoggingInstrumentor()
    instrumentor.instrument(
        tracer_provider=trace_provider,
        set_logging_format=True,
        enable_log_auto_instrumentation=False,
        log_hook=log_hook,
    )

    try:
        tracer = trace_provider.get_tracer(__name__)
        logger = GetLogger("checkout.api")
        with tracer.start_as_current_span("authorize-payment") as span:
            logger.info("Payment authorized", extra={"order_id": "ord-1042", "amount": 249.0})
            span_context = span.get_span_context()
            expected_trace_id = f"{span_context.trace_id:032x}"
            expected_span_id = f"{span_context.span_id:016x}"
        _shutdown()
    finally:
        instrumentor.uninstrument()

    record = json.loads((tmp_path / "CheckoutAPI.log").read_text(encoding="utf-8").strip())
    assert record["message"] == "Payment authorized"
    assert record["otelTraceID"] == expected_trace_id
    assert record["otelSpanID"] == expected_span_id
    assert record["otelServiceName"] == "checkout-api"
    assert record["checkout_stage"] == "authorize"
    assert record["from_sampled_span"] is True
    assert record["order_id"] == "ord-1042"
