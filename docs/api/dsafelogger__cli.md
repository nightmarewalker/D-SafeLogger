# CLI Tool

**Module**: `dsafelogger._cli`

D-SafeLogger CLI utility (dsafelogger command).

## Functions

### `cmd_init() -> 'None'`

Print INI config template to stdout.

### `cmd_ls(log_dir: 'str') -> 'None'`

List D-SafeLogger log files grouped by pg_name.

### `cmd_tail(log_dir: 'str', pg_name: 'str', initial_lines: 'int', poll_interval: 'float') -> 'None'`

Follow latest log file for a given pg_name, with transparent file switching.

### `main() -> 'None'`

CLI entry point.

## Constants

| Name | Type | Value |
|---|---|---|
| `INI_TEMPLATE` | `str` | `"; ==========================================================================...` |
