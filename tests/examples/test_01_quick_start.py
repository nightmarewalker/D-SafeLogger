"""Runnable scenario for examples/01_quick_start.md."""

from __future__ import annotations

import re

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def test_quick_start_complete_runnable_example_outputs_all_levels(
    tmp_path,
    capsys,
    clean_env,
):
    log_dir = tmp_path / 'logs'

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name='QuickStart',
        routing_mode='daily',
        default_level='DEBUG',
    )

    logger = GetLogger(__name__)
    expected = [
        ('DBG', 'Loaded 142 configuration entries from cache'),
        ('INF', 'Server started on port 8080'),
        ('WAR', 'TLS certificate expires in 7 days'),
        ('ERR', 'Failed to connect to payment gateway'),
        ('CRI', 'Failed over to read-only mode'),
    ]

    logger.debug(expected[0][1])
    logger.info(expected[1][1])
    logger.warning(expected[2][1])
    logger.error(expected[3][1])
    logger.critical(expected[4][1])
    _shutdown()

    console_output = _ANSI_RE.sub('', capsys.readouterr().err)
    for level, message in expected:
        assert f'[{level}]' in console_output
        assert message in console_output

    log_files = sorted(log_dir.glob('QuickStart*.log'))
    assert len(log_files) == 1

    file_output = log_files[0].read_text(encoding='utf-8')
    assert '\x1b[' not in file_output
    for level, message in expected:
        assert f'[{level}]' in file_output
        assert message in file_output
