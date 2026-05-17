"""Tests for GetLogger (separate from test_configure.py)."""

from __future__ import annotations

import logging
import os

import pytest
import dsafelogger
from dsafelogger import ConfigureLogger, GetLogger
from dsafelogger._logger import DSafeLogger


class TestGetLogger:
    """UT-GL: GetLogger tests."""

    def test_returns_dsafe_logger(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger('myapp')
        assert isinstance(logger, DSafeLogger)

    def test_same_name_same_instance(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        a = GetLogger('myapp')
        b = GetLogger('myapp')
        assert a is b

    def test_different_names_different_instances(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        a = GetLogger('a')
        b = GetLogger('b')
        assert a is not b

    def test_empty_string_root_logger(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger('')
        assert logger.name == 'root'

    def test_no_args_root_logger(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger()
        assert logger.name == 'root'

    def test_auto_fire_before_configure(self, tmp_path, clean_env):
        os.chdir(tmp_path)
        logger = GetLogger('early')
        assert isinstance(logger, logging.Logger)
        assert dsafelogger._configure_state == 'auto'

    def test_auto_then_explicit_reconfigure(self, tmp_path, clean_env):
        os.chdir(tmp_path)
        GetLogger('early')  # Auto-fire
        assert dsafelogger._configure_state == 'auto'

        ConfigureLogger(log_path=str(tmp_path), default_level='DEBUG', console_out=False)
        assert dsafelogger._configure_state == 'explicit'
        assert logging.getLogger().level == logging.DEBUG
