"""Custom log level management for D-SafeLogger."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

# ── Built-in immutable sets ──
_BUILTIN_VALUES: frozenset[int] = frozenset({10, 20, 30, 40, 50})
_BUILTIN_ABBREVIATIONS: frozenset[str] = frozenset({'DBG', 'INF', 'WAR', 'ERR', 'CRI'})
_BUILTIN_NAMES: frozenset[str] = frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'})

_BUILTIN_LEVEL_MAP: dict[str, str] = {
    'DEBUG': 'DBG', 'INFO': 'INF', 'WARNING': 'WAR',
    'ERROR': 'ERR', 'CRITICAL': 'CRI',
}

_BUILTIN_COLOR_MAP: dict[str, str] = {
    'DBG': '\033[36m',   # Cyan
    'INF': '\033[32m',   # Green
    'WAR': '\033[33m',   # Yellow
    'ERR': '\033[31m',   # Red
    'CRI': '\033[1;31m', # Bold Red
}

# ── Custom level store ──
# key: name (str), value: (value: int, abbreviation: str, color: str)
_custom_levels: dict[str, tuple[int, str, str]] = {}
_levels_lock = threading.RLock()


def register_level(
    name: str,
    value: int,
    abbreviation: str,
    color: str = '',
) -> None:
    """Register a custom log level.

    This is the internal implementation. The public API in __init__.py
    adds the state guard (must be called before ConfigureLogger).

    Args:
        name: Level name (e.g., 'TRACE'). Normalized to uppercase.
        value: Numeric value for the level.
        abbreviation: Exactly 3-character abbreviation.
        color: ANSI escape sequence. Empty for no color.

    Raises:
        ValueError: If validation fails.
    """
    name_upper = name.strip().upper()
    abbr_upper = abbreviation.strip().upper()

    if not name_upper:
        raise ValueError('name must not be empty')

    if value < 0:
        raise ValueError(f'value must be >= 0, got {value}')

    if value in _BUILTIN_VALUES:
        raise ValueError(
            f'Cannot override built-in level value {value}. '
            f'Built-in values are: {sorted(_BUILTIN_VALUES)}'
        )

    if name_upper in _BUILTIN_NAMES:
        raise ValueError(f'Cannot override built-in level name {name_upper!r}')

    if len(abbr_upper) != 3:
        raise ValueError(
            f'abbreviation must be exactly 3 characters, got {abbr_upper!r} '
            f'(length={len(abbr_upper)})'
        )

    if abbr_upper in _BUILTIN_ABBREVIATIONS:
        raise ValueError(
            f'abbreviation {abbr_upper!r} conflicts with built-in abbreviation'
        )

    with _levels_lock:
        # Check duplicates against existing custom levels
        for existing_name, (existing_value, existing_abbr, existing_color) in _custom_levels.items():
            if value == existing_value:
                if (
                    name_upper == existing_name
                    and abbr_upper == existing_abbr
                    and color == existing_color
                ):
                    return
                raise ValueError(
                    f'value {value} is already registered by level {existing_name!r}'
                )
            if abbr_upper == existing_abbr:
                if (
                    name_upper == existing_name
                    and value == existing_value
                    and color == existing_color
                ):
                    return
                raise ValueError(
                    f'abbreviation {abbr_upper!r} is already registered by level {existing_name!r}'
                )
            if name_upper == existing_name:
                if (
                    value == existing_value
                    and abbr_upper == existing_abbr
                    and color == existing_color
                ):
                    return
                raise ValueError(f'level {name_upper!r} is already registered')

        # Register with standard logging
        logging.addLevelName(value, name_upper)

        # Store internally
        _custom_levels[name_upper] = (value, abbr_upper, color)


def get_all_level_map() -> dict[str, str]:
    """Return unified LEVEL_MAP (built-in + custom).

    Used by Formatter initialization.
    """
    with _levels_lock:
        custom_levels = dict(_custom_levels)
    merged = _BUILTIN_LEVEL_MAP.copy()
    for name, (_, abbr, _) in custom_levels.items():
        merged[name] = abbr
    return merged


def get_all_color_map(
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return unified COLOR_MAP (built-in + custom + INI/dict overrides).

    Used by ColorStreamHandler initialization.

    Args:
        overrides: {abbreviation(upper): ANSI code numeric part} dict.
                   Empty string means disable color for that level.
    """
    with _levels_lock:
        custom_levels = dict(_custom_levels)
    merged = _BUILTIN_COLOR_MAP.copy()
    for _name, (_, abbr, color) in custom_levels.items():
        if color:
            merged[abbr] = color

    if overrides:
        for abbr, code in overrides.items():
            if code == '':
                merged.pop(abbr, None)
            else:
                merged[abbr] = f'\033[{code}m'

    return merged


def get_valid_level_names() -> set[str]:
    """Return valid level names for validation."""
    names = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    with _levels_lock:
        names.update(_custom_levels.keys())
    return names


def get_valid_abbreviations() -> set[str]:
    """Return valid abbreviations (built-in + custom)."""
    abbrs = {'DBG', 'INF', 'WAR', 'ERR', 'CRI'}
    with _levels_lock:
        custom_levels = dict(_custom_levels)
    for _, (_, abbr, _) in custom_levels.items():
        abbrs.add(abbr)
    return abbrs


def install_convenience_methods(logger_class: type) -> None:
    """Dynamically add convenience methods for custom levels.

    Example: register_level('TRACE', 5, 'TRC') → logger.trace(msg, ...)
    """
    with _levels_lock:
        custom_levels = dict(_custom_levels)
    for name, (value, _, _) in custom_levels.items():
        method_name = name.lower()

        if hasattr(logger_class, method_name):
            continue

        def _make_log_method(level_value: int) -> Callable[..., None]:
            def log_method(self: logging.Logger, msg: object, *args: Any, **kwargs: Any) -> None:
                if self.isEnabledFor(level_value):
                    self._log(level_value, msg, args, **kwargs)
            return log_method

        setattr(logger_class, method_name, _make_log_method(value))


def _clear_custom_levels_for_tests() -> None:
    """Clear custom levels for test isolation."""
    with _levels_lock:
        _custom_levels.clear()
