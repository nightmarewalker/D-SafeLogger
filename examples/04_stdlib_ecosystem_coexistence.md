# Stdlib Ecosystem Coexistence

D-SafeLogger is designed to extend the standard `logging` path, not replace it.
Application modules and libraries that call `logging.getLogger()` can participate
in the same configured logging setup.

This example uses only the standard library and `dsafelogger`. The "third-party"
module below is intentionally just a local function that behaves like a library:
it obtains its own logger through `logging.getLogger()` and does not import
D-SafeLogger directly.

## The Scenario

You have:

- application code using `logging.getLogger("orders.api")`;
- library-style code using `logging.getLogger("vendor.payments")`;
- one centralized D-SafeLogger setup at process startup.

The goal is to keep those call sites unchanged while giving the application a
single logging policy.

## Existing Library-Style Code

```python
import logging


def charge_card(order_id: str) -> None:
    logger = logging.getLogger("vendor.payments")
    logger.info("authorized payment", extra={"order_id": order_id})
```

The function does not know about D-SafeLogger. It just uses stdlib logging.

## Application Setup

Configure D-SafeLogger once, before the application starts doing work. The
module section below sends `vendor.payments` to its own file while normal
application records continue through the root route.

```python
from dsafelogger import ConfigureLogger

ConfigureLogger(
    log_path="./logs/ecosystem",
    pg_name="Ecosystem",
    console_out=False,
    structured=True,
    config_dict={
        "global": {"default_level": "INFO"},
        "dsafelogger:vendor.payments": {
            "level": "INFO",
            "path": "./logs/ecosystem/vendor_payments.log",
        },
    },
)
```

## Module-Specific Routing

> This is a concrete instance of normal production isolation from
> `24_per_module_log_control.md`: a selected high-value or integration-facing
> logger is routed to its own file while the rest of the application keeps its
> normal logging layout.

After setup:

- `logging.getLogger("orders.api")` writes through the root D-SafeLogger route;
- `logging.getLogger("vendor.payments")` writes to `vendor_payments.log`;
- no application log call site needs to be changed to a new logger API.

## Complete Runnable Example

The tested scenario for this guide is maintained in
`tests/examples/test_04_stdlib_ecosystem_coexistence.py`.

```python
"""stdlib_ecosystem_coexistence.py"""

import logging
from pathlib import Path

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown


def charge_card(order_id: str) -> None:
    logging.getLogger("vendor.payments").info(
        "authorized payment",
        extra={"order_id": order_id},
    )


def main() -> None:
    log_dir = Path("./logs/ecosystem")
    vendor_log = log_dir / "vendor_payments.log"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="Ecosystem",
        console_out=False,
        structured=True,
        config_dict={
            "global": {"default_level": "INFO"},
            "dsafelogger:vendor.payments": {
                "level": "INFO",
                "path": str(vendor_log),
            },
        },
    )

    app_log = GetLogger("orders.api")
    app_log.info("received order", extra={"order_id": "ord-1001"})
    charge_card("ord-1001")

    SafeShutdown()
    print(f"application log: {log_dir / 'Ecosystem.log'}")
    print(f"library-style log: {vendor_log}")


if __name__ == "__main__":
    main()
```

## How to Run

```bash
python stdlib_ecosystem_coexistence.py
```

For repository validation, run the maintained scenario test:

```bash
uv run pytest tests/examples/test_04_stdlib_ecosystem_coexistence.py -q
```

## What to Check

- `Ecosystem.log` contains the application record.
- `vendor_payments.log` contains the library-style record.
- `vendor.payments` did not import or call D-SafeLogger directly.

## What's Next

- [Windows Service and Scheduled Batch Logging](05_windows_service_and_scheduled_batch.md)
- [Migrating from stdlib `logging`](03_migration_from_stdlib.md)
