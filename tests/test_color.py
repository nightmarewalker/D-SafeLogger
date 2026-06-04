"""Tests for dsafelogger._color (ColorStreamHandler)."""

from __future__ import annotations

import io
import json
import logging
import sys

import pytest
from dsafelogger import ConfigureLogger, GetLogger, RegisterLevel, _shutdown
from dsafelogger._color import ColorStreamHandler
from dsafelogger._formatter import ConsoleDecoratingFormatter, DSafeFormatter


def _make_record(level: int = logging.INFO) -> logging.LogRecord:
    record = logging.LogRecord(
        'test', level, 'test.py', 1, 'test message', (), None,
    )
    return record


class TestColorStreamHandler:
    """UT-CSH: ColorStreamHandler tests."""

    def test_color_dbg(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.DEBUG)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[36mDBG\033[0m' in output

    def test_color_inf(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.INFO)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[32mINF\033[0m' in output

    def test_color_war(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.WARNING)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[33mWAR\033[0m' in output

    def test_color_err(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.ERROR)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[31mERR\033[0m' in output

    def test_color_cri(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.CRITICAL)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[1;31mCRI\033[0m' in output

    def test_color_disabled(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=False)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.ERROR)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[' not in output

    def test_default_stream_stderr(self):
        handler = ColorStreamHandler()
        assert handler.stream is sys.stderr

    def test_color_override(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(
            stream=stream,
            color_enabled=True,
            color_overrides={'ERR': '35'},  # Magenta
        )
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.ERROR)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[35mERR\033[0m' in output

    def test_color_disable_override(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(
            stream=stream,
            color_enabled=True,
            color_overrides={'DBG': ''},  # Disable
        )
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.DEBUG)
        handler.emit(record)
        output = stream.getvalue()
        # DBG should NOT have color code
        assert '\033[36m' not in output

    def test_reset_code(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.INFO)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[0m' in output  # Reset

    def test_registered_custom_level_uses_abbreviation_for_color_lookup(self):
        RegisterLevel('TRACE', 5, 'TRC', '\033[35m')
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(5)
        handler.emit(record)
        output = stream.getvalue()
        assert '\033[35mTRC\033[0m' in output


class TestColorStreamHandlerStylesAndImmutability:
    """UT-CSH-015 to UT-CSH-018: format style coverage and levelname immutability."""

    def test_percent_style_with_color(self):
        """UT-CSH-015: % style formatter receives coloured levelname from proxy."""
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.INFO)
        handler.emit(record)
        assert '\033[32mINF\033[0m' in stream.getvalue()

    def test_brace_style_with_color(self):
        """UT-CSH-016: {} style formatter receives coloured levelname from proxy."""
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('{levelname}', style='{'))
        record = _make_record(logging.INFO)
        handler.emit(record)
        assert '\033[32mINF\033[0m' in stream.getvalue()

    def test_dollar_style_with_color(self):
        """UT-CSH-017: $ style formatter receives coloured levelname from proxy."""
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('${levelname}', style='$'))
        record = _make_record(logging.INFO)
        handler.emit(record)
        assert '\033[32mINF\033[0m' in stream.getvalue()

    def test_levelname_immutable_after_emit(self):
        """UT-CSH-018: record.levelname is not mutated by emit()."""
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.INFO)
        original = record.levelname
        handler.emit(record)
        assert record.levelname == original

    def test_custom_level_levelname_immutable(self):
        """UT-CSH-019: custom level record.levelname is not mutated by emit()."""
        RegisterLevel('TRACE2', 6, 'TR2', '\033[35m')
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(6)
        original = record.levelname
        handler.emit(record)
        assert record.levelname == original

    def test_custom_color_override_levelname_immutable(self):
        """UT-CSH-020: custom color override does not mutate record.levelname."""
        stream = io.StringIO()
        handler = ColorStreamHandler(
            stream=stream,
            color_enabled=True,
            color_overrides={'ERR': '35'},
        )
        handler.setFormatter(logging.Formatter('%(levelname)s'))
        record = _make_record(logging.ERROR)
        original = record.levelname
        handler.emit(record)
        assert record.levelname == original


class TestLevelnameNonLeakage:
    """UT-LN: ANSI codes and abbreviations must not leak via shared LogRecord instances."""

    def test_ansi_does_not_leak_to_plain_handler(self):
        """UT-LN-001: plain handler sharing the same record sees no ANSI from colour handler."""
        colour_stream = io.StringIO()
        plain_stream = io.StringIO()

        colour_handler = ColorStreamHandler(stream=colour_stream, color_enabled=True)
        colour_handler.setFormatter(logging.Formatter('%(levelname)s'))

        plain_handler = logging.StreamHandler(plain_stream)
        plain_handler.setFormatter(logging.Formatter('%(levelname)s'))

        record = _make_record(logging.ERROR)
        colour_handler.emit(record)
        plain_handler.emit(record)

        assert '\033[' in colour_stream.getvalue()
        assert '\033[' not in plain_stream.getvalue()

    def test_ansi_does_not_leak_to_dsafe_formatter_handler(self):
        """UT-LN-002: DSafeFormatter handler sharing same record sees no ANSI from colour handler."""
        colour_stream = io.StringIO()
        dsafe_stream = io.StringIO()

        colour_handler = ColorStreamHandler(stream=colour_stream, color_enabled=True)
        colour_handler.setFormatter(logging.Formatter('%(levelname)s'))

        dsafe_handler = logging.StreamHandler(dsafe_stream)
        dsafe_handler.setFormatter(DSafeFormatter(fmt='%(levelname)s %(message)s'))

        record = _make_record(logging.ERROR)
        colour_handler.emit(record)
        dsafe_handler.emit(record)

        assert '\033[31m' in colour_stream.getvalue()
        assert '\033[31m' not in dsafe_stream.getvalue()
        assert 'ERR' in dsafe_stream.getvalue()

    def test_dsafe_abbreviation_does_not_leak_to_plain_handler(self):
        """UT-LN-003: plain handler sharing same record sees original levelname after DSafeFormatter."""
        dsafe_stream = io.StringIO()
        plain_stream = io.StringIO()

        dsafe_handler = logging.StreamHandler(dsafe_stream)
        dsafe_handler.setFormatter(DSafeFormatter(fmt='%(levelname)s %(message)s'))

        plain_handler = logging.StreamHandler(plain_stream)
        plain_handler.setFormatter(logging.Formatter('%(levelname)s'))

        record = _make_record(logging.WARNING)
        dsafe_handler.emit(record)
        plain_handler.emit(record)

        assert dsafe_stream.getvalue().split()[0] == 'WAR'
        assert plain_stream.getvalue().strip() == 'WARNING'

    def test_same_record_multiple_colour_emits_idempotent(self):
        """UT-LN-004: emitting the same record through colour handler multiple times is idempotent."""
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(logging.Formatter('%(levelname)s'))

        record = _make_record(logging.INFO)
        original_levelname = record.levelname

        handler.emit(record)
        handler.emit(record)

        assert record.levelname == original_levelname
        assert stream.getvalue().count('\033[32mINF\033[0m') == 2


class TestConsoleDecoratingFormatter:
    """Metadata decoration for D-SafeLogger-owned console text output."""

    def test_timestamp_source_and_context_are_decorated(self):
        formatter = ConsoleDecoratingFormatter()
        record = _make_record(logging.INFO)
        record._ds_context = {'request_id': 'abc-123'}

        output = formatter.format(record)

        assert output.startswith('\033[2m')
        assert '\033[0m [INF]\033[2m[test.py:1:None]\033[0m ' in output
        assert output.endswith('test message\033[2;36m [request_id:abc-123]\033[0m')
        assert record.levelname == 'INFO'

    def test_message_remains_plain_for_error(self):
        formatter = ConsoleDecoratingFormatter()
        record = _make_record(logging.ERROR)
        record.msg = 'ERROR message stays plain [not:context]'

        output = formatter.format(record)
        message = output.rsplit('\033[0m ', 1)[1]

        assert message == 'ERROR message stays plain [not:context]'
        assert '\033[' not in message

    def test_level_color_reset_does_not_break_metadata_decoration(self):
        stream = io.StringIO()
        handler = ColorStreamHandler(stream=stream, color_enabled=True)
        handler.setFormatter(ConsoleDecoratingFormatter())

        handler.emit(_make_record(logging.INFO))
        output = stream.getvalue()

        assert output.startswith('\033[2m')
        assert '[\033[32mINF\033[0m]' in output
        assert ']\033[2m[test.py:1:None]\033[0m test message' in output


class TestConsoleColorPipelineSelection:
    def test_color_enabled_default_console_uses_metadata_decoration(self, tmp_path, clean_env, monkeypatch, capsys):
        monkeypatch.setenv('D_LOG_COLOR', '1')
        ConfigureLogger(log_path=str(tmp_path), pg_name='ColorMeta')

        GetLogger(__name__).info('pipeline metadata color')
        _shutdown()

        output = capsys.readouterr().err
        assert output.startswith('\033[2m')
        assert '[\033[32mINF\033[0m]' in output
        assert '\033[2m[test_color.py:' in output
        assert output.rstrip().endswith('pipeline metadata color')

    def test_color_disabled_default_console_has_no_metadata_decoration(self, tmp_path, clean_env, monkeypatch, capsys):
        monkeypatch.setenv('D_LOG_COLOR', '0')
        ConfigureLogger(log_path=str(tmp_path), pg_name='NoColorMeta')

        GetLogger(__name__).info('plain console')
        _shutdown()

        output = capsys.readouterr().err
        assert '\033[' not in output
        assert 'plain console' in output

    def test_file_output_stays_ansi_free_when_console_is_colored(self, tmp_path, clean_env, monkeypatch, capsys):
        monkeypatch.setenv('D_LOG_COLOR', '1')
        ConfigureLogger(log_path=str(tmp_path), pg_name='FilePlain')

        GetLogger(__name__).error('file stays plain')
        _shutdown()
        capsys.readouterr()

        output = (tmp_path / 'FilePlain.log').read_text(encoding='utf-8')
        assert '\033[' not in output
        assert '[ERR]' in output
        assert 'file stays plain' in output

    def test_structured_console_and_file_stay_ansi_free(self, tmp_path, clean_env, monkeypatch, capsys):
        monkeypatch.setenv('D_LOG_COLOR', '1')
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='JsonPlain',
            structured=True,
        )

        GetLogger(__name__).info('json stays plain')
        _shutdown()

        console_output = capsys.readouterr().err
        file_output = (tmp_path / 'JsonPlain.log').read_text(encoding='utf-8')

        assert '\033[' not in console_output
        assert '\033[' not in file_output
        assert json.loads(console_output)['level'] == 'INF'
        assert json.loads(file_output)['level'] == 'INF'

    def test_custom_console_formatter_is_not_metadata_decorated(self, tmp_path, clean_env, monkeypatch, capsys):
        monkeypatch.setenv('D_LOG_COLOR', '1')
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='CustomConsole',
            console_fmt='%(levelname)s:%(message)s',
        )

        GetLogger(__name__).warning('custom format')
        _shutdown()

        output = capsys.readouterr().err
        assert '\033[2m' not in output
        assert '\033[33mWAR\033[0m:custom format' in output
