"""Shared configuration validation for D-SafeLogger v23j."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Literal, Mapping

from dsafelogger._constants import VALID_MIN_INTERVAL_DIVISORS, VALID_ROUTING_MODES


_DURATION_RE = re.compile(r'^(\d+)(h|d)$')


def is_cyclic_config(routing_mode: str, max_count: int | None) -> bool:
    """Return True when routing reuses file names cyclically."""
    return (
        routing_mode in ('cyclic_weekday', 'cyclic_month')
        or (routing_mode in ('size', 'count') and max_count is not None)
    )


def is_overflow_error_config(routing_mode: str, max_count: int | None) -> bool:
    """Return True for size/count monotonic index mode."""
    return routing_mode in ('size', 'count') and max_count is None


def is_generation_managed_config(routing_mode: str, max_count: int | None) -> bool:
    """Return True when backup_count/archive_mode can do useful work."""
    return routing_mode in ('daily', 'hourly', 'min_interval', 'startup_interval')


def parse_startup_interval_minutes(interval: str | int) -> int:
    """Parse startup_interval interval to minutes and reject non-positive values."""
    if isinstance(interval, bool):
        raise TypeError('interval must be int or str, got bool')
    if isinstance(interval, int):
        minutes = interval
    else:
        interval_str = str(interval).strip().lower()
        match = _DURATION_RE.match(interval_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            minutes = value * (60 if unit == 'h' else 1440)
        else:
            try:
                minutes = int(interval_str)
            except ValueError:
                raise ValueError(
                    f"Invalid interval: {interval!r}. "
                    f"Expected integer minutes, or duration string (e.g., '12h', '1d')"
                ) from None
    if minutes < 1:
        raise ValueError(f'interval must be >= 1 minute, got {interval!r}')
    return minutes


def validate_bool_args(params: Mapping[str, Any], *, scope: str) -> None:
    """Reject string truthiness for public Python API bool arguments."""
    for key, value in params.items():
        if not isinstance(value, bool):
            raise TypeError(f'{scope}: {key} must be bool, got {type(value).__name__}')


def validate_console_out_arg(value: object, *, scope: str) -> bool | Literal['only']:
    """Validate public Python API console_out.

    Only exact True, exact False, and the explicit literal "only" are accepted.
    Integers such as 1/0 are intentionally rejected even though bool is a
    subclass of int.
    """
    if value is True:
        return True
    if value is False:
        return False
    if value == 'only':
        return 'only'
    raise TypeError(
        f'{scope}: console_out must be True, False, or "only", '
        f'got {type(value).__name__}'
    )


def validate_level_name(level_name: str, *, valid_levels: Iterable[str], scope: str) -> None:
    """Validate a level name after custom levels are registered."""
    if level_name.upper() not in set(valid_levels):
        raise ValueError(f"{scope}: invalid level {level_name!r}")


def _has_formatter_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    return isinstance(value, logging.Formatter)


def _is_default_interval(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 10
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text) == 10
        except ValueError:
            return False
    return False


def validate_resolved_common_config(
    config: Mapping[str, Any],
    *,
    scope: str,
    valid_levels: Iterable[str] | None = None,
    level_key: str | None = None,
    check_formatter_conflict: bool = True,
) -> None:
    """Validate merged settings that are meaningful with or without file sinks."""
    if level_key is not None and valid_levels is not None:
        validate_level_name(str(config[level_key]), valid_levels=valid_levels, scope=scope)

    backup_count = config.get('backup_count', 0)
    max_bytes = config.get('max_bytes', 0)
    max_lines = config.get('max_lines', 0)
    max_count = config.get('max_count')
    suffix_digits = config.get('suffix_digits', 3)

    if backup_count < 0:
        raise ValueError(f'{scope}: backup_count must be >= 0, got {backup_count}')
    if max_bytes < 0:
        raise ValueError(f'{scope}: max_bytes must be >= 0, got {max_bytes}')
    if max_lines < 0:
        raise ValueError(f'{scope}: max_lines must be >= 0, got {max_lines}')
    if max_count is not None and max_count < 1:
        raise ValueError(f'{scope}: max_count must be >= 1 or None, got {max_count}')
    if suffix_digits < 1:
        raise ValueError(f'{scope}: suffix_digits must be >= 1, got {suffix_digits}')

    if check_formatter_conflict and config.get('structured'):
        for key in ('fmt', 'file_fmt', 'console_fmt'):
            if _has_formatter_value(config.get(key)):
                raise ValueError(
                    f'{scope}: structured=True cannot be specified with {key}'
                )
        if config.get('datefmt') not in (None, ''):
            raise ValueError(
                f'{scope}: structured=True cannot be specified with datefmt'
            )


def validate_console_only_conflicts(
    config: Mapping[str, Any],
    module_configs: Mapping[str, Mapping[str, Any]],
    *,
    scope: str,
) -> None:
    """Reject file-oriented settings in console-only mode."""
    problems: list[str] = []

    if config.get('log_path') != '.':
        problems.append('log_path must remain "."')
    if config.get('pg_name') != 'Default':
        problems.append('pg_name must remain "Default"')
    if _has_formatter_value(config.get('file_fmt')):
        problems.append('file_fmt is file-sink only')
    if config.get('routing_mode', 'none') != 'none':
        problems.append('routing_mode is file-sink only')
    if not _is_default_interval(config.get('interval', 10)):
        problems.append('interval is file-sink only')
    if config.get('max_bytes', 0) != 0:
        problems.append('max_bytes is file-sink only')
    if config.get('max_lines', 0) != 0:
        problems.append('max_lines is file-sink only')
    if config.get('max_count') is not None:
        problems.append('max_count is file-sink only')
    if config.get('backup_count', 0) != 0:
        problems.append('backup_count is file-sink only')
    if config.get('archive_mode', False):
        problems.append('archive_mode is file-sink only')
    if config.get('suffix_digits', 3) != 3:
        problems.append('suffix_digits is file-sink only')
    if config.get('enable_hash', False):
        problems.append('enable_hash is file-sink only')
    if config.get('manifest_path') not in (None, ''):
        problems.append('manifest_path is file-sink only')

    for mod_name, mod_conf in module_configs.items():
        prefix = f'module {mod_name!r}'
        if mod_conf.get('path') is not None:
            problems.append(f'{prefix}: path is file-sink only')
        if mod_conf.get('routing_mode', 'none') != 'none':
            problems.append(f'{prefix}: routing_mode is file-sink only')
        if not _is_default_interval(mod_conf.get('interval', 10)):
            problems.append(f'{prefix}: interval is file-sink only')
        if mod_conf.get('max_bytes', 0) != 0:
            problems.append(f'{prefix}: max_bytes is file-sink only')
        if mod_conf.get('max_lines', 0) != 0:
            problems.append(f'{prefix}: max_lines is file-sink only')
        if mod_conf.get('max_count') is not None:
            problems.append(f'{prefix}: max_count is file-sink only')
        if mod_conf.get('suffix_digits', 3) != 3:
            problems.append(f'{prefix}: suffix_digits is file-sink only')
        if mod_conf.get('backup_count', 0) != 0:
            problems.append(f'{prefix}: backup_count is file-sink only')
        if mod_conf.get('archive_mode', False):
            problems.append(f'{prefix}: archive_mode is file-sink only')

    if problems:
        raise ValueError(f'{scope}: console-only mode cannot use file-oriented settings: '
                         + '; '.join(problems))


def validate_resolved_file_config(
    config: Mapping[str, Any],
    *,
    scope: str,
    valid_levels: Iterable[str] | None = None,
    level_key: str | None = None,
    check_formatter_conflict: bool = True,
) -> None:
    """Validate one fully merged file-sink configuration.

    This is intentionally strict in v23j: combinations that cannot have the
    requested effect fail at startup instead of silently becoming no-ops.
    """
    validate_resolved_common_config(
        config,
        scope=scope,
        valid_levels=valid_levels,
        level_key=level_key,
        check_formatter_conflict=check_formatter_conflict,
    )

    routing_mode = str(config.get('routing_mode', 'none'))
    if routing_mode not in VALID_ROUTING_MODES:
        raise ValueError(
            f"{scope}: invalid routing_mode {routing_mode!r}; "
            f"valid values: {sorted(VALID_ROUTING_MODES)}"
        )

    backup_count = config.get('backup_count', 0)
    max_bytes = config.get('max_bytes', 0)
    max_lines = config.get('max_lines', 0)
    max_count = config.get('max_count')
    archive_mode = config.get('archive_mode', False)
    enable_hash = config.get('enable_hash', False)
    manifest_path = config.get('manifest_path')

    if routing_mode == 'size' and (max_bytes is None or max_bytes <= 0):
        raise ValueError(f"{scope}: routing_mode='size' requires max_bytes > 0, got {max_bytes!r}")
    if routing_mode == 'count' and (max_lines is None or max_lines <= 0):
        raise ValueError(f"{scope}: routing_mode='count' requires max_lines > 0, got {max_lines!r}")
    if routing_mode == 'min_interval':
        interval = config.get('interval', 10)
        int_interval = int(interval) if isinstance(interval, str) else interval
        if int_interval not in VALID_MIN_INTERVAL_DIVISORS:
            raise ValueError(
                f"{scope}: interval must be a divisor of 60, got {interval}. "
                f"Valid values: {sorted(VALID_MIN_INTERVAL_DIVISORS)}"
            )
    if routing_mode == 'startup_interval':
        parse_startup_interval_minutes(config.get('interval', 10))

    if manifest_path is not None and not enable_hash:
        raise ValueError(f'{scope}: manifest_path requires enable_hash=True')

    if routing_mode == 'none':
        if enable_hash:
            raise ValueError(f"{scope}: enable_hash=True requires routing_mode != 'none'")
        if backup_count > 0:
            raise ValueError(f"{scope}: backup_count requires routing_mode != 'none'")
        if archive_mode:
            raise ValueError(f"{scope}: archive_mode=True requires routing_mode != 'none'")

    if is_cyclic_config(routing_mode, max_count):
        if enable_hash:
            raise ValueError(f'{scope}: enable_hash=True is not allowed with cyclic routing')
        if backup_count > 0:
            raise ValueError(f'{scope}: backup_count is not allowed with cyclic routing')
        if archive_mode:
            raise ValueError(f'{scope}: archive_mode=True is not allowed with cyclic routing')

    if is_overflow_error_config(routing_mode, max_count):
        if backup_count > 0:
            raise ValueError(
                f'{scope}: backup_count is not allowed in overflow-error mode '
                '(size/count with max_count=None)'
            )
        if archive_mode:
            raise ValueError(
                f'{scope}: archive_mode=True is not allowed in overflow-error mode '
                '(size/count with max_count=None)'
            )

    if archive_mode and backup_count == 0:
        raise ValueError(f'{scope}: archive_mode=True requires backup_count > 0')
