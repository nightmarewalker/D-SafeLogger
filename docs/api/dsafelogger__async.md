# Async Logging

**Module**: `dsafelogger._async`

Async logging support and safe shutdown for D-SafeLogger.

## Classes

### `DSafeQueueHandler(queue)`

Queue handler with producer-side context and diagnostic snapshot.

Does NOT call super().prepare() to avoid stdlib's destructive
exc_info formatting.

Public methods:

- `prepare(self, record: 'logging.LogRecord') -> 'logging.LogRecord'`

### `DSafeQueueListener(queue, *handlers, respect_handler_level=False)`

Queue listener running in empty Context.

Prevents application-side contextualize from leaking into
the consumer thread.

Public methods:

- `start(self) -> 'None'`
- `stop_with_timeout(self, timeout: 'float') -> 'None'`

## Constants

| Name | Type | Value |
|---|---|---|
| `QUEUE_DRAIN_TIMEOUT_SEC` | `float` | `10.0` |
| `WORKER_JOIN_TIMEOUT_SEC` | `float` | `5.0` |
