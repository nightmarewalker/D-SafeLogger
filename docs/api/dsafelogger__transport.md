# Transport Configuration

**Module**: `dsafelogger._transport`

Transport layer for D-SafeLogger.

Isolates execution mode (sync vs async) from the Capture and Sink layers.

## Classes

### `DirectTransport(handlers: 'Sequence[logging.Handler]') -> 'None'`

Synchronous transport that directly calls target handlers.

Public methods:

- `get_root_handler(self) -> 'logging.Handler'`
- `get_sink_handlers(self) -> 'list[logging.Handler]'`
- `start(self) -> 'None'`
- `stop(self, timeout: 'float | None' = None) -> 'bool'`

### `QueueTransport(handlers: 'Sequence[logging.Handler]', queue_size: 'int' = -1) -> 'None'`

Asynchronous transport using Queue.

Public methods:

- `get_root_handler(self) -> 'logging.Handler'`
- `get_sink_handlers(self) -> 'list[logging.Handler]'`
- `start(self) -> 'None'`
- `stop(self, timeout: 'float | None' = None) -> 'bool'`

### `Transport()`

Abstract base class for event transport mechanisms (v20).

Public methods:

- `get_root_handler(self) -> 'logging.Handler'`
- `get_root_handlers(self) -> 'list[logging.Handler]'`
- `get_sink_handlers(self) -> 'list[logging.Handler]'`
- `start(self) -> 'None'`
- `stop(self, timeout: 'float | None' = None) -> 'bool'`

### `TransportFactory()`

Creates the appropriate transport based on is_async flag.

## Constants

| Name | Type | Value |
|---|---|---|
| `QUEUE_DRAIN_TIMEOUT_SEC` | `float` | `10.0` |
