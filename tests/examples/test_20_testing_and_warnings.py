"""Runnable scenarios for examples/20_testing_and_warnings.md."""

from __future__ import annotations

import logging
import warnings

from dsafelogger import ConfigureLogger, GetLogger


def test_caplog_and_file_sink_receive_same_record(tmp_path, caplog, clean_env):
    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="PytestCaplog",
        structured=True,
        console_out=False,
    )

    logger = GetLogger("tests.caplog")

    with caplog.at_level(logging.INFO, logger="tests.caplog"):
        logger.info("caplog and file sink both receive this", extra={"case": "caplog"})

    log_path = tmp_path / "PytestCaplog.log"
    assert "caplog and file sink both receive this" in caplog.text
    assert "caplog and file sink both receive this" in log_path.read_text(
        encoding="utf-8"
    )


def test_warnings_capture_routes_to_file_and_restores_showwarning(tmp_path, clean_env):
    original_showwarning = warnings.showwarning

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="WarningsRoute",
        structured=True,
        console_out=False,
    )

    logging.captureWarnings(True)
    try:
        warnings.warn("deprecated option", DeprecationWarning, stacklevel=1)
    finally:
        logging.captureWarnings(False)

    log_path = tmp_path / "WarningsRoute.log"
    assert warnings.showwarning is original_showwarning
    assert "deprecated option" in log_path.read_text(encoding="utf-8")
