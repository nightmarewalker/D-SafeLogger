"""Tests for ConfigureLogger + INI/Dict/EnvVar integration (3-layer pipeline)."""

from __future__ import annotations

import logging
import os

import pytest
import dsafelogger
from dsafelogger import ConfigureLogger, GetLogger


class TestIniIntegration:
    """UT-CL-INI: INI file integration tests."""

    def test_config_file_arg(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[global]\ndefault_level = DEBUG\n',
            encoding='utf-8',
        )
        ConfigureLogger(config_file=str(ini), log_path=str(tmp_path), console_out=False)
        assert logging.getLogger().level == logging.DEBUG

    def test_env_config_overrides_arg(self, tmp_path, clean_env):
        ini_a = tmp_path / 'a.ini'
        ini_a.write_text('[global]\ndefault_level = DEBUG\n', encoding='utf-8')
        ini_b = tmp_path / 'b.ini'
        ini_b.write_text('[global]\ndefault_level = WARNING\n', encoding='utf-8')

        os.environ['D_LOG_CONFIG'] = str(ini_b)
        ConfigureLogger(config_file=str(ini_a), log_path=str(tmp_path), console_out=False)
        assert logging.getLogger().level == logging.WARNING

    def test_both_none_layer2_skip(self, tmp_path, clean_env):
        ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert logging.getLogger().level == logging.INFO  # Default

    def test_ini_overrides_arg_level(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text('[global]\ndefault_level = WARNING\n', encoding='utf-8')
        ConfigureLogger(
            config_file=str(ini),
            default_level='DEBUG',
            log_path=str(tmp_path),
            console_out=False,
        )
        assert logging.getLogger().level == logging.WARNING

    def test_env_overrides_ini_level(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text('[global]\ndefault_level = INFO\n', encoding='utf-8')
        os.environ['D_LOG_LEVEL'] = 'ERROR'
        ConfigureLogger(
            config_file=str(ini),
            default_level='DEBUG',
            log_path=str(tmp_path),
            console_out=False,
        )
        assert logging.getLogger().level == logging.ERROR

    def test_ini_diagnose_ignored(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text('[global]\ndiagnose = true\n', encoding='utf-8')
        ConfigureLogger(config_file=str(ini), log_path=str(tmp_path), console_out=False)
        assert dsafelogger._diagnose_enabled is False

    def test_ini_module_section(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[global]\ndefault_level = INFO\n\n'
            '[dsafelogger:mymod]\nlevel = DEBUG\n',
            encoding='utf-8',
        )
        ConfigureLogger(config_file=str(ini), log_path=str(tmp_path), console_out=False)
        mod_logger = logging.getLogger('mymod')
        assert mod_logger.level == logging.DEBUG
        assert mod_logger.propagate is True

        mod_logger.debug('ini_level_only_visible')
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert 'ini_level_only_visible' in (tmp_path / 'Default.log').read_text(encoding='utf-8')

    def test_ini_global_size_mode_requires_positive_max_bytes(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[global]\nrouting_mode = size\nmax_bytes = 0\n',
            encoding='utf-8',
        )
        with pytest.raises(ValueError, match='max_bytes > 0'):
            ConfigureLogger(config_file=str(ini), log_path=str(tmp_path), console_out=False)

    def test_ini_module_size_mode_requires_positive_max_bytes(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[global]\ndefault_level = INFO\n\n'
            '[dsafelogger:audit]\n'
            'level = INFO\n'
            'path = audit.log\n'
            'routing_mode = size\n'
            'max_bytes = 0\n',
            encoding='utf-8',
        )
        with pytest.raises(ValueError, match=r"module 'audit'.*max_bytes > 0"):
            ConfigureLogger(config_file=str(ini), log_path=str(tmp_path), console_out=False)


class TestDictIntegration:
    """UT-CL-DICT: Dict integration tests."""

    def test_config_dict_layer2(self, tmp_path, clean_env):
        ConfigureLogger(
            config_dict={'global': {'default_level': 'DEBUG'}},
            log_path=str(tmp_path),
            console_out=False,
        )
        assert logging.getLogger().level == logging.DEBUG

    def test_config_dict_module(self, tmp_path, clean_env):
        ConfigureLogger(
            config_dict={
                'global': {'default_level': 'INFO'},
                'dsafelogger:mymod': {'level': 'DEBUG'},
            },
            log_path=str(tmp_path),
            console_out=False,
        )
        mod_logger = logging.getLogger('mymod')
        assert mod_logger.level == logging.DEBUG
        assert mod_logger.propagate is True

        mod_logger.debug('dict_level_only_visible')
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert 'dict_level_only_visible' in (tmp_path / 'Default.log').read_text(encoding='utf-8')

    def test_env_config_overrides_dict(self, tmp_path, clean_env):
        ini = tmp_path / 'env.ini'
        ini.write_text('[global]\ndefault_level = ERROR\n', encoding='utf-8')
        os.environ['D_LOG_CONFIG'] = str(ini)

        ConfigureLogger(
            config_dict={'global': {'default_level': 'DEBUG'}},
            log_path=str(tmp_path),
            console_out=False,
        )
        assert logging.getLogger().level == logging.ERROR

    def test_config_file_and_dict_exclusive(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text('[global]\n', encoding='utf-8')
        with pytest.raises(ValueError, match='mutually exclusive'):
            ConfigureLogger(
                config_file=str(ini),
                config_dict={'global': {}},
                log_path=str(tmp_path),
            )

    def test_env_level_overrides_dict(self, tmp_path, clean_env):
        os.environ['D_LOG_LEVEL'] = 'WARNING'
        ConfigureLogger(
            config_dict={'global': {'default_level': 'DEBUG'}},
            log_path=str(tmp_path),
            console_out=False,
        )
        assert logging.getLogger().level == logging.WARNING

    def test_config_dict_count_mode_requires_positive_max_lines(self, tmp_path, clean_env):
        with pytest.raises(ValueError, match='max_lines > 0'):
            ConfigureLogger(
                config_dict={'global': {'routing_mode': 'count', 'max_lines': '0'}},
                log_path=str(tmp_path),
                console_out=False,
            )


class TestModulesEnvIntegration:
    """UT-CL-MOD: {prefix}_MODULES integration."""

    def test_env_module_level_override(self, tmp_path, clean_env):
        ini = tmp_path / 'test.ini'
        ini.write_text(
            '[dsafelogger:mymod]\nlevel = DEBUG\n',
            encoding='utf-8',
        )
        os.environ['D_LOG_MODULES'] = 'mymod:ERROR'
        ConfigureLogger(config_file=str(ini), log_path=str(tmp_path), console_out=False)
        mod_logger = logging.getLogger('mymod')
        assert mod_logger.level == logging.ERROR

    def test_env_adds_new_module(self, tmp_path, clean_env):
        os.environ['D_LOG_MODULES'] = 'newmod:DEBUG'
        ConfigureLogger(log_path=str(tmp_path), console_out=False, fmt='%(message)s')
        mod_logger = logging.getLogger('newmod')
        assert mod_logger.level == logging.DEBUG
        assert mod_logger.propagate is True

        mod_logger.debug('env_level_only_visible')
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert 'env_level_only_visible' in (tmp_path / 'Default.log').read_text(encoding='utf-8')

    def test_module_with_dedicated_path_does_not_propagate(self, tmp_path, clean_env):
        ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            config_dict={
                'dsafelogger:mymod': {
                    'level': 'DEBUG',
                    'path': 'mymod.log',
                },
            },
        )
        mod_logger = logging.getLogger('mymod')
        assert mod_logger.level == logging.DEBUG
        assert mod_logger.propagate is False
        assert mod_logger.handlers

        mod_logger.debug('dedicated_module_visible')
        for handler in [*logging.getLogger().handlers, *mod_logger.handlers]:
            handler.flush()

        assert 'dedicated_module_visible' in (tmp_path / 'mymod.log').read_text(encoding='utf-8')
        root_text = (tmp_path / 'Default.log').read_text(encoding='utf-8')
        assert 'dedicated_module_visible' not in root_text
