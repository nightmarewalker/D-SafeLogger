# Using D-SafeLogger with structlog

`structlog` is a powerful and very popular library for structured logging in Python. It excels at assembling event dictionaries, managing context variables, and creating highly customized processor chains. 

If you already use `structlog` or want to leverage its elegant `logger.bind()` API, you don't have to choose between it and D-SafeLogger. In fact, **they complement each other perfectly when combined.**

- **structlog** excels at generating event dictionaries and context structures.
- **D-SafeLogger** excels at the final log delivery: file rotation, append-only strategies on Windows, asynchronous queues, module-based routing, SHA-256 integrity checks, and sensitive data masking.

This tutorial covers the two definitive patterns for integrating them.

---

## 1. Choosing the Integration Pattern

Before configuring them, you must decide *which system is responsible for the final output format*. This choice prevents conflicting formatters and double-JSON-encoding.

| Pattern | Best For | Architecture Concept |
|---|---|---|
| **[Pattern A: Dual Stream](#2-pattern-a-mechanic-json-via-structlog-human-text-via-d-safelogger)** | You need native JSON logs sent to a log aggregator (Datadog/Elastic) via `structlog`, but you *also* want human-readable text logs on disk for developers using D-SafeLogger. | **Separation of Duties**: Each library owns a dedicated output stream. |
| **[Pattern B: Unified Output](#3-pattern-b-unified-context-and-output)** | You want to use `structlog.bind()` for assembling context in your business logic, but you want **D-SafeLogger** to be the single source of truth for routing, formatting (JSON or Text), and rotation. | **Pipeline**: `structlog` hands off the assembled context to D-SafeLogger for final output. |

---

## 2. Pattern A: Mechanic JSON via structlog, Human Text via D-SafeLogger

In this pattern, you generate two logs per event. `structlog` handles the JSON output natively (using its own mechanisms to write to a file or stdout), while D-SafeLogger handles standard textual human-readable logs.

### Why use this pattern?
You can use `structlog`'s JSONRenderer without any conflict, while utilizing D-SafeLogger's environment configurations, text coloring, and crash diagnostics on a separate text stream.

### Architecture
```text
Business Event
   ├── machine_logger (structlog) → machine.jsonl
   └── human_logger (D-SafeLogger) → app_20260408.log
```

### Example Implementation

```python
import logging
from pathlib import Path

import structlog
from dsafelogger import ConfigureLogger, GetLogger

LOG_DIR = Path("./logs")
LOG_DIR.mkdir(exist_ok=True)
machine_log_file = LOG_DIR / "machine.jsonl"

# -----------------------------
# 1. D-SafeLogger: Human Logs
# -----------------------------
ConfigureLogger(
    log_path=str(LOG_DIR),
    pg_name="MyAppHuman",
    routing_mode="daily",
    structured=False,   # Keep as text
    console_out=True,
)
human_logger = GetLogger("human.app")

# -----------------------------
# 2. structlog: Machine JSON Logs
# -----------------------------
# Note: In a real application, you should manage the lifecycle of this file handle
# (e.g., closing it on application shutdown or using a context manager/atexit).
machine_stream = machine_log_file.open("a", encoding="utf-8")

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.WriteLoggerFactory(file=machine_stream),
)
machine_logger = structlog.get_logger("machine.app")

# -----------------------------
# 3. Usage
# -----------------------------
def process_order(order_id: int, user_id: str) -> None:
    # Machine Log (JSON)
    machine_logger.bind(order_id=order_id, user_id=user_id).info("order_processed", status="success")

    # Human Log (Text)
    human_logger.info("Order processed", extra={"order_id": order_id, "user_id": user_id, "status": "success"})

process_order(1042, "alice")
```

---

## 3. Pattern B: Unified Context and Output

In this pattern, you use `structlog` purely as a frontend API for your application logic. The context variables and event dictionaries are passed seamlessly into standard `logging`, where D-SafeLogger's powerful `DSafeFormatter` or `StructuredFormatter` takes over.

### The "Double Formatter" Problem
If not configured carefully, passing `structlog` to `logging` causes conflicts because `structlog.stdlib.ProcessorFormatter` and D-SafeLogger's `DSafeFormatter` fight to control `logging.Formatter`.
**Solution:** Do not use `structlog.stdlib.ProcessorFormatter`. Let D-SafeLogger own the final formatter, and use `structlog`'s specific bridge processors.

---

### Pattern B-1: structlog Frontend ➔ D-SafeLogger Text Output

If you want `structlog` context to appear cleanly in D-SafeLogger's textual log output, you must configure `structlog` to flatten its event dictionary into the `msg` string.

```python
import structlog
from dsafelogger import ConfigureLogger

# 1. Init D-SafeLogger as text output
ConfigureLogger(
    log_path="./logs",
    pg_name="MyApp",
    routing_mode="daily",
    structured=False,  # Text mode
    is_async=True,
)

# 2. Configure structlog as a frontend for stdlib logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        # Stringify the key-value pairs into the log message
        structlog.processors.KeyValueRenderer(
            key_order=["event"], drop_missing=True
        ),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

log = structlog.get_logger("checkout.api")

with structlog.contextvars.bound_contextvars(order_id=1042):
    log.info("payment_authorized", amount=5000)
    
# Output:
# 2026-04-08 00:00:00.000 [INF][myapp.py:32] event='payment_authorized' amount=5000 order_id=1042
```

> [!NOTE]
> In Pattern B-1, `structlog.processors.KeyValueRenderer` formats context into the string message natively (e.g., `amount=5000`). This differs visually from D-SafeLogger's native `contextualize()` API, which appends contexts as a clean bracketed suffix (e.g., `[amount:5000]`). If you mix both libraries for context in text mode, be aware of this visual difference.

---

### Pattern B-2: structlog Frontend ➔ D-SafeLogger JSON Output (Highly Recommended)

If you are using D-SafeLogger's `structured=True` mode, the integration is direct.
D-SafeLogger's `StructuredFormatter` extracts custom, unreserved variables from the
`LogRecord.__dict__`. By using `structlog.stdlib.render_to_log_kwargs` at the end
of the `structlog` chain, bound context variables are passed as standard `extra`
kwargs into Python `logging` and appear as first-class JSON fields.

```python
import structlog
from dsafelogger import ConfigureLogger

# 1. Init D-SafeLogger in JSON mode
ConfigureLogger(
    log_path="./logs",
    pg_name="MyApp",
    routing_mode="daily",
    structured=True,  # Crucial!
    is_async=True,
)

# 2. Configure structlog to pass variables into stdlib "extra"
structlog.configure(
    processors=[
        structlog.stdlib.PositionalArgumentsFormatter(),
        # Passes the event_dict dictionary into standard logging as 'extra' keyword arguments
        # No formatting occurs here, leaving it purely as context data!
        structlog.stdlib.render_to_log_kwargs, 
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

log = structlog.get_logger("chk_api")
log = log.bind(session_id="xy-123", tenant="acme")

log.info("checkout_completed", status="success")
```

The output written to disk by D-SafeLogger looks natively integrated:
```json
{"timestamp":"2026-04-08 00:00:00.000","level":"INF","logger":"chk_api","message":"checkout_completed","session_id":"xy-123","tenant":"acme","status":"success"}
```

### Why B-2 is the Ultimate Setup
* **No Format Conflicts**: `structlog` acts purely as a context manager; D-SafeLogger strictly handles the JSON serialization.
* **Diagnose Mode Compatibility**: If performance dips or exceptions throw, and you drop into `D_LOG_DIAGNOSE=1` mode, D-SafeLogger will still properly expand `f_locals` directly inside the JSON without breaking the pipeline.
* **Asynchronous Routing**: All properties extracted by `structlog` will perfectly traverse D-SafeLogger's non-blocking `QueueHandler` (via `is_async=True`) because they are fully integrated into the `LogRecord`.
