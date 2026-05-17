"""Tests for dsafelogger._env_parser.EnvParser."""

from __future__ import annotations

import pytest
from dsafelogger._env_parser import EnvParser


class TestParseGlobalLevel:
    """UT-EP-GL: {prefix}_LEVEL parsing."""

    def test_valid_level(self):
        assert EnvParser.parse_global_level('INFO') == 'INFO'

    def test_lowercase_input(self):
        assert EnvParser.parse_global_level('debug') == 'DEBUG'

    def test_whitespace_trimmed(self):
        assert EnvParser.parse_global_level('  WARNING  ') == 'WARNING'

    def test_empty_string(self):
        assert EnvParser.parse_global_level('') is None

    def test_whitespace_only(self):
        assert EnvParser.parse_global_level('  ') is None

    def test_comma_raises_valueerror(self):
        with pytest.raises(ValueError, match='comma-separated'):
            EnvParser.parse_global_level('INFO,mymod:DEBUG')

    def test_comma_only(self):
        with pytest.raises(ValueError, match='comma-separated'):
            EnvParser.parse_global_level(',')

    def test_trailing_comma(self):
        with pytest.raises(ValueError, match='comma-separated'):
            EnvParser.parse_global_level('INFO,')


class TestParseModulesEnv:
    """UT-EP-MO: {prefix}_MODULES parsing."""

    def test_level_only(self):
        result = EnvParser.parse_modules_env('mymod:DEBUG')
        assert result == {'mymod': {'level': 'DEBUG', 'path': None}}

    def test_level_and_path(self):
        result = EnvParser.parse_modules_env('mymod:DEBUG:app.log')
        assert result == {'mymod': {'level': 'DEBUG', 'path': 'app.log'}}

    def test_multiple_modules(self):
        result = EnvParser.parse_modules_env('a:DEBUG,b:ERROR:b.log')
        assert len(result) == 2
        assert result['a'] == {'level': 'DEBUG', 'path': None}
        assert result['b'] == {'level': 'ERROR', 'path': 'b.log'}

    def test_case_conversion(self):
        result = EnvParser.parse_modules_env('mymod:debug')
        assert result['mymod']['level'] == 'DEBUG'

    def test_windows_absolute_path(self):
        result = EnvParser.parse_modules_env(r'mymod:DEBUG:C:\logs\app.log')
        assert result['mymod']['path'] == r'C:\logs\app.log'

    def test_empty_string(self):
        assert EnvParser.parse_modules_env('') == {}

    def test_whitespace_only(self):
        assert EnvParser.parse_modules_env('  ') == {}

    def test_dotted_module_name(self):
        result = EnvParser.parse_modules_env('myapp.db:DEBUG')
        assert 'myapp.db' in result


class TestParseBoolEnv:
    """UT-EP-B: Boolean env var parsing."""

    @pytest.mark.parametrize('value,expected', [
        ('1', True), ('true', True), ('TRUE', True),
        ('0', False), ('false', False), ('FALSE', False),
    ])
    def test_valid_values(self, value, expected):
        assert EnvParser.parse_bool_env(value) is expected

    def test_none(self):
        assert EnvParser.parse_bool_env(None) is None

    def test_invalid_value(self):
        assert EnvParser.parse_bool_env('yes') is None


class TestParseConfigPath:
    """UT-EP-CP: {prefix}_CONFIG parsing."""

    def test_valid_path(self):
        assert EnvParser.parse_config_path('/etc/myapp/logging.ini') == '/etc/myapp/logging.ini'

    def test_whitespace_trimmed(self):
        assert EnvParser.parse_config_path('  ./config.ini  ') == './config.ini'

    def test_empty_string(self):
        assert EnvParser.parse_config_path('') is None

    def test_none(self):
        assert EnvParser.parse_config_path(None) is None

    def test_whitespace_only(self):
        assert EnvParser.parse_config_path('  ') is None


class TestResolveEnvNames:
    """UT-EP-RN: env name derivation."""

    def test_default_prefix(self):
        names = EnvParser.resolve_env_names('D_LOG')
        assert names['level'] == 'D_LOG_LEVEL'
        assert names['modules'] == 'D_LOG_MODULES'
        assert names['hash'] == 'D_LOG_HASH'
        assert names['manifest'] == 'D_LOG_MANIFEST'

    def test_custom_prefix(self):
        names = EnvParser.resolve_env_names('MY_APP')
        assert names['level'] == 'MY_APP_LEVEL'


class TestParseHashEnv:
    """UT-EP-HE: {prefix}_HASH parsing."""

    @pytest.mark.parametrize('value,expected', [
        ('1', True), ('true', True), ('TRUE', True),
        ('0', False), ('false', False),
    ])
    def test_valid_values(self, value, expected):
        assert EnvParser.parse_hash_env(value) is expected

    def test_none(self):
        assert EnvParser.parse_hash_env(None) is None

    def test_invalid_value(self):
        assert EnvParser.parse_hash_env('yes') is None


class TestParseManifestEnv:
    """UT-EP-ME: {prefix}_MANIFEST parsing."""

    def test_valid_path(self):
        assert EnvParser.parse_manifest_env('/var/log/manifest.txt') == '/var/log/manifest.txt'

    def test_empty_string(self):
        assert EnvParser.parse_manifest_env('') is None

    def test_none(self):
        assert EnvParser.parse_manifest_env(None) is None
