# Context Management

**Module**: `dsafelogger._context`

contextvars-based context management for D-SafeLogger.

## Functions

### `_snapshot_context() -> 'MappingProxyType[str, Any] | None'`

Return the current context snapshot safely for cross-thread/async queue hand-off.
Returns None if the context is empty. This is an O(1) operation because
MappingProxyType is treated as shallow immutable.

### `contextualize(**kwargs: 'Any') -> 'Generator[None, None, None]'`

Add kwargs to the logging context within a 'with' block.

Raises:
    TypeError: If any of the kwargs values are of a representative mutable type
               (list, dict, set, etc.). This enforces the fail-fast rule to
               prevent unintentional side effects due to shallow immutability
               of MappingProxyType when handed off across threads/tasks.

### `get_context() -> 'MappingProxyType[str, Any]'`

Return current logging context MappingProxyType.

### `reset_context(token: 'contextvars.Token') -> 'None'`

Reset logging context to previous state using token.

### `set_context(data: 'MappingProxyType[str, Any]') -> 'contextvars.Token'`

Set logging context and return reset token.
