"""Tests for dsafelogger._logger (DSafeLogger)."""

from __future__ import annotations

import logging

from dsafelogger._logger import DSafeLogger
from dsafelogger._context import get_context


class TestLoggerCapture:
    """UT-GL-001 to UT-GL-005: Logger Capture & Context"""

    def test_logger_is_logging_logger(self):
        logger = DSafeLogger('test_logger')
        assert isinstance(logger, logging.Logger)

    def test_contextualize_delegation(self):
        logger = DSafeLogger('test_logger_ctx')
        assert hasattr(logger, 'contextualize')
        
        with logger.contextualize(foo='bar'):
            ctx = get_context()
            assert ctx['foo'] == 'bar'

    def test_standard_logging_methods_work(self, caplog):
        logging.setLoggerClass(DSafeLogger)
        logger = logging.getLogger('test_std')
        logger.setLevel(logging.DEBUG)
        logger.propagate = True
        
        with caplog.at_level(logging.DEBUG, logger='test_std'):
            logger.debug('debug msg')
            logger.info('info msg')
            logger.warning('warn msg')
            logger.error('err msg')
            logger.critical('crit msg')
        
        records = caplog.records
        assert len(records) == 5
        levels = [r.levelname for r in records]
        assert levels == ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

