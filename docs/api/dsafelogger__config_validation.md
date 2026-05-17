# dsafelogger._config_validation

**Module**: `dsafelogger._config_validation`

Shared configuration validation for D-SafeLogger v23j.

## Functions

### `_has_formatter_value(value: 'Any') -> 'bool'`

### `is_cyclic_config(routing_mode: 'str', max_count: 'int | None') -> 'bool'`

Return True when routing reuses file names cyclically.

### `is_generation_managed_config(routing_mode: 'str', max_count: 'int | None') -> 'bool'`

Return True when backup_count/archive_mode can do useful work.

### `is_overflow_error_config(routing_mode: 'str', max_count: 'int | None') -> 'bool'`

Return True for size/count monotonic index mode.

### `parse_startup_interval_minutes(interval: 'str | int') -> 'int'`

Parse startup_interval interval to minutes and reject non-positive values.

### `validate_bool_args(params: 'Mapping[str, Any]', *, scope: 'str') -> 'None'`

Reject string truthiness for public Python API bool arguments.

### `validate_level_name(level_name: 'str', *, valid_levels: 'Iterable[str]', scope: 'str') -> 'None'`

Validate a level name after custom levels are registered.

### `validate_resolved_file_config(config: 'Mapping[str, Any]', *, scope: 'str', valid_levels: 'Iterable[str] | None' = None, level_key: 'str | None' = None, check_formatter_conflict: 'bool' = True) -> 'None'`

Validate one fully merged file-sink configuration.

This is intentionally strict in v23j: combinations that cannot have the
requested effect fail at startup instead of silently becoming no-ops.

## Constants

| Name | Type | Value |
|---|---|---|
| `VALID_MIN_INTERVAL_DIVISORS` | `frozenset` | `frozenset({1, 10, 12, 15, 2, 20, 3, 30, 4, 5, 6, 60})` |
| `VALID_ROUTING_MODES` | `frozenset` | `frozenset({'count', 'cyclic_month', 'cyclic_weekday', 'daily', 'hourly', 'min...` |
