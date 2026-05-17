# Multiprocess Protocol

**Module**: `dsafelogger._mp_protocol`

Multiprocess protocol types and record serialization for D-SafeLogger.

## Functions

### `_is_close_marker(item: 'Any') -> 'bool'`

Return True if item is a CloseMarker-like sentinel.

Full validation requires Writer runtime state (session_id and expected
client_id set), so it is performed in WriterRuntime._record_close_marker().

### `_reconstruct_record(event: 'LogEvent') -> 'logging.LogRecord'`

Reconstruct a LogRecord from a LogEvent for Writer-side dispatch.

The Writer does NOT re-evaluate logger hierarchy or level filters —
it dispatches directly to sink handlers.

### `_serialize_record(record: 'logging.LogRecord', ds_route: 'str') -> 'LogEvent'`

Snapshot a LogRecord into a picklable LogEvent on the producer thread.

## Classes

### `BootstrapContext(protocol_version: 'int', session_id: 'str', writer_pid: 'int', log_queue: 'Any', control_queue: 'Any', resolved_config: 'dict[str, object]', resolved_config_digest: 'str', registry_hash: 'str', log_queue_maxsize: 'int', ipc_client_queue_maxsize: 'int', writer_flush_batch: 'int', ipc_log_timeout: 'float', overflow_policy: "Literal['drop']") -> None`

Opaque, picklable context passed to worker processes via mp.GetWorkerInitializer.

### `CloseMarker(...)`

Sentinel sent on the log plane queue after all LogEvents from a client.

Ordering guarantee: CloseMarker is sent on the same log_queue as LogEvents,
so the Writer processes it in FIFO order after all preceding LogEvents.

### `ControlAck(...)`

dict() -> new empty dictionary
dict(mapping) -> new dictionary initialized from a mapping object's
    (key, value) pairs
dict(iterable) -> new dictionary initialized as if via:
    d = {}
    for k, v in iterable:
        d[k] = v
dict(**kwargs) -> new dictionary initialized with the name=value pairs
    in the keyword argument list.  For example:  dict(one=1, two=2)

### `ControlRequest(...)`

dict() -> new empty dictionary
dict(mapping) -> new dictionary initialized from a mapping object's
    (key, value) pairs
dict(iterable) -> new dictionary initialized as if via:
    d = {}
    for k, v in iterable:
        d[k] = v
dict(**kwargs) -> new dictionary initialized with the name=value pairs
    in the keyword argument list.  For example:  dict(one=1, two=2)

### `LogEvent(...)`

Picklable snapshot of a LogRecord for cross-process transport.
