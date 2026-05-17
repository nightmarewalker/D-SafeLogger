"""Tests for dsafelogger._ini_loader (IniLoader and DictLoader)."""

from __future__ import annotations

import sys
import pytest
from dsafelogger._ini_loader import IniLoader, DictLoader


class TestIniLoaderLoad:
    """UT-INI-F: File-level Fail-Fast."""

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            IniLoader.load('nonexistent.ini')

    def test_valid_ini(self, tmp_path):
        ini = tmp_path / 'valid.ini'
        ini.write_text('[global]\ndefault_level = DEBUG\n', encoding='utf-8')
        g, m = IniLoader.load(str(ini))
        assert g['default_level'] == 'DEBUG'
        assert m == {}

    def test_empty_ini(self, tmp_path):
        ini = tmp_path / 'empty.ini'
        ini.write_text('', encoding='utf-8')
        g, m = IniLoader.load(str(ini))
        assert g == {}
        assert m == {}


class TestIniLoaderGlobal:
    """UT-INI-G: [global] section parsing."""

    def _load(self, tmp_path, content):
        ini = tmp_path / 'test.ini'
        ini.write_text(content, encoding='utf-8')
        return IniLoader.load(str(ini))

    def test_str_key_default_level(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\ndefault_level = DEBUG\n')
        assert g['default_level'] == 'DEBUG'

    def test_int_key_backup_count(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nbackup_count = 30\n')
        assert g['backup_count'] == 30

    def test_bool_key_true(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nis_async = true\n')
        assert g['is_async'] is True

    def test_bool_key_false(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nis_async = false\n')
        assert g['is_async'] is False

    def test_bool_key_case_insensitive(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nstructured = TRUE\n')
        assert g['structured'] is True

    def test_optional_int_value(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nmax_count = 5\n')
        assert g['max_count'] == 5

    def test_optional_int_empty(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nmax_count =\n')
        assert g['max_count'] is None

    def test_csv_key_sens_kws(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nsens_kws = my_secret, api_token\n')
        assert g['sens_kws'] == ['my_secret', 'api_token']

    def test_csv_key_empty(self, tmp_path):
        g, _ = self._load(tmp_path, '[global]\nsens_kws =\n')
        assert g['sens_kws'] == []

    def test_int_key_invalid(self, tmp_path):
        with pytest.raises(ValueError, match='expected int'):
            self._load(tmp_path, '[global]\nbackup_count = abc\n')

    def test_bool_key_invalid(self, tmp_path):
        with pytest.raises(ValueError, match='expected bool'):
            self._load(tmp_path, '[global]\nis_async = maybe\n')

    def test_diagnose_ignored(self, tmp_path, capsys):
        g, _ = self._load(tmp_path, '[global]\ndiagnose = true\n')
        assert 'diagnose' not in g
        # No warning for sanctuary key
        captured = capsys.readouterr()
        assert 'unknown key' not in captured.err

    def test_unknown_key_warning(self, tmp_path, capsys):
        g, _ = self._load(tmp_path, '[global]\nunknown_key = value\n')
        assert 'unknown_key' not in g
        captured = capsys.readouterr()
        assert 'unknown key' in captured.err


class TestIniLoaderModule:
    """UT-INI-M: Module section parsing."""

    def _load(self, tmp_path, content):
        ini = tmp_path / 'test.ini'
        ini.write_text(content, encoding='utf-8')
        return IniLoader.load(str(ini))

    def test_level_only(self, tmp_path):
        _, m = self._load(tmp_path, '[dsafelogger:mymod]\nlevel = DEBUG\n')
        assert m['mymod']['level'] == 'DEBUG'

    def test_level_and_path(self, tmp_path):
        _, m = self._load(tmp_path, '[dsafelogger:mymod]\nlevel = ERROR\npath = app.log\n')
        assert m['mymod']['path'] == 'app.log'

    def test_level_required(self, tmp_path):
        with pytest.raises(ValueError, match="requires 'level'"):
            self._load(tmp_path, '[dsafelogger:mymod]\npath = app.log\n')

    def test_empty_module_name(self, tmp_path):
        with pytest.raises(ValueError, match='empty module name'):
            self._load(tmp_path, '[dsafelogger:]\nlevel = DEBUG\n')

    def test_routing_without_path_warning(self, tmp_path, capsys):
        _, m = self._load(tmp_path, '[dsafelogger:mymod]\nlevel = DEBUG\nrouting_mode = daily\n')
        assert 'routing_mode' not in m['mymod']
        captured = capsys.readouterr()
        assert "requires 'path'" in captured.err


class TestDictLoader:
    """UT-DL: DictLoader tests."""

    def test_basic_global(self):
        g, m = DictLoader.load({'global': {'default_level': 'DEBUG'}})
        assert g['default_level'] == 'DEBUG'

    def test_type_error_non_dict(self):
        with pytest.raises(TypeError, match='must be dict'):
            DictLoader.load('not_a_dict')  # type: ignore

    def test_type_error_section_non_dict(self):
        with pytest.raises(TypeError, match='must be dict'):
            DictLoader.load({'global': 'not_a_dict'})  # type: ignore

    def test_type_error_key_non_str(self):
        with pytest.raises(TypeError, match='must be str'):
            DictLoader.load({'global': {123: 'value'}})  # type: ignore

    def test_type_error_value_non_str(self):
        with pytest.raises(TypeError, match='must be str'):
            DictLoader.load({'global': {'key': 123}})  # type: ignore

    def test_empty_dict(self):
        g, m = DictLoader.load({})
        assert g == {}
        assert m == {}

    def test_module_section(self):
        _, m = DictLoader.load({'dsafelogger:mymod': {'level': 'DEBUG'}})
        assert m['mymod']['level'] == 'DEBUG'

    def test_module_level_required(self):
        with pytest.raises(ValueError, match="requires 'level'"):
            DictLoader.load({'dsafelogger:mymod': {'path': 'app.log'}})

    def test_diagnose_ignored(self, capsys):
        g, _ = DictLoader.load({'global': {'diagnose': 'true'}})
        assert 'diagnose' not in g

    def test_int_conversion(self):
        g, _ = DictLoader.load({'global': {'backup_count': '30'}})
        assert g['backup_count'] == 30

    def test_bool_conversion(self):
        g, _ = DictLoader.load({'global': {'is_async': 'true'}})
        assert g['is_async'] is True
