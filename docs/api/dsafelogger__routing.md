# Routing Strategies

**Module**: `dsafelogger._routing`

Routing strategies for D-SafeLogger file switching.

## Functions

### `create_strategy(routing_mode: 'str', base_dir: 'Path', pg_name: 'str', interval: 'str | int' = 10, max_bytes: 'int' = 0, max_lines: 'int' = 0, max_count: 'int | None' = None, suffix_digits: 'int' = 3) -> 'RoutingStrategy'`

Factory function to create the appropriate routing strategy.

## Classes

### `CountStrategy(base_dir: 'Path', pg_name: 'str', max_lines: 'int', max_count: 'int | None', suffix_digits: 'int') -> 'None'`

Switch when line count exceeds max_lines: {pg_name}_{NNN}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `increment_line_count(self) -> 'None'`
- `is_cyclic(self) -> 'bool'`
- `on_emit(self) -> 'None'`
- `should_switch(self) -> 'bool'`

### `CyclicMonthStrategy(base_dir: 'Path', pg_name: 'str') -> 'None'`

Overwrite by month (12 files): {pg_name}_{MM}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `is_cyclic(self) -> 'bool'`
- `should_switch(self) -> 'bool'`

### `CyclicWeekdayStrategy(base_dir: 'Path', pg_name: 'str') -> 'None'`

Overwrite by day of week (7 files): {pg_name}_{dow}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `is_cyclic(self) -> 'bool'`
- `should_switch(self) -> 'bool'`

### `DailyStrategy(base_dir: 'Path', pg_name: 'str') -> 'None'`

Switch at midnight: {pg_name}_{YYYYMMDD}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `should_switch(self) -> 'bool'`

### `HourlyStrategy(base_dir: 'Path', pg_name: 'str') -> 'None'`

Switch every hour: {pg_name}_{YYYYMMDD_HH}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `should_switch(self) -> 'bool'`

### `MinIntervalStrategy(base_dir: 'Path', pg_name: 'str', interval: 'int') -> 'None'`

Switch at fixed minute boundaries: {pg_name}_{YYYYMMDD_HHMM}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `should_switch(self) -> 'bool'`

### `NoneStrategy(base_dir: 'Path', pg_name: 'str') -> 'None'`

No switching: single file forever.

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `should_switch(self) -> 'bool'`

### `RoutingStrategy(base_dir: 'Path', pg_name: 'str') -> 'None'`

Abstract base class for file routing strategies.

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `is_cyclic(self) -> 'bool'`
- `on_emit(self) -> 'None'`
- `should_switch(self) -> 'bool'`

### `SizeStrategy(base_dir: 'Path', pg_name: 'str', max_bytes: 'int', max_count: 'int | None', suffix_digits: 'int') -> 'None'`

Switch when file exceeds max_bytes: {pg_name}_{NNN}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `is_cyclic(self) -> 'bool'`
- `should_switch(self) -> 'bool'`

### `StartupIntervalStrategy(base_dir: 'Path', pg_name: 'str', interval: 'str | int') -> 'None'`

Switch after elapsed time from startup: {pg_name}_{YYYYMMDD_HHMMSS}.log

Public methods:

- `advance(self) -> 'Path'`
- `get_current_path(self) -> 'Path'`
- `should_switch(self) -> 'bool'`

## Constants

| Name | Type | Value |
|---|---|---|
| `VALID_MIN_INTERVAL_DIVISORS` | `frozenset` | `frozenset({1, 10, 12, 15, 2, 20, 3, 30, 4, 5, 6, 60})` |
| `WEEKDAY_SUFFIXES` | `tuple` | `('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')` |
