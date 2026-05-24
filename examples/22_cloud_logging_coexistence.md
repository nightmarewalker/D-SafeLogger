# Cloud Logging Coexistence

<!-- example-test: docs-only; remote cloud delivery requires credentials, network, quotas, and backend state outside D-SafeLogger scope -->

## 1. What this guide covers

This guide explains how to use D-SafeLogger alongside cloud logging platforms
such as Google Cloud Logging, AWS CloudWatch, Datadog, or a hosted collector
pipeline.

It is docs-only because remote cloud delivery cannot be verified in the
repository test suite without real credentials, network access, quota state,
and backend ingestion checks. D-SafeLogger does not own those concerns.

## 2. Ownership boundary

Use D-SafeLogger for durable local evidence. Let cloud SDKs, agents, or
collectors own remote delivery.

| Component | Owns |
|---|---|
| D-SafeLogger | local JSON Lines files, append-only routing, fail-fast local path validation, hash sidecars |
| Cloud SDK handler | authentication, API calls, remote retries, backend-specific formatting |
| Collector / agent | file tailing, buffering, network delivery, backend ingestion policy |
| Cloud backend | indexing, retention, alerting, search, dashboards |

## 3. Pattern A: local files tailed by a collector

This is the preferred production shape when you need a local audit trail and a
cloud backend.

D-SafeLogger writes local structured files:

<!-- example-test: docs-only; cloud collector runtime is outside D-SafeLogger scope -->

```python
from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

ConfigureLogger(
    log_path="/var/log/myapp",
    pg_name="OrderService",
    structured=True,
    console_out=False,
)

logger = GetLogger("orders")
logger.info("order accepted", extra={"order_id": "ord-123"})

SafeShutdown()
```

Your collector tails those files and ships them:

<!-- example-test: docs-only; collector configuration is platform-specific -->

```text
inputs:
  - path: /var/log/myapp/OrderService.log
    parser: json
outputs:
  - name: your-cloud-logging-backend
```

D-SafeLogger does not manage collector buffering, authentication, retry, or
remote ingestion status.

## 4. Pattern B: split local evidence and cloud handler

If an application already uses a cloud logging handler, keep it as a separate
stdlib logging handler. D-SafeLogger keeps the local durable file. The cloud
handler owns remote delivery.

<!-- example-test: docs-only; cloud handler imports and credentials are deployment-specific -->

```python
import logging

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

ConfigureLogger(
    log_path="./logs",
    pg_name="BillingWorker",
    structured=True,
    console_out=False,
)

# Example shape only:
# cloud_handler = CloudLoggingHandler(...)
# logging.getLogger().addHandler(cloud_handler)

logger = GetLogger("billing")
logger.error("invoice sync failed", extra={"invoice_id": "inv-456"})

SafeShutdown()
```

Do not treat D-SafeLogger as proof that the cloud backend received the record.
Remote acknowledgement, retries, quota failures, and backend visibility are
cloud SDK or collector responsibilities.

## 5. What not to claim

- Do not claim this repository tests Google Cloud Logging, CloudWatch, Datadog,
  or any other remote backend.
- Do not use dummy credentials to make remote delivery appear successful.
- Do not make cloud handlers the primary D-SafeLogger sink.
- Do not describe D-SafeLogger as a log shipper or cloud ingestion client.

## 6. Relationship to container collectors

For container stdout/stderr and local collector patterns, see
[Container and Collector Coexistence](17_container_collector_coexistence.md).
This guide focuses on the cloud ownership boundary; the container guide focuses
on local file tailing and platform collector coexistence.

## 7. What's Next

- [Container and Collector Coexistence](17_container_collector_coexistence.md)
- [OpenTelemetry Logging Correlation](15_opentelemetry_logging.md)
- [Incident Response Bundle](10_incident_response_bundle.md)
