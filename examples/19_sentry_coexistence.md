# Sentry Coexistence

D-SafeLogger does not replace remote error tracking. Sentry can continue to own
remote exception reporting while D-SafeLogger owns local evidence: durable JSON
Lines, append-only routing, and data available even when remote delivery is
disabled or unavailable.

This example intentionally does not claim that Sentry delivered anything
remotely. It only shows local evidence alongside a Sentry capture call.

```python
import os
from pathlib import Path

import sentry_sdk

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

Path("logs").mkdir(parents=True, exist_ok=True)

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    traces_sample_rate=0.0,
)

ConfigureLogger(
    log_path="logs",
    pg_name="SentryLocal",
    structured=True,
    console_out=False,
)

logger = GetLogger("checkout.sentry")

try:
    raise RuntimeError("payment provider rejected request")
except RuntimeError as exc:
    sentry_sdk.capture_exception(exc)
    logger.exception(
        "captured local exception",
        extra={"system": "sentry", "remote_delivery_claimed": False},
    )
finally:
    SafeShutdown()
```

Use this pattern when local forensic evidence is required even if remote error
tracking is rate-limited, disabled, blocked by the network, or sampled out.
