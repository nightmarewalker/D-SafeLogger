# Container and Collector Coexistence

Container platforms often collect stdout/stderr, and production deployments
often use Fluent Bit, Vector, Filebeat, OpenTelemetry Collector, or another log
pipeline. D-SafeLogger does not replace those tools.

Use D-SafeLogger when the application also needs local file safety, audit files,
append-only routing, or integrity sidecars before a collector takes over.

## The Scenario

You want:

- normal platform logs on stdout/stderr;
- local audit files with D-SafeLogger;
- optional collector configuration that tails those local files.

## What D-SafeLogger Owns

D-SafeLogger owns local application file output:

- append-only file routing;
- fail-fast setup for local destinations;
- JSON Lines formatting;
- hash sidecars and manifests when enabled.

## What the Collector Owns

The collector owns transport outside the process:

- file tailing;
- network delivery;
- buffering to a backend;
- retry policy;
- authentication to the remote platform.

## Pattern A: stdout for platform logs, D-SafeLogger for audit files

The application can print a compact platform event while D-SafeLogger writes
local audit records.

## Pattern B: collector tails D-SafeLogger files

A collector can tail the D-SafeLogger file directory. Treat the collector
configuration below as a sketch, not a drop-in production config.

```text
inputs:
  - path: /app/logs/audit/*.log
    parser: json
outputs:
  - name: your-observability-backend
```

## Complete Runnable Example

The tested scenario for this guide is maintained in
`tests/examples/test_17_container_collector_coexistence.py`.

```python
"""container_collector_coexistence.py"""

import json
from pathlib import Path

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def main() -> None:
    log_dir = Path("./logs/container-audit")
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="ContainerAudit",
        console_out=False,
        structured=True,
    )

    print(json.dumps({"stream": "platform", "event": "startup"}))

    audit = GetLogger("container.audit")
    audit.info(
        "local audit record",
        extra={"container_id": "local-dev", "operation": "startup"},
    )

    _shutdown()
    print(f"collector can tail: {log_dir / 'ContainerAudit.log'}")


if __name__ == "__main__":
    main()
```

## Example Collector Notes

- In a container, mount the local log directory where your collector can read it.
- Use JSON parsing if `structured=True`.
- Keep collector retry, authentication, and remote delivery policy outside
  D-SafeLogger.

## Boundaries

D-SafeLogger is not a log shipper, metrics backend, tracing backend, SIEM, or
access-control system. It can feed those systems by producing safe local files.

## What's Next

- [OpenTelemetry Logging Correlation](15_opentelemetry_logging.md)
- [Using D-SafeLogger with structlog](16_structlog_coexistence.md)

