# Web API Logging

In a web API handling hundreds of concurrent requests, a log line like
`Processing complete` is useless. Which request? Which user? Which endpoint?

D-SafeLogger's `contextualize()` context manager attaches request metadata to
every log line automatically, while per-module routing directs database queries to
a separate file and structured JSON output feeds your log aggregation pipeline.

## The Scenario

An **order processing API** with three modules, each with different logging needs:

| Module | Level | Destination | Why |
|--------|-------|-------------|-----|
| `myapp.api` | INFO | Main log | Request lifecycle events |
| `myapp.db` | DEBUG | `db_queries.log` | Slow query analysis — too noisy for main log |
| `myapp.payment` | WARNING | `payment_alerts.log` | Only surface payment anomalies |

All output is **structured JSON** so it can be ingested by ELK, Datadog, or Loki.

## The INI Configuration

Save as `api_logging.ini`:

```ini
[global]
default_level = INFO
log_path = ./logs
pg_name = OrderAPI
routing_mode = daily
structured = true

[dsafelogger:myapp.db]
level = DEBUG
path = db_queries.log

[dsafelogger:myapp.payment]
level = WARNING
path = payment_alerts.log
```

Key points:

- `structured = true` → every log line is a JSON object
- `myapp.db` at DEBUG with its own file keeps query noise out of the main log
- `myapp.payment` at WARNING with its own file keeps high-value payment alerts separate

> These are concrete instances of normal production isolation from
> `24_per_module_log_control.md`: high-volume database logs and high-value
> payment logs are separated from the main request-flow log.

## The Application Code

```python
"""order_api.py — Realistic web API logging with D-SafeLogger."""

from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(config_file='api_logging.ini')

api_logger = GetLogger('myapp.api')
db_logger = GetLogger('myapp.db')
payment_logger = GetLogger('myapp.payment')


def handle_order(request_id: str, user: str, amount: float):
    """Process an incoming order request."""

    # contextualize() attaches key-value pairs to every log line
    # inside this block — no need to pass request_id manually.
    with api_logger.contextualize(request_id=request_id, user=user):
        api_logger.info(f'POST /orders - amount={amount}')

        # DB operations in their own context — goes to db_queries.log
        with db_logger.contextualize(request_id=request_id):
            db_logger.debug('BEGIN TRANSACTION')
            db_logger.debug(
                'INSERT INTO orders (user, amount) VALUES (%s, %s)',
            )
            db_logger.debug('COMMIT')

        # Payment warnings only surface for high-value orders
        if amount > 1000:
            with payment_logger.contextualize(
                request_id=request_id, amount=amount,
            ):
                payment_logger.warning(f'High-value order: {amount}')

        api_logger.info('Order completed successfully')
```

## The Output

### Main Log (`./logs/OrderAPI_20260403.log`)

Every JSON line includes the context keys set by `contextualize()`:

```json
{"timestamp":"2026-04-03T09:15:22.738","level":"INF","logger":"myapp.api","file":"order_api.py","line":19,"function":"handle_order","message":"POST /orders - amount=2500.00","request_id":"req-a1b2","user":"alice"}
{"timestamp":"2026-04-03T09:15:22.742","level":"INF","logger":"myapp.api","file":"order_api.py","line":36,"function":"handle_order","message":"Order completed successfully","request_id":"req-a1b2","user":"alice"}
```

### DB Query Log (`./logs/db_queries.log`)

```json
{"timestamp":"2026-04-03T09:15:22.739","level":"DEBUG","logger":"myapp.db","file":"order_api.py","line":23,"function":"handle_order","message":"BEGIN TRANSACTION","request_id":"req-a1b2"}
{"timestamp":"2026-04-03T09:15:22.740","level":"DEBUG","logger":"myapp.db","file":"order_api.py","line":24,"function":"handle_order","message":"INSERT INTO orders (user, amount) VALUES (%s, %s)","request_id":"req-a1b2"}
{"timestamp":"2026-04-03T09:15:22.740","level":"DEBUG","logger":"myapp.db","file":"order_api.py","line":27,"function":"handle_order","message":"COMMIT","request_id":"req-a1b2"}
```

### Payment Alert Log (`./logs/payment_alerts.log`)

```json
{"timestamp":"2026-04-03T09:15:22.741","level":"WAR","logger":"myapp.payment","file":"order_api.py","line":33,"function":"handle_order","message":"High-value order: 2500.0","request_id":"req-a1b2","amount":2500.0}
```

### Filtering with jq

Because the output is structured JSON, you can filter by any field:

```bash
# Find all entries for a specific request across ALL log files
cat logs/*.log | jq -s 'sort_by(.timestamp) | .[] | select(.request_id == "req-a1b2")'

# Show only warnings and errors
cat logs/OrderAPI_20260403.log | jq 'select(.level == "WAR" or .level == "ERR")'

# List unique request IDs that hit the payment module
cat logs/payment_alerts.log | jq -r '.request_id' | sort -u
```

## Correlation Across Services

The `request_id` pattern scales beyond a single process. If your API receives a
trace ID from an upstream gateway (e.g., `X-Request-ID` header), pass it into
`contextualize()` and every downstream log entry — across HTTP handlers, background
workers, and database calls — carries the same correlation key. Your log aggregator
can then reconstruct the full request lifecycle across services.

If you already use OpenTelemetry spans instead of a custom `request_id`, see
**[OpenTelemetry Logging](15_opentelemetry_logging.md)** for the same idea using
`LoggingInstrumentor` and automatic `otelTraceID` / `otelSpanID` injection.

```python
def middleware(request, call_next):
    request_id = request.headers.get('X-Request-ID', str(uuid4()))
    with api_logger.contextualize(request_id=request_id):
        response = call_next(request)
    return response
```

## Complete Runnable Example

Save as `web_api_demo.py`:

```python
"""web_api_demo.py — Simulates concurrent API requests with correlated logging."""

import uuid
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(config_file='api_logging.ini')

api_logger = GetLogger('myapp.api')
db_logger = GetLogger('myapp.db')
payment_logger = GetLogger('myapp.payment')


def handle_order(request_id: str, user: str, amount: float):
    with api_logger.contextualize(request_id=request_id, user=user):
        api_logger.info(f'POST /orders - amount={amount}')

        with db_logger.contextualize(request_id=request_id):
            db_logger.debug('BEGIN TRANSACTION')
            db_logger.debug(f'INSERT INTO orders (user, amount) VALUES ({user!r}, {amount})')
            db_logger.debug('COMMIT')

        if amount > 1000:
            with payment_logger.contextualize(request_id=request_id, amount=amount):
                payment_logger.warning(f'High-value order requires review: {amount}')

        api_logger.info('Order completed successfully')


def main():
    # Simulate 3 concurrent requests
    requests = [
        ('alice', 250.00),
        ('bob', 2500.00),
        ('carol', 89.99),
    ]

    for user, amount in requests:
        request_id = f'req-{uuid.uuid4().hex[:8]}'
        print(f'Processing order: user={user} amount={amount} id={request_id}')
        handle_order(request_id, user, amount)

    print('\n✓ Check ./logs/ for structured JSON output.')
    print('  Main log:     ./logs/OrderAPI_<date>.log')
    print('  DB queries:   ./logs/db_queries.log')
    print('  Try: cat logs/*.log | python -m json.tool')


if __name__ == '__main__':
    main()
```

## How to Run

```bash
# 1. Create the INI file (api_logging.ini) from the section above
# 2. Run the demo
python web_api_demo.py

# 3. Inspect the output
cat logs/OrderAPI_*.log | python -m json.tool
cat logs/db_queries.log | python -m json.tool

# 4. Filter with jq (if installed)
cat logs/*.log | jq 'select(.user == "bob")'
```

## What's Next

- **[Long-Running Service](07_long_running_service.md)** — Log rotation strategies
  for services that run for months.
- **[Compliance & Audit Logging](08_compliance_audit.md)** — SHA-256 integrity
  verification and structured JSON for regulated environments.
- **[Async & High Throughput](11_async_performance.md)** — Non-blocking logging for
  high-throughput services using `is_async=True`.
- **[OpenTelemetry Logging](15_opentelemetry_logging.md)** — Reuse stdlib
  `LoggingInstrumentor` and correlate local logs with distributed traces.
