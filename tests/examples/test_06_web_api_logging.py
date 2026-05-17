"""Runnable scenario for examples/06_web_api_logging.md."""

from __future__ import annotations

import json

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def test_web_api_logging_routes_contextual_json(tmp_path, clean_env):
    log_dir = tmp_path / "logs"
    db_log = log_dir / "db_queries.log"
    payment_log = log_dir / "payment_alerts.log"
    ini = tmp_path / "api_logging.ini"
    ini.write_text(
        "[global]\n"
        "default_level = INFO\n"
        f"log_path = {log_dir}\n"
        "pg_name = OrderAPI\n"
        "routing_mode = none\n"
        "structured = true\n"
        "console_out = false\n\n"
        "[dsafelogger:myapp.db]\n"
        "level = DEBUG\n"
        f"path = {db_log}\n\n"
        "[dsafelogger:myapp.payment]\n"
        "level = WARNING\n"
        f"path = {payment_log}\n",
        encoding="utf-8",
    )

    ConfigureLogger(config_file=str(ini))

    api_logger = GetLogger("myapp.api")
    db_logger = GetLogger("myapp.db")
    payment_logger = GetLogger("myapp.payment")

    with api_logger.contextualize(request_id="req-a1b2", user="alice"):
        api_logger.info("POST /orders - amount=2500.0")
        with db_logger.contextualize(request_id="req-a1b2"):
            db_logger.debug("BEGIN TRANSACTION")
            db_logger.debug("COMMIT")
        with payment_logger.contextualize(request_id="req-a1b2", amount=2500.0):
            payment_logger.warning("High-value order: 2500.0")
        api_logger.info("Order completed successfully")
    _shutdown()

    main_records = [
        json.loads(line)
        for line in (log_dir / "OrderAPI.log").read_text(encoding="utf-8").splitlines()
    ]
    db_records = [json.loads(line) for line in db_log.read_text(encoding="utf-8").splitlines()]
    payment_records = [
        json.loads(line) for line in payment_log.read_text(encoding="utf-8").splitlines()
    ]

    assert any(r["message"] == "Order completed successfully" for r in main_records)
    assert any(r["logger"] == "myapp.payment" and r["amount"] == 2500.0 for r in payment_records)
    assert all(r.get("request_id") == "req-a1b2" for r in db_records)
    assert [r["message"] for r in db_records] == ["BEGIN TRANSACTION", "COMMIT"]
