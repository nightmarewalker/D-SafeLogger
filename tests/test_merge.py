"""Tests for 3-layer merge logic."""

from __future__ import annotations

import pytest
from dsafelogger import _merge_module_configs


class TestMergeModuleConfigs:
    """UT-MG-M: Module config merge tests."""

    def test_ini_only(self):
        ini = {'mymod': {'level': 'DEBUG', 'path': 'app.log', 'routing_mode': 'daily'}}
        env = {}
        result = _merge_module_configs(ini, env)
        assert result == ini

    def test_env_only(self):
        ini = {}
        env = {'mymod': {'level': 'DEBUG', 'path': None}}
        result = _merge_module_configs(ini, env)
        assert result['mymod'] == {'level': 'DEBUG', 'path': None}

    def test_level_override(self):
        ini = {'mymod': {'level': 'DEBUG', 'path': 'app.log', 'routing_mode': 'daily'}}
        env = {'mymod': {'level': 'ERROR', 'path': None}}
        result = _merge_module_configs(ini, env)
        assert result['mymod']['level'] == 'ERROR'
        assert result['mymod']['path'] == 'app.log'  # Maintained from INI
        assert result['mymod']['routing_mode'] == 'daily'  # Maintained

    def test_path_override(self):
        ini = {'mymod': {'level': 'DEBUG', 'path': 'old.log'}}
        env = {'mymod': {'level': 'ERROR', 'path': 'new.log'}}
        result = _merge_module_configs(ini, env)
        assert result['mymod']['level'] == 'ERROR'
        assert result['mymod']['path'] == 'new.log'

    def test_env_path_none_preserves_ini(self):
        ini = {'mymod': {'level': 'DEBUG', 'path': 'app.log', 'routing_mode': 'size', 'max_bytes': 1024}}
        env = {'mymod': {'level': 'ERROR', 'path': None}}
        result = _merge_module_configs(ini, env)
        assert result['mymod']['path'] == 'app.log'
        assert result['mymod']['routing_mode'] == 'size'
        assert result['mymod']['max_bytes'] == 1024

    def test_mixed_merge(self):
        ini = {'a': {'level': 'DEBUG'}, 'b': {'level': 'INFO'}}
        env = {'b': {'level': 'ERROR', 'path': None}, 'c': {'level': 'WARNING', 'path': None}}
        result = _merge_module_configs(ini, env)
        assert result['a']['level'] == 'DEBUG'  # INI only
        assert result['b']['level'] == 'ERROR'  # Merged
        assert result['c']['level'] == 'WARNING'  # Env only

    def test_both_empty(self):
        result = _merge_module_configs({}, {})
        assert result == {}
