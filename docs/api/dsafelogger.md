# Public API

**Module**: `dsafelogger`

D-SafeLogger: Zero-dependency, thread-safe, append-only logging library.

Public API:
    ConfigureLogger - Initialize the logging system with 3-layer config pipeline
    GetLogger       - Get a DSafeLogger instance (auto-fires ConfigureLogger if needed)
    RegisterLevel   - Register custom log levels before ConfigureLogger
    ReopenLogFiles  - Re-open file sinks after external log rotation
    SafeShutdown    - Terminal public shutdown for the current process

## Functions

### `ConfigureLogger(default_level: 'str' = 'INFO', log_path: 'str' = '.', pg_name: 'str' = 'Default', env_prefix: 'str' = 'D_LOG', config_file: 'str | None' = None, config_dict: 'dict[str, dict[str, str]] | None' = None, is_async: 'bool' = False, backup_count: 'int' = 0, archive_mode: 'bool' = False, routing_mode: 'str' = 'none', interval: 'str | int' = 10, max_bytes: 'int' = 0, max_lines: 'int' = 0, max_count: 'int | None' = None, suffix_digits: 'int' = 3, console_out: 'bool' = True, structured: 'bool' = False, fmt: 'str | logging.Formatter | None' = None, file_fmt: 'str | logging.Formatter | None' = None, console_fmt: 'str | logging.Formatter | None' = None, datefmt: 'str | None' = None, enable_hash: 'bool' = False, manifest_path: 'str | None' = None, sens_kws: 'Sequence[str] | None' = None, sens_kws_replace: 'bool' = False) -> 'None'`

Initialize D-SafeLogger with 3-layer config pipeline.

Settings are merged in order (higher overrides lower):
    Layer 1: Environment variables ({env_prefix}_LEVEL, etc.)
    Layer 2: INI file or dict (config_file / config_dict / {env_prefix}_CONFIG)
    Layer 3: Function arguments (defaults)

This function is idempotent: calling it multiple times after the first
explicit call is a no-op. Auto-fired initialization (via GetLogger) can
be overridden by an explicit call.

### `GetLogger(name: 'str' = '') -> 'DSafeLogger'`

Get a DSafeLogger instance.

If ConfigureLogger() has not been called yet, it will be auto-fired
with default arguments (state transitions to 'auto').

Args:
    name: Logger name. Empty string returns the root logger.

Returns:
    DSafeLogger instance (logging.Logger compatible).

### `RegisterLevel(name: 'str', value: 'int', abbreviation: 'str', color: 'str' = '') -> 'None'`

Register a custom log level before ConfigureLogger().

Must be called before ConfigureLogger(). Calling after initialization
raises RuntimeError.

Args:
    name: Level name (e.g. 'TRACE'). Normalized to uppercase.
    value: Numeric value (e.g. 5). Built-in values (10,20,30,40,50) are protected.
    abbreviation: 3-character abbreviation (e.g. 'TRC'). Required.
    color: ANSI escape sequence string. Empty for no color.

Raises:
    RuntimeError: If ConfigureLogger() has already been called.
    ValueError: If validation fails.

### `ReopenLogFiles() -> 'None'`

Re-open all writer-side file sinks after external log rotation.

Intended for use with routing_mode='none' and external log rotators
(e.g. logrotate on Linux) that use the rename + create cycle.

This function does NOT install any signal handler.  It is the caller's
responsibility to invoke ReopenLogFiles() in response to a notification
(e.g. SIGHUP or logrotate postrotate script).

Constraints:
    - ConfigureLogger() must have been called first.
    - routing_mode must be 'none' for every active file sink.

Raises:
    RuntimeError: If the logger has not been configured, or if no file
        sinks are found (console-only configuration).
    ValueError: If any active file sink uses a routing strategy other
        than NoneStrategy (routing_mode != 'none').

### `SafeShutdown() -> 'None'`

Shut down D-SafeLogger in the current process.

Flushes pending records, stops async listeners and worker threads,
closes file sinks, and removes D-SafeLogger handlers from the root logger.

This call is idempotent and safe to call alongside the atexit hook.
After SafeShutdown(), ConfigureLogger() and GetLogger() cannot be called
again in the same process; doing so raises RuntimeError.

For test suites that need fresh ConfigureLogger() calls per test, use an
internal test fixture rather than this public API.
