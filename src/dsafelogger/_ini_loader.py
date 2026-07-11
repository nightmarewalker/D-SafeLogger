"""INI file and dict config loaders for D-SafeLogger."""

from __future__ import annotations

import configparser
import re
import sys
from pathlib import Path


class IniLoader:
    """INI file loader with Fail-Fast validation and type conversion."""

    # ── Key categories ──
    MODULE_SECTION_PREFIX = 'dsafelogger:'
    COLOR_KEY_PREFIX = 'color_'

    # Keys that are silently ignored (sanctuary: diagnose)
    IGNORED_KEYS = frozenset({'diagnose'})

    # Valid global keys
    VALID_GLOBAL_KEYS = frozenset({
        'default_level', 'log_path', 'pg_name', 'env_prefix',
        'is_async', 'backup_count', 'archive_mode',
        'routing_mode', 'interval',
        'max_bytes', 'max_lines', 'max_count', 'suffix_digits',
        'console_out', 'structured', 'fmt', 'file_fmt', 'console_fmt', 'datefmt',
        'enable_hash', 'manifest_path',
        'sens_kws', 'sens_kws_replace',
    })

    # Valid module keys
    VALID_MODULE_KEYS = frozenset({
        'level', 'path',
        'routing_mode', 'interval',
        'max_bytes', 'max_lines', 'max_count', 'suffix_digits',
        'backup_count', 'archive_mode',
    })

    # Module keys that require 'path' to be set
    MODULE_ROUTING_KEYS = frozenset({
        'routing_mode', 'interval',
        'max_bytes', 'max_lines', 'max_count', 'suffix_digits',
        'backup_count', 'archive_mode',
    })

    # Type categories
    BOOL_KEYS = frozenset({
        'is_async', 'structured',
        'archive_mode', 'enable_hash', 'sens_kws_replace',
    })
    INT_KEYS = frozenset({
        'backup_count', 'max_bytes', 'max_lines', 'suffix_digits',
    })
    OPTIONAL_INT_KEYS = frozenset({
        'max_count',
    })
    CSV_KEYS = frozenset({
        'sens_kws',
    })
    STR_KEYS = frozenset({
        'default_level', 'log_path', 'pg_name', 'env_prefix',
        'routing_mode', 'fmt', 'file_fmt', 'console_fmt', 'datefmt', 'interval',
        'manifest_path',
    })

    @classmethod
    def load(cls, config_path: str) -> tuple[dict, dict[str, dict]]:
        """Load INI file and return (global_config, module_configs).

        Args:
            config_path: Path to INI file.

        Returns:
            (global_config dict, {module_name: module_config dict})

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If parsing or validation fails.
        """
        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Config file not found: '{config_path}'")

        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(str(path), encoding='utf-8')
        except configparser.Error as e:
            raise ValueError(f"INI parse error in '{config_path}': {e}") from None

        global_config = cls._parse_global_section(parser)
        module_configs = cls._parse_module_sections(parser)

        return global_config, module_configs

    @classmethod
    def _parse_global_section(cls, parser: configparser.ConfigParser) -> dict:
        """Parse [global] section."""
        config: dict = {}
        if not parser.has_section('global'):
            return config

        for key, raw_value in parser.items('global'):
            # Sanctuary keys: silently ignore
            if key in cls.IGNORED_KEYS:
                continue

            # Color keys: handled separately by _parse_color_palette
            if key.startswith(cls.COLOR_KEY_PREFIX):
                continue

            # Unknown keys: warn
            if key not in cls.VALID_GLOBAL_KEYS:
                print(
                    f"[D-SafeLogger] INI: unknown key in [global]: {key!r} (ignored)",
                    file=sys.stderr,
                )
                continue

            config[key] = cls._convert_value(key, raw_value, section='global')

        return config

    @classmethod
    def _parse_module_sections(cls, parser: configparser.ConfigParser) -> dict[str, dict]:
        """Parse [dsafelogger:mod] sections."""
        module_configs: dict[str, dict] = {}

        for section in parser.sections():
            if not section.startswith(cls.MODULE_SECTION_PREFIX):
                if section != 'global':
                    print(
                        f"[D-SafeLogger] INI: unknown section [{section}] (ignored)",
                        file=sys.stderr,
                    )
                continue

            module_name = section[len(cls.MODULE_SECTION_PREFIX):]
            if not module_name:
                raise ValueError(f"INI: empty module name in section [{section}]")

            mod_config: dict = {}
            has_path = parser.has_option(section, 'path')

            for key, raw_value in parser.items(section):
                if key not in cls.VALID_MODULE_KEYS:
                    print(
                        f"[D-SafeLogger] INI: unknown key in [{section}]: {key!r} (ignored)",
                        file=sys.stderr,
                    )
                    continue

                # Routing keys require 'path'
                if not has_path and key in cls.MODULE_ROUTING_KEYS:
                    print(
                        f"[D-SafeLogger] INI: [{section}] key {key!r} requires "
                        f"'path' to be set (ignored)",
                        file=sys.stderr,
                    )
                    continue

                mod_config[key] = cls._convert_module_value(key, raw_value, section=section)

            # 'level' is required
            if 'level' not in mod_config:
                raise ValueError(f"INI: [{section}] requires 'level' key")

            module_configs[module_name] = mod_config

        return module_configs

    @classmethod
    def _parse_color_palette(
        cls,
        parser: configparser.ConfigParser,
        valid_abbreviations: set[str],
    ) -> dict[str, str]:
        """Extract color_{abbr} keys from [global] and return override dict.

        Returns:
            {abbreviation(upper): ANSI code numeric part}
        """
        VALID_VALUE_PATTERN = re.compile(r'^[0-9;]*$')

        if not parser.has_section('global'):
            return {}

        overrides: dict[str, str] = {}
        for key, raw_value in parser.items('global'):
            if not key.startswith(cls.COLOR_KEY_PREFIX):
                continue

            abbr = key[len(cls.COLOR_KEY_PREFIX):].upper()

            if abbr not in valid_abbreviations:
                print(
                    f"[D-SafeLogger] INI: unknown color key {key!r} "
                    f"(abbreviation {abbr!r} is not registered). Ignoring.",
                    file=sys.stderr,
                )
                continue

            value = raw_value.strip()
            if value == '':
                overrides[abbr] = ''
                continue

            if not VALID_VALUE_PATTERN.match(value):
                print(
                    f"[D-SafeLogger] INI: invalid ANSI code {value!r} "
                    f"for {key!r}. Only digits and semicolons are allowed. Ignoring.",
                    file=sys.stderr,
                )
                continue

            overrides[abbr] = value

        return overrides

    @classmethod
    def _convert_value(cls, key: str, raw_value: str, section: str) -> object:
        """Convert [global] section value to appropriate type."""
        if key == 'console_out':
            return cls._parse_console_out(key, raw_value, section)
        if key in cls.BOOL_KEYS:
            return cls._parse_bool(key, raw_value, section)
        if key in cls.INT_KEYS:
            return cls._parse_int(key, raw_value, section)
        if key in cls.OPTIONAL_INT_KEYS:
            return cls._parse_optional_int(key, raw_value, section)
        if key in cls.CSV_KEYS:
            return cls._parse_csv(key, raw_value, section)
        return raw_value

    @classmethod
    def _convert_module_value(cls, key: str, raw_value: str, section: str) -> object:
        """Convert module section value to appropriate type."""
        if key == 'level':
            return raw_value.upper()
        if key == 'path':
            return raw_value
        if key in ('routing_mode',):
            return raw_value
        if key in ('max_bytes', 'max_lines', 'suffix_digits', 'backup_count'):
            return cls._parse_int(key, raw_value, section)
        if key in ('max_count',):
            return cls._parse_optional_int(key, raw_value, section)
        if key in ('archive_mode',):
            return cls._parse_bool(key, raw_value, section)
        return raw_value

    @staticmethod
    def _parse_bool(key: str, raw_value: str, section: str) -> bool:
        """Parse boolean value. Fail-Fast."""
        v = raw_value.strip().lower()
        if v in ('true', '1', 'yes', 'on'):
            return True
        if v in ('false', '0', 'no', 'off'):
            return False
        raise ValueError(
            f"INI key '{key}' in [{section}]: expected bool, got {raw_value!r}"
        )

    @staticmethod
    def _parse_console_out(key: str, raw_value: str, section: str) -> bool | str:
        """Parse console_out with bool aliases plus the literal 'only'."""
        v = raw_value.strip().lower()
        if v in ('true', '1', 'yes', 'on'):
            return True
        if v in ('false', '0', 'no', 'off'):
            return False
        if v == 'only':
            return 'only'
        raise ValueError(
            f"INI key '{key}' in [{section}]: expected bool or 'only', got {raw_value!r}"
        )

    @staticmethod
    def _parse_int(key: str, raw_value: str, section: str) -> int:
        """Parse integer value. Fail-Fast."""
        raw_value = raw_value.strip()
        try:
            return int(raw_value)
        except ValueError:
            raise ValueError(
                f"INI key '{key}' in [{section}]: expected int, got {raw_value!r}"
            ) from None

    @staticmethod
    def _parse_optional_int(key: str, raw_value: str, section: str) -> int | None:
        """Parse optional integer value. Empty → None. Fail-Fast."""
        raw_value = raw_value.strip()
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except ValueError:
            raise ValueError(
                f"INI key '{key}' in [{section}]: expected int or empty, got {raw_value!r}"
            ) from None

    @staticmethod
    def _parse_csv(key: str, raw_value: str, section: str) -> list[str]:
        """Parse comma-separated string to list[str]."""
        raw_value = raw_value.strip()
        if not raw_value:
            return []
        items = [item.strip() for item in raw_value.split(',')]
        return [item for item in items if item]


class DictLoader:
    """Dict-based config loader with Fail-Fast validation.

    Delegates type conversion to IniLoader methods to ensure parity.
    """

    @classmethod
    def load(cls, config_dict: dict[str, dict[str, str]]) -> tuple[dict, dict[str, dict]]:
        """Load config from dict.

        Args:
            config_dict: {'global': {key: value}, 'dsafelogger:mod': {key: value}, ...}
                         All values must be str.

        Returns:
            (global_config, module_configs)

        Raises:
            TypeError: Invalid dict structure.
            ValueError: Type conversion or validation error.
        """
        if not isinstance(config_dict, dict):
            raise TypeError(
                f"config_dict must be dict[str, dict[str, str]], "
                f"got {type(config_dict).__name__}"
            )

        for section_name, section_value in config_dict.items():
            if not isinstance(section_name, str):
                raise TypeError(
                    f"config_dict section key must be str, "
                    f"got {type(section_name).__name__}: {section_name!r}"
                )
            if not isinstance(section_value, dict):
                raise TypeError(
                    f"config_dict section '{section_name}' must be dict[str, str], "
                    f"got {type(section_value).__name__}"
                )
            for key, value in section_value.items():
                if not isinstance(key, str):
                    raise TypeError(
                        f"config_dict key in ['{section_name}'] must be str, "
                        f"got {type(key).__name__}: {key!r}"
                    )
                if not isinstance(value, str):
                    raise TypeError(
                        f"config_dict value for '{key}' in ['{section_name}'] must be str, "
                        f"got {type(value).__name__}: {value!r}"
                    )

        global_config = cls._parse_global_section(config_dict)
        module_configs = cls._parse_module_sections(config_dict)

        return global_config, module_configs

    @classmethod
    def _parse_global_section(cls, config_dict: dict[str, dict[str, str]]) -> dict:
        """Parse 'global' section from dict."""
        config: dict = {}
        default_section = config_dict.get('global', {})

        for key, raw_value in default_section.items():
            key_lower = key.lower()

            if key_lower in IniLoader.IGNORED_KEYS:
                continue

            if key_lower.startswith(IniLoader.COLOR_KEY_PREFIX):
                continue

            if key_lower not in IniLoader.VALID_GLOBAL_KEYS:
                print(
                    f"[D-SafeLogger] config_dict: unknown key in [global]: {key!r} (ignored)",
                    file=sys.stderr,
                )
                continue

            config[key_lower] = IniLoader._convert_value(key_lower, raw_value, section='global')

        return config

    @classmethod
    def _parse_module_sections(cls, config_dict: dict[str, dict[str, str]]) -> dict[str, dict]:
        """Parse 'dsafelogger:' prefixed sections from dict."""
        module_configs: dict[str, dict] = {}

        for section_name, section_data in config_dict.items():
            if not section_name.startswith(IniLoader.MODULE_SECTION_PREFIX):
                if section_name != 'global':
                    print(
                        f"[D-SafeLogger] config_dict: unknown section [{section_name}] (ignored)",
                        file=sys.stderr,
                    )
                continue

            module_name = section_name[len(IniLoader.MODULE_SECTION_PREFIX):]
            if not module_name:
                raise ValueError(
                    f"config_dict: empty module name in section [{section_name}]"
                )

            mod_config: dict = {}
            has_path = 'path' in section_data

            for key, raw_value in section_data.items():
                key_lower = key.lower()

                if key_lower not in IniLoader.VALID_MODULE_KEYS:
                    print(
                        f"[D-SafeLogger] config_dict: unknown key in [{section_name}]: "
                        f"{key!r} (ignored)",
                        file=sys.stderr,
                    )
                    continue

                if not has_path and key_lower in IniLoader.MODULE_ROUTING_KEYS:
                    print(
                        f"[D-SafeLogger] config_dict: [{section_name}] key {key!r} requires "
                        f"'path' to be set (ignored)",
                        file=sys.stderr,
                    )
                    continue

                mod_config[key_lower] = IniLoader._convert_module_value(
                    key_lower, raw_value, section=section_name
                )

            if 'level' not in mod_config:
                raise ValueError(
                    f"config_dict: [{section_name}] requires 'level' key"
                )

            module_configs[module_name] = mod_config

        return module_configs

    @classmethod
    def _parse_color_palette(
        cls,
        config_dict: dict[str, dict[str, str]],
        valid_abbreviations: set[str],
    ) -> dict[str, str]:
        """Extract color_{abbr} keys from 'global' section of dict."""
        VALID_VALUE_PATTERN = re.compile(r'^[0-9;]*$')

        default_section = config_dict.get('global', {})
        overrides: dict[str, str] = {}

        for key, raw_value in default_section.items():
            key_lower = key.lower()
            if not key_lower.startswith(IniLoader.COLOR_KEY_PREFIX):
                continue

            abbr = key_lower[len(IniLoader.COLOR_KEY_PREFIX):].upper()

            if abbr not in valid_abbreviations:
                print(
                    f"[D-SafeLogger] config_dict: unknown color key {key!r} "
                    f"(abbreviation {abbr!r} is not registered). Ignoring.",
                    file=sys.stderr,
                )
                continue

            value = raw_value.strip()
            if value == '':
                overrides[abbr] = ''
                continue

            if not VALID_VALUE_PATTERN.match(value):
                print(
                    f"[D-SafeLogger] config_dict: invalid ANSI code {value!r} "
                    f"for {key!r}. Only digits and semicolons are allowed. Ignoring.",
                    file=sys.stderr,
                )
                continue

            overrides[abbr] = value

        return overrides
