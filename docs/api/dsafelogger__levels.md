# Custom Log Levels

**Module**: `dsafelogger._levels`

Custom log level management for D-SafeLogger.

## Functions

### `_clear_custom_levels_for_tests() -> 'None'`

Clear custom levels for test isolation.

### `get_all_color_map(overrides: 'dict[str, str] | None' = None) -> 'dict[str, str]'`

Return unified COLOR_MAP (built-in + custom + INI/dict overrides).

Used by ColorStreamHandler initialization.

Args:
    overrides: {abbreviation(upper): ANSI code numeric part} dict.
               Empty string means disable color for that level.

### `get_all_level_map() -> 'dict[str, str]'`

Return unified LEVEL_MAP (built-in + custom).

Used by Formatter initialization.

### `get_valid_abbreviations() -> 'set[str]'`

Return valid abbreviations (built-in + custom).

### `get_valid_level_names() -> 'set[str]'`

Return valid level names for validation.

### `install_convenience_methods(logger_class: 'type') -> 'None'`

Dynamically add convenience methods for custom levels.

Example: RegisterLevel('TRACE', 5, 'TRC') -> logger.trace(msg, ...)

### `register_custom_level(name: 'str', value: 'int', abbreviation: 'str', color: 'str' = '') -> 'None'`

Register a custom log level.

This is the internal implementation. The public API in __init__.py
adds the state guard (must be called before ConfigureLogger).

Args:
    name: Level name (e.g., 'TRACE'). Normalized to uppercase.
    value: Numeric value for the level.
    abbreviation: Exactly 3-character abbreviation.
    color: ANSI escape sequence. Empty for no color.

Raises:
    ValueError: If validation fails.
