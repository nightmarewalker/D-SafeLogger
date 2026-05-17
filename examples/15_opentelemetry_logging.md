# OpenTelemetry Logging Correlation

If your service already uses OpenTelemetry tracing, you do **not** need a custom
logging adapter to get trace correlation into D-SafeLogger.

Because D-SafeLogger stays compatible with stdlib `logging`, OpenTelemetry's
`LoggingInstrumentor` can keep injecting trace context into `LogRecord` objects,
and D-SafeLogger will carry those attributes into both:

- **text logs** through a formatter that references `otelTraceID`, `otelSpanID`, and related attributes
- **structured JSON** as top-level fields like `otelTraceID`, `otelSpanID`, and `otelServiceName`

This example shows the common production pattern:

1. OpenTelemetry traces are exported to your tracing backend.
2. D-SafeLogger writes append-only local files for audit and incident response.
3. Both are correlated by the same OpenTelemetry trace ID.

## The Scenario

You run a **checkout API** and already export traces with OpenTelemetry.
What you want from logging is:

- human-readable local files for fast incident triage
- structured JSON for log pipelines
- the same trace ID / span ID that appears in Jaeger, Tempo, or Datadog
- async logging so request threads do not block on file I/O

## Packages

```bash
pip install d-safelogger \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-instrumentation-logging
```

> If you already have an OTLP exporter configured, keep using it.
> This example uses a console span exporter only to stay self-contained.

## The Application Code

```python
"""otel_checkout_demo.py — D-SafeLogger + OpenTelemetry trace correlation."""

from dsafelogger import ConfigureLogger, GetLogger
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


def log_hook(span, record):
    """Attach business context while the span is still active."""
    record.checkout_stage = 'authorize'
    if span and span.is_recording():
        record.from_sampled_span = span.get_span_context().trace_flags.sampled


trace_provider = TracerProvider(
    resource=Resource.create({'service.name': 'checkout-api'})
)
trace_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
tracer = trace_provider.get_tracer(__name__)


ConfigureLogger(
    log_path='./logs',
    pg_name='CheckoutAPI',
    structured=True,
    is_async=True,
    console_out=False,
)

# set_logging_format=True enables OTel's trace/span injection into LogRecord.
# enable_log_auto_instrumentation=False keeps this demo focused on local files;
# leave it at the default if you also want OTel's logging handler/export path.
LoggingInstrumentor().instrument(
    tracer_provider=trace_provider,
    set_logging_format=True,
    enable_log_auto_instrumentation=False,
    log_hook=log_hook,
)

logger = GetLogger('checkout.api')


def authorize_payment(order_id: str, amount: float):
    with tracer.start_as_current_span('authorize-payment'):
        logger.info(
            'Authorizing payment',
            extra={'order_id': order_id, 'amount': amount},
        )

        # ... call gateway ...

        logger.info(
            'Payment authorized',
            extra={'order_id': order_id, 'amount': amount, 'gateway': 'stripe'},
        )


authorize_payment('ord-1042', 249.00)
```

## Structured JSON Output

With `structured=True`, OpenTelemetry correlation fields become natural top-level
JSON fields:

```json
{
  "timestamp": "2026-04-06 18:40:12.381",
  "level": "INF",
  "logger": "checkout.api",
  "file": "otel_checkout_demo.py",
  "line": 39,
  "function": "authorize_payment",
  "message": "Payment authorized",
  "otelTraceID": "d7f8d3e6034fb8f43f50e3af1f80a4f1",
  "otelSpanID": "7c2b6a0a8e8df3d1",
  "otelServiceName": "checkout-api",
  "otelTraceSampled": true,
  "checkout_stage": "authorize",
  "from_sampled_span": true,
  "order_id": "ord-1042",
  "amount": 249.0,
  "gateway": "stripe"
}
```

This is the sweet spot for log pipelines:

- `otelTraceID` links directly to your tracing backend
- `order_id` and `amount` remain normal JSON fields for search/filter
- custom `log_hook` attributes like `checkout_stage` survive naturally

## Text Output Works Too

If you change `structured=True` to `structured=False`, pass a formatter that
references OpenTelemetry's injected LogRecord attributes:

```python
otel_text_fmt = (
    '%(asctime)s.%(msecs)03d [%(levelname)s] '
    'trace_id=%(otelTraceID)s span_id=%(otelSpanID)s '
    'service_name=%(otelServiceName)s trace_sampled=%(otelTraceSampled)s '
    '%(message)s'
)

ConfigureLogger(
    log_path='./logs',
    pg_name='CheckoutAPI',
    structured=False,
    fmt=otel_text_fmt,
)
```

```text
2026-04-06 18:40:12.381 [INFO] trace_id=d7f8d3e6034fb8f43f50e3af1f80a4f1 span_id=7c2b6a0a8e8df3d1 service_name=checkout-api trace_sampled=True Payment authorized
```

That means you do not need to switch to JSON just to keep trace correlation.

## Why async mode still works

When `is_async=True`, D-SafeLogger hands `LogRecord` objects to a queue and
formats them on the listener thread. OpenTelemetry's injected fields and
`log_hook` extensions are preserved across that hand-off, so the JSON output
still contains `otelTraceID`, `otelSpanID`, and any extra business attributes.

This matters for high-throughput APIs where you want:

- request threads to stay fast
- trace correlation to survive queueing
- append-only local files for postmortems

## What D-SafeLogger does — and does not do

D-SafeLogger does **not** replace the OpenTelemetry SDK.

- Use **OpenTelemetry** for distributed traces and OTLP export.
- Use **D-SafeLogger** for local append-only files, structured JSON, rotation,
  integrity hashing, and fast operational debugging.

They complement each other cleanly because both sit on stdlib `logging`.

## What's Next

- **[Web API Logging](06_web_api_logging.md)** — request correlation with
  `contextualize()` and per-module routing.
- **[Async & High Throughput](11_async_performance.md)** — when to enable
  `is_async=True` and how shutdown draining works.
- **[Migrating from stdlib](03_migration_from_stdlib.md)** — keep existing
  `logging.getLogger()` calls and layer D-SafeLogger underneath.
