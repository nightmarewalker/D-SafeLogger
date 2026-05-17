"""Runnable scenario for examples/04_stdlib_ecosystem_coexistence.md."""

from __future__ import annotations

import logging
import json

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def _charge_card(order_id: str) -> None:
    logging.getLogger("vendor.payments").info(
        "authorized payment",
        extra={"order_id": order_id},
    )


def test_stdlib_ecosystem_coexistence(tmp_path, clean_env):
    log_dir = tmp_path / "logs"
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
    _charge_card("ord-1001")
    _shutdown()

    app_records = [
        json.loads(line)
        for line in (log_dir / "Ecosystem.log").read_text(encoding="utf-8").splitlines()
    ]
    vendor_records = [
        json.loads(line)
        for line in vendor_log.read_text(encoding="utf-8").splitlines()
    ]

    assert any(record["message"] == "received order" for record in app_records)
    assert any(record["message"] == "authorized payment" for record in vendor_records)
    assert any(record.get("order_id") == "ord-1001" for record in vendor_records)
