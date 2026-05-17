"""OpenTelemetry LoggingInstrumentor coexistence tests."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.optional_integration

# opentelemetry-sdk uses C extensions (protobuf / internal tracing) that are
# not free-threaded safe.  Importing opentelemetry.sdk.trace segfaults on
# Python 3.13t / 3.14t (SIGSEGV in the C layer).  Skip the whole module on
# free-threaded builds until upstream adds FT support.
_is_free_threaded = not getattr(sys, '_is_gil_enabled', lambda: True)()
if _is_free_threaded:
    pytest.skip(
        'opentelemetry-sdk C extensions segfault on free-threaded Python '
        '(GIL disabled); skipping until upstream adds FT support.',
        allow_module_level=True,
    )

from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def _log_hook(span: Span, record: logging.LogRecord) -> None:
    """Attach extra attributes through OpenTelemetry's log hook."""
    record.checkout_stage = 'authorize'
    if span.is_recording():
        record.from_sampled_span = span.get_span_context().trace_flags.sampled


def _emit_with_otel(
    tmp_path: Path,
    *,
    structured: bool,
    is_async: bool = False,
) -> tuple[str, dict[str, str]]:
    """Emit one log line inside an active span and return the file contents."""
    tracer_provider = TracerProvider(
        resource=Resource.create({'service.name': 'checkout-api'}),
    )

    # Provide custom format string for text output to map otel trace fields natively
    fmt_str = "%(levelname)s | trace_id=%(otelTraceID)s | span_id=%(otelSpanID)s | service_name=%(otelServiceName)s | trace_sampled=%(otelTraceSampled)s | %(message)s"
    
    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name='OtelDemo',
        console_out=False,
        structured=structured,
        is_async=is_async,
        fmt=fmt_str if not structured else None,
    )

    instrumentor = LoggingInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        set_logging_format=True,
        enable_log_auto_instrumentation=False,
        log_hook=_log_hook,
    )

    try:
        tracer = tracer_provider.get_tracer(__name__)
        logger = GetLogger('otel.demo')

        with tracer.start_as_current_span('checkout-span') as span:
            logger.info('Processed payment')
            span_context = span.get_span_context()
            expected = {
                'trace_id': f'{span_context.trace_id:032x}',
                'span_id': f'{span_context.span_id:016x}',
            }

        _shutdown()
        log_path = next(tmp_path.glob('*.log'))
        return log_path.read_text(encoding='utf-8').strip(), expected
    finally:
        instrumentor.uninstrument()


class TestOpenTelemetryIntegration:
    """IT-OTEL: OpenTelemetry LoggingInstrumentor integration tests."""

    def test_text_formatter_emits_trace_and_span_ids(self, tmp_path, clean_env):
        output, expected = _emit_with_otel(tmp_path, structured=False)

        assert f"trace_id={expected['trace_id']}" in output
        assert f"span_id={expected['span_id']}" in output
        assert 'service_name=checkout-api' in output
        assert 'trace_sampled=True' in output

    def test_structured_formatter_maps_otel_fields(self, tmp_path, clean_env):
        output, expected = _emit_with_otel(tmp_path, structured=True)
        data = json.loads(output)

        assert data['otelTraceID'] == expected['trace_id']
        assert data['otelSpanID'] == expected['span_id']
        assert data['otelServiceName'] == 'checkout-api'
        assert data['otelTraceSampled'] is True
        assert data['checkout_stage'] == 'authorize'
        assert data['from_sampled_span'] is True

    def test_async_queue_handoff_preserves_otel_extensions(self, tmp_path, clean_env):
        output, expected = _emit_with_otel(
            tmp_path,
            structured=True,
            is_async=True,
        )
        data = json.loads(output)

        assert data['otelTraceID'] == expected['trace_id']
        assert data['otelSpanID'] == expected['span_id']
        assert data['checkout_stage'] == 'authorize'
        assert data['from_sampled_span'] is True
