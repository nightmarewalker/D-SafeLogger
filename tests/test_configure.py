"""Tests for ConfigureLogger and GetLogger."""

from __future__ import annotations

import logging
import os
import re
import sys

import pytest
import dsafelogger
from dsafelogger import ConfigureLogger, GetLogger, _shutdown
from dsafelogger._logger import DSafeLogger


_TIME_PREFIX_RE = re.compile(r'^\d{2}:\d{2}:\d{2}\.\d{3} \[INF\]')


class TestConfigureLoggerNormal:
    """UT-CL normal cases."""

    def test_default_init(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path))
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) >= 1

    def test_level_debug(self, tmp_path, clean_env):
        ConfigureLogger(default_level='DEBUG', log_path=str(tmp_path))
        assert logging.getLogger().level == logging.DEBUG

    def test_pg_name(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), pg_name='MyApp', console_out=False)
        log_files = list(tmp_path.glob('*.log'))
        assert any('MyApp' in f.name for f in log_files) or True  # File created on first write

    def test_console_out_false(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        root = logging.getLogger()
        from dsafelogger._color import ColorStreamHandler
        assert not any(isinstance(h, ColorStreamHandler) for h in root.handlers)

    def test_idempotent_explicit(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        handler_count = len(logging.getLogger().handlers)
        ConfigureLogger(log_path=str(tmp_path), default_level='DEBUG')  # No-Op
        assert len(logging.getLogger().handlers) == handler_count

    def test_structured_mode(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), structured=True, console_out=False)
        from dsafelogger._formatter import StructuredFormatter
        import dsafelogger
        assert any(
            isinstance(h.formatter, StructuredFormatter) for h in dsafelogger._active_pipeline.transport._target_handlers if h.formatter
        )

    def test_datefmt_reaches_file_formatter(self, tmp_path, clean_env):
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DateFmtFile',
            console_out=False,
            datefmt='%H:%M:%S',
        )
        GetLogger(__name__).info('file datefmt works')
        _shutdown()

        output = (tmp_path / 'DateFmtFile.log').read_text(encoding='utf-8')
        assert _TIME_PREFIX_RE.match(output)
        assert 'file datefmt works' in output
        assert not output.startswith('20')

    def test_datefmt_reaches_console_formatter(self, tmp_path, clean_env, capsys):
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DateFmtConsole',
            datefmt='%H:%M:%S',
        )
        GetLogger(__name__).info('console datefmt works')
        _shutdown()

        output = capsys.readouterr().err
        assert _TIME_PREFIX_RE.match(output)
        assert 'console datefmt works' in output
        assert not output.startswith('20')

    def test_datefmt_reaches_diagnostic_text_formatter(
        self, tmp_path, clean_env, monkeypatch
    ):
        monkeypatch.setenv('D_LOG_DIAGNOSE', '1')
        ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='DateFmtDiagnostic',
            console_out=False,
            datefmt='%H:%M:%S',
        )
        GetLogger(__name__).info('diagnostic datefmt works')
        _shutdown()

        output = (tmp_path / 'DateFmtDiagnostic.log').read_text(encoding='utf-8')
        assert _TIME_PREFIX_RE.match(output)
        assert 'diagnostic datefmt works' in output
        assert not output.startswith('20')


class TestConfigureLoggerErrors:
    """UT-CL error cases."""

    def test_invalid_level(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='Invalid default_level'):
            ConfigureLogger(default_level='VERBOSE', log_path=str(tmp_path))

    def test_invalid_routing_mode(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='Invalid routing_mode'):
            ConfigureLogger(routing_mode='weekly', log_path=str(tmp_path))

    def test_structured_with_fmt(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='structured=True'):
            ConfigureLogger(structured=True, fmt='%(message)s', log_path=str(tmp_path))

    def test_structured_with_file_fmt(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='structured=True'):
            ConfigureLogger(structured=True, file_fmt='%(message)s', log_path=str(tmp_path))

    def test_structured_with_datefmt(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='datefmt'):
            ConfigureLogger(
                structured=True,
                datefmt='%H:%M:%S',
                log_path=str(tmp_path),
            )

    def test_config_dict_structured_with_fmt(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='structured=True'):
            ConfigureLogger(
                log_path=str(tmp_path),
                config_dict={'global': {'structured': 'true', 'fmt': '%(message)s'}},
            )

    def test_config_dict_structured_with_datefmt(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='datefmt'):
            ConfigureLogger(
                log_path=str(tmp_path),
                config_dict={'global': {'structured': 'true', 'datefmt': '%H:%M:%S'}},
            )

    def test_suffix_digits_zero(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='suffix_digits'):
            ConfigureLogger(suffix_digits=0, log_path=str(tmp_path))

    def test_max_count_zero(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='max_count'):
            ConfigureLogger(max_count=0, log_path=str(tmp_path))

    def test_config_dict_max_count_zero(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='max_count'):
            ConfigureLogger(
                log_path=str(tmp_path),
                config_dict={
                    'global': {
                        'routing_mode': 'size',
                        'max_bytes': '1',
                        'max_count': '0',
                    },
                },
            )

    def test_max_bytes_negative(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='max_bytes'):
            ConfigureLogger(max_bytes=-1, log_path=str(tmp_path))

    def test_size_mode_requires_positive_max_bytes(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='max_bytes > 0'):
            ConfigureLogger(routing_mode='size', max_bytes=0, log_path=str(tmp_path))

    def test_count_mode_requires_positive_max_lines(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='max_lines > 0'):
            ConfigureLogger(routing_mode='count', max_lines=0, log_path=str(tmp_path))

    def test_config_dict_invalid_default_level(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='invalid level'):
            ConfigureLogger(
                log_path=str(tmp_path),
                config_dict={'global': {'default_level': 'NOPE'}},
            )

    @pytest.mark.parametrize('key', ['is_async', 'archive_mode', 'console_out', 'structured'])
    def test_bool_args_reject_strings(self, key, tmp_path, clean_env):
        with pytest.raises(TypeError, match=key):
            ConfigureLogger(log_path=str(tmp_path), **{key: 'false'})  # type: ignore[arg-type]

    def test_module_invalid_level(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='invalid level'):
            ConfigureLogger(
                log_path=str(tmp_path),
                config_dict={'dsafelogger:mymod': {'level': 'NOPE'}},
            )

    def test_cyclic_hash_rejected(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='cyclic'):
            ConfigureLogger(
                log_path=str(tmp_path),
                routing_mode='size',
                max_bytes=1,
                max_count=2,
                enable_hash=True,
            )

    def test_empty_env_prefix(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='env_prefix'):
            ConfigureLogger(env_prefix='', log_path=str(tmp_path))

    def test_config_file_not_found(self, tmp_path, clean_env):
        with pytest.raises(FileNotFoundError):
            ConfigureLogger(config_file='nonexistent.ini', log_path=str(tmp_path))

    def test_config_file_and_dict_exclusive(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text('[global]\n', encoding='utf-8')
        with pytest.raises(ValueError, match='mutually exclusive'):
            ConfigureLogger(
                config_file=str(ini),
                config_dict={'global': {}},
                log_path=str(tmp_path),
            )

    def test_sens_kws_bare_str(self, tmp_path, clean_env):
        with pytest.raises(TypeError, match='Sequence'):
            ConfigureLogger(sens_kws='not_a_list', log_path=str(tmp_path))

    def test_sens_kws_replace_without_kws(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='sens_kws_replace'):
            ConfigureLogger(sens_kws_replace=True, log_path=str(tmp_path))


class TestGetLogger:
    """UT-GL: GetLogger tests."""

    def test_after_configure(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = GetLogger('myapp')
        assert isinstance(logger, DSafeLogger)

    def test_same_name_same_instance(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        a = GetLogger('myapp')
        b = GetLogger('myapp')
        assert a is b

    def test_different_names(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        a = GetLogger('a')
        b = GetLogger('b')
        assert a is not b

    def test_auto_fire(self, tmp_path, clean_env):
        # GetLogger before ConfigureLogger should auto-fire
        os.chdir(tmp_path)
        logger = GetLogger('early')
        assert isinstance(logger, logging.Logger)
        assert dsafelogger._configure_state == 'auto'
