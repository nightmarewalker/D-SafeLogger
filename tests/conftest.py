"""Shared test fixtures for D-SafeLogger test suite."""

from __future__ import annotations

import logging
import os
import sys
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_logger_state():
    """Reset D-SafeLogger state between tests.

    This ensures each test starts with a clean logger environment.
    """
    import dsafelogger

    yield

    dsafelogger._reset_for_tests()

    # Remove all handlers from root logger
    root = logging.getLogger()
    for handler in root.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)

    # Reset logger class
    logging.setLoggerClass(logging.Logger)

    # Reset root logger level
    root.setLevel(logging.WARNING)

    # Clear all non-root loggers
    logging.Logger.manager.loggerDict.clear()


@pytest.fixture
def mp_state():
    """Reset dsafelogger.mp and _mp_attach state after each test.

    Use in any test that calls mp.ConfigureLogger() or otherwise starts a
    WriterRuntime.  Not autouse because it would add overhead to every test.
    """
    import dsafelogger._mp_attach as mp_attach_mod
    import dsafelogger.mp as mp_mod

    yield

    # Stop WriterRuntime if one was started during the test
    runtime = mp_mod._mp_writer_runtime
    try:
        mp_attach_mod._do_detach(best_effort=True)
    except Exception:
        pass
    if runtime is not None:
        try:
            runtime.stop(timeout=2.0)
        except Exception:
            pass

    mp_mod._mp_writer_runtime = None
    mp_mod._mp_atexit_registered = False
    mp_attach_mod._mp_runtime_state = None


@pytest.fixture
def clean_env():
    """Fixture to clean D_LOG_* environment variables."""
    env_keys = [
        'D_LOG_LEVEL', 'D_LOG_MODULES', 'D_LOG_CONFIG',
        'D_LOG_CONSOLE', 'D_LOG_COLOR', 'D_LOG_DIAGNOSE',
        'D_LOG_HASH', 'D_LOG_MANIFEST', 'NO_COLOR',
        'OTEL_PYTHON_LOG_CORRELATION', 'OTEL_PYTHON_LOG_FORMAT',
        'OTEL_PYTHON_LOG_LEVEL', 'OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION',
        'OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED',
        'OTEL_PYTHON_LOG_CODE_ATTRIBUTES',
    ]
    original = {k: os.environ.get(k) for k in env_keys}

    # Remove all D_LOG_* env vars
    for k in env_keys:
        os.environ.pop(k, None)

    yield

    # Restore original values
    for k, v in original.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
