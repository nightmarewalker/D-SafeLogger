# DSafeLogger Class

**Module**: `dsafelogger._logger`

DSafeLogger class for D-SafeLogger.

## Classes

### `DSafeLogger(name, level=0)`

Extended Logger with contextualize support.

Provides a context manager for adding key-value pairs to log output
within a specific scope. Uses contextvars for thread/async safety.

Public methods:

- `contextualize(self, **kwargs: 'object') -> 'Generator[None, None, None]'`
