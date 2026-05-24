"""Tests for the public SafeShutdown lifecycle API."""

from __future__ import annotations

import logging

import pytest

import dsafelogger
from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown


def test_internal_shutdown_is_noop_for_configure(tmp_path, clean_env):
    """atexit-style _shutdown() keeps ConfigureLogger() as a compatibility no-op."""
    ConfigureLogger(log_path=str(tmp_path), console_out=False)

    dsafelogger._shutdown()
    ConfigureLogger(log_path=str(tmp_path), default_level="DEBUG", console_out=False)

    assert dsafelogger._configure_state == "shutting_down"


def test_safe_shutdown_raises_for_configure_and_get(tmp_path, clean_env):
    ConfigureLogger(log_path=str(tmp_path), console_out=False)

    SafeShutdown()

    with pytest.raises(RuntimeError, match="SafeShutdown\\(\\) has been called"):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
    with pytest.raises(RuntimeError, match="SafeShutdown\\(\\) has been called"):
        GetLogger("after-safe-shutdown")


def test_safe_shutdown_is_idempotent(tmp_path, clean_env):
    ConfigureLogger(log_path=str(tmp_path), console_out=False)

    SafeShutdown()
    SafeShutdown()

    assert dsafelogger._configure_state == "terminal_shutdown"


def test_safe_shutdown_flushes_records(tmp_path, clean_env):
    ConfigureLogger(log_path=str(tmp_path), console_out=False)
    logger = GetLogger("safe-shutdown.flush")

    logger.info("record before terminal shutdown")
    SafeShutdown()

    contents = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.log"))
    assert "record before terminal shutdown" in contents


def test_safe_shutdown_removes_handlers(tmp_path, clean_env):
    ConfigureLogger(log_path=str(tmp_path), console_out=False)
    assert logging.getLogger().handlers

    SafeShutdown()

    assert not any(
        handler.__class__.__module__.startswith("dsafelogger")
        for handler in logging.getLogger().handlers
    )


def test_reset_clears_terminal_shutdown(tmp_path, clean_env):
    SafeShutdown()
    assert dsafelogger._configure_state == "terminal_shutdown"

    dsafelogger._reset_for_tests()
    ConfigureLogger(log_path=str(tmp_path), console_out=False)

    assert dsafelogger._configure_state == "explicit"
