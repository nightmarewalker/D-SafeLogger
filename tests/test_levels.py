"""Tests for dsafelogger._levels (RegisterLevel and query functions)."""

from __future__ import annotations

import logging
import pytest
from dsafelogger._levels import (
    register_custom_level as RegisterLevel,
    get_all_level_map,
    get_all_color_map,
    get_valid_level_names,
    get_valid_abbreviations,
    install_convenience_methods,
    _custom_levels,
)


class TestRegisterLevel:
    """Tests for RegisterLevel()."""

    def test_basic_registration(self):
        RegisterLevel('TRACE', 5, 'TRC')
        assert 'TRACE' in _custom_levels
        assert _custom_levels['TRACE'] == (5, 'TRC', '')

    def test_with_color(self):
        RegisterLevel('TRACE', 5, 'TRC', '\033[90m')
        assert _custom_levels['TRACE'][2] == '\033[90m'

    def test_name_normalized_to_upper(self):
        RegisterLevel('trace', 5, 'TRC')
        assert 'TRACE' in _custom_levels

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match='must not be empty'):
            RegisterLevel('', 5, 'TRC')

    def test_negative_value_raises(self):
        with pytest.raises(ValueError, match='must be >= 0'):
            RegisterLevel('TRACE', -1, 'TRC')

    def test_builtin_value_raises(self):
        with pytest.raises(ValueError, match='Cannot override built-in'):
            RegisterLevel('CUSTOM', 10, 'CST')  # 10 = DEBUG

    def test_builtin_name_raises(self):
        with pytest.raises(ValueError, match='Cannot override built-in'):
            RegisterLevel('DEBUG', 5, 'DBX')

    def test_abbreviation_not_3_chars_raises(self):
        with pytest.raises(ValueError, match='exactly 3 characters'):
            RegisterLevel('TRACE', 5, 'TR')

    def test_builtin_abbreviation_raises(self):
        with pytest.raises(ValueError, match='conflicts with built-in'):
            RegisterLevel('TRACE', 5, 'DBG')

    def test_duplicate_value_raises(self):
        RegisterLevel('TRACE', 5, 'TRC')
        with pytest.raises(ValueError, match='already registered'):
            RegisterLevel('VERBOSE', 5, 'VRB')

    def test_duplicate_abbreviation_raises(self):
        RegisterLevel('TRACE', 5, 'TRC')
        with pytest.raises(ValueError, match='already registered'):
            RegisterLevel('VERBOSE', 7, 'TRC')

    def test_duplicate_name_raises(self):
        RegisterLevel('TRACE', 5, 'TRC')
        with pytest.raises(ValueError, match='already registered'):
            RegisterLevel('TRACE', 7, 'TR2')

    def test_same_definition_reregister_is_noop(self):
        RegisterLevel('TRACE', 5, 'TRC', '\033[90m')
        RegisterLevel('TRACE', 5, 'TRC', '\033[90m')
        assert _custom_levels['TRACE'] == (5, 'TRC', '\033[90m')

    def test_registers_with_standard_logging(self):
        RegisterLevel('TRACE', 5, 'TRC')
        assert logging.getLevelName(5) == 'TRACE'


class TestQueryFunctions:
    """Tests for get_all_* functions."""

    def test_level_map_builtins(self):
        m = get_all_level_map()
        assert m['DEBUG'] == 'DBG'
        assert m['INFO'] == 'INF'
        assert m['WARNING'] == 'WAR'
        assert m['ERROR'] == 'ERR'
        assert m['CRITICAL'] == 'CRI'

    def test_level_map_with_custom(self):
        RegisterLevel('TRACE', 5, 'TRC')
        m = get_all_level_map()
        assert m['TRACE'] == 'TRC'

    def test_color_map_builtins(self):
        m = get_all_color_map()
        assert m['DBG'] == '\033[36m'
        assert m['CRI'] == '\033[1;31m'

    def test_color_map_with_overrides(self):
        m = get_all_color_map(overrides={'ERR': '91'})
        assert m['ERR'] == '\033[91m'

    def test_color_map_disable_with_empty(self):
        m = get_all_color_map(overrides={'DBG': ''})
        assert 'DBG' not in m

    def test_valid_level_names(self):
        names = get_valid_level_names()
        assert 'DEBUG' in names
        assert 'INFO' in names
        RegisterLevel('TRACE', 5, 'TRC')
        names = get_valid_level_names()
        assert 'TRACE' in names

    def test_valid_abbreviations(self):
        abbrs = get_valid_abbreviations()
        assert 'DBG' in abbrs
        RegisterLevel('TRACE', 5, 'TRC')
        abbrs = get_valid_abbreviations()
        assert 'TRC' in abbrs


class TestInstallConvenienceMethods:
    """Tests for install_convenience_methods()."""

    def test_adds_method(self):
        RegisterLevel('TRACE', 5, 'TRC')

        class FakeLogger:
            pass

        install_convenience_methods(FakeLogger)
        assert hasattr(FakeLogger, 'trace')
