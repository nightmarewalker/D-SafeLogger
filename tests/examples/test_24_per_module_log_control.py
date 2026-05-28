"""Runnable scenarios for examples/24_per_module_log_control.md."""

from __future__ import annotations

from dsafelogger import ConfigureLogger, GetLogger, RegisterLevel, _shutdown


def test_per_module_log_control_normal_production_isolates_selected_modules(tmp_path, clean_env):
    log_dir = tmp_path / "logs"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="OrderService",
        console_out=False,
        default_level="INFO",
        config_dict={
            "global": {"default_level": "INFO"},
            # High-volume module: keep query noise out of the main log.
            "dsafelogger:myapp.db": {"level": "WARNING", "path": "db_warnings.log"},
            # High-value module: keep payment anomalies separate.
            "dsafelogger:myapp.payment": {"level": "WARNING", "path": "payment_alerts.log"},
            # Background worker: keep long-running task events separate.
            "dsafelogger:myapp.tasks": {"level": "INFO", "path": "worker_tasks.log"},
        },
    )

    api_logger = GetLogger("myapp.api")
    db_logger = GetLogger("myapp.db")
    payment_logger = GetLogger("myapp.payment")
    tasks_logger = GetLogger("myapp.tasks")

    api_logger.info("request received")
    db_logger.info("noisy query that should be filtered")
    db_logger.warning("slow query detected")
    payment_logger.warning("payment anomaly detected")
    tasks_logger.info("background task started")
    _shutdown()

    main_log = (log_dir / "OrderService.log").read_text(encoding="utf-8")
    db_log = (log_dir / "db_warnings.log").read_text(encoding="utf-8")
    payment_log = (log_dir / "payment_alerts.log").read_text(encoding="utf-8")
    tasks_log = (log_dir / "worker_tasks.log").read_text(encoding="utf-8")

    # Each module writes to its own dedicated file.
    assert "slow query detected" in db_log
    assert "payment anomaly detected" in payment_log
    assert "background task started" in tasks_log

    # The module's INFO noise is filtered at WARNING.
    assert "noisy query that should be filtered" not in db_log

    # The main log stays focused on application flow; module records are isolated.
    assert "request received" in main_log
    assert "slow query detected" not in main_log
    assert "payment anomaly detected" not in main_log
    assert "background task started" not in main_log


def test_per_module_log_control_development_lowers_one_module_only(tmp_path, clean_env):
    log_dir = tmp_path / "logs"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="OrderServiceDev",
        console_out=False,
        default_level="INFO",
        config_dict={
            "global": {"default_level": "INFO"},
            "dsafelogger:myapp.parser": {"level": "DEBUG", "path": "parser_debug.log"},
        },
    )

    parser_logger = GetLogger("myapp.parser")
    other_logger = GetLogger("myapp.other")

    parser_logger.debug("parser internal state dump")
    other_logger.debug("unrelated debug that should be filtered")
    other_logger.info("unrelated info")
    _shutdown()

    parser_log = (log_dir / "parser_debug.log").read_text(encoding="utf-8")
    main_log = (log_dir / "OrderServiceDev.log").read_text(encoding="utf-8")

    # The target module's DEBUG is captured in its own file.
    assert "parser internal state dump" in parser_log

    # Unrelated modules stay at the global INFO level: their DEBUG is filtered.
    assert "unrelated debug that should be filtered" not in main_log
    assert "unrelated debug that should be filtered" not in parser_log
    assert "unrelated info" in main_log


def test_per_module_log_control_incident_response_redirects_one_module(tmp_path, monkeypatch, clean_env):
    log_dir = tmp_path / "logs"
    incident_path = tmp_path / "incidents" / "checkout_trace.log"

    RegisterLevel("TRACE", 5, "TRC", "\033[90m")
    monkeypatch.setenv("D_LOG_MODULES", f"myapp.checkout:TRACE:{incident_path}")

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="OrderService",
        console_out=False,
        default_level="INFO",
    )

    checkout_logger = GetLogger("myapp.checkout")
    other_logger = GetLogger("myapp.other")

    checkout_logger.trace("checkout step trace evidence")
    other_logger.debug("unrelated debug should not be collected")
    other_logger.info("unrelated info")
    _shutdown()

    # The incident file is created at the explicit override path.
    assert incident_path.exists()
    incident_log = incident_path.read_text(encoding="utf-8")
    main_log = (log_dir / "OrderService.log").read_text(encoding="utf-8")

    # Only the suspect module's TRACE lands in the incident file.
    assert "[TRC]" in incident_log
    assert "checkout step trace evidence" in incident_log

    # Other modules' DEBUG/TRACE do not leak into the incident file,
    # and the suspect module's trace does not pollute the main log.
    assert "unrelated debug should not be collected" not in incident_log
    assert "checkout step trace evidence" not in main_log


def test_per_module_log_control_path_resolution_and_fail_fast_creation(tmp_path, clean_env):
    log_dir = tmp_path / "logs"
    explicit_dir = tmp_path / "explicit"
    explicit_path = explicit_dir / "audit.log"

    # explicit_dir does not exist yet; ConfigureLogger() must create it fail-fast.
    assert not explicit_dir.exists()

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="MyApp",
        console_out=False,
        default_level="INFO",
        config_dict={
            "global": {"default_level": "INFO"},
            # Simple file name → placed under the global log_path.
            "dsafelogger:myapp.db": {"level": "DEBUG", "path": "db_queries.log"},
            # Explicit path → written to its own parent directory.
            "dsafelogger:myapp.audit": {"level": "INFO", "path": str(explicit_path)},
        },
    )

    # The missing parent directory was created during configuration.
    assert explicit_dir.exists()

    db_logger = GetLogger("myapp.db")
    audit_logger = GetLogger("myapp.audit")

    db_logger.debug("SELECT 1")
    audit_logger.info("user exported data")
    _shutdown()

    # Simple file name resolves under the global log_path.
    simple_path = log_dir / "db_queries.log"
    assert simple_path.exists()
    assert "SELECT 1" in simple_path.read_text(encoding="utf-8")

    # Explicit path resolves to its own parent directory.
    assert explicit_path.exists()
    assert "user exported data" in explicit_path.read_text(encoding="utf-8")
