# Multiprocess Control Plane

**Module**: `dsafelogger._mp_control`

Control plane helpers for D-SafeLogger multiprocess.

## Functions

### `_make_attach_request(client_id: 'str', send_conn: 'Any', session_id: 'str', *, protocol_version: 'int', registry_hash: 'str', pid: 'int | None' = None) -> 'ControlRequest'`

### `_make_bootstrap_ready_request(client_id: 'str', send_conn: 'Any') -> 'ControlRequest'`

### `_make_detach_request(client_id: 'str', send_conn: 'Any', *, close_marker_failed: 'bool' = False, local_drop_summary: 'dict[str, int] | None' = None) -> 'ControlRequest'`

### `_make_pipe() -> 'tuple[Any, Any]'`

Create a unidirectional Pipe.  Returns (send_conn, recv_conn).

### `_make_pipe_with_context(mp_context: 'Any' = None) -> 'tuple[Any, Any]'`

Create a unidirectional Pipe using the normalized multiprocessing context.

### `_make_reopen_request(client_id: 'str', send_conn: 'Any') -> 'ControlRequest'`

### `_make_request(command: 'str', client_id: 'str', send_conn: 'Any', payload: 'dict[str, Any] | None' = None) -> 'ControlRequest'`

Build a ControlRequest using a Pipe send-end as the reply channel.

Args:
    send_conn: The send end of a multiprocessing.Pipe(duplex=False) pair.
               Connection objects are picklable and can be placed inside
               a ControlRequest dict that travels through a Queue.

### `_make_status_request(client_id: 'str', send_conn: 'Any') -> 'ControlRequest'`

### `_make_stop_request(client_id: 'str', send_conn: 'Any') -> 'ControlRequest'`

### `_raise_for_failed_ack(ack: 'ControlAck') -> 'None'`

Raise the appropriate exception if the ACK signals failure.

Raises:
    TimeoutError: error_category == 'timeout'
    ValueError: error_category == 'validation'
    RuntimeError: any other failure

### `_resolve_mp_context(mp_context: 'Any' = None) -> 'Any'`

Normalize a multiprocessing context or start-method string.

Args:
    mp_context: None, a start-method string, or a BaseContext-like object.

### `_send_control_ack(send_conn: 'Any', ack: 'ControlAck') -> 'None'`

Send an ACK through the Pipe reply path and always close the endpoint.

### `_send_control_request(control_queue: 'Any', req: 'ControlRequest') -> 'None'`

Put a ControlRequest onto the Writer's control queue (blocking).

### `_wait_control_ack(recv_conn: 'Any', request_id: 'str') -> 'ControlAck'`

Block until the Writer sends the matching ACK via recv_conn.

Uses multiprocessing.Connection.poll() for timeout, then .recv() to
retrieve the ACK.  Connection objects (from Pipe()) are picklable and
can be embedded in ControlRequest dicts sent through another Queue.

Raises:
    TimeoutError: If no ACK arrives within CONTROL_PLANE_ACK_TIMEOUT_SEC.
    RuntimeError: If the received ACK has a mismatched request_id.

## Constants

| Name | Type | Value |
|---|---|---|
| `CONTROL_PLANE_ACK_TIMEOUT_SEC` | `float` | `5.0` |
| `MAX_IPC_LOG_TIMEOUT_SECONDS` | `float` | `3.0` |
| `WRITER_STOP_WAIT_TIMEOUT_SEC` | `float` | `10.0` |
