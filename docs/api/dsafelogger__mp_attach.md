# Multiprocess Client Transport

**Module**: `dsafelogger._mp_attach`

Process-local multiprocess attach state and client-side transport.

## Functions

### `_build_local_drop_summary(state: 'MPProcessState') -> 'dict[str, int]'`

Aggregate root and module transport counters for DETACH.

### `_cleanup_process_local_state(state: 'MPProcessState') -> 'None'`

### `_do_attach(ctx: 'BootstrapContext') -> 'None'`

Attach the current process to an existing Writer runtime (3-phase).

Phase 1 (lock): validate state, prepare reply queue and ATTACH request.
Phase 2 (no lock): send ATTACH request and wait for ACK.
Phase 3 (lock): finalise process-local state and attach root handler.

Raises:
    RuntimeError: Already attached to a different session.
    TimeoutError: Writer ACK timed out.
    ValueError: Writer rejected the ATTACH (e.g. shutting down).

### `_do_detach(*, best_effort: 'bool' = False) -> 'None'`

Detach the current process from the Writer runtime and clean local state.

v23b ordering:
  Phase 1 — drain: stop all transports (joins pump threads for is_async=True).
  Phase 2 — close marker: put CloseMarker on log_queue so the Writer can
            confirm this client's drain on the log plane.
  Phase 3 — DETACH: send DETACH on the control plane with close_marker_failed
            flag if Phase 2 failed.
  Phase 4 — cleanup: remove handlers and clear process-local state.

### `_rehydrate_if_needed(state: 'MPProcessState') -> 'None'`

Restart pump threads that were lost due to a post-fork in the parent process.

### `_same_process_identity(state: 'MPProcessState') -> 'bool'`

### `_validate_attach_ack(ack: 'ControlAck', *, expected_protocol_version: 'int', expected_registry_hash: 'str') -> 'None'`

### `_validate_bootstrap_context(ctx: 'BootstrapContext') -> 'None'`

### `_validate_protocol_version(protocol_version: 'int') -> 'None'`

### `_validate_registry_hash(registry_hash: 'str') -> 'None'`

## Classes

### `MPClientTransport(ctx: 'BootstrapContext', ds_route: 'str', is_async: 'bool' = False) -> 'None'`

Serialises LogRecord → LogEvent and puts it onto the Writer's log_queue.

When is_async=True a process-local bounded queue + pump thread are used
so that the calling thread is never blocked by the Writer's queue pressure.

Public methods:

- `get_root_handler(self) -> 'logging.Handler'`
- `send_close_marker(self, client_id: 'str') -> 'bool'`
- `start(self) -> 'None'`
- `stop(self, timeout: 'float' = 5.0) -> 'bool'`

### `MPProcessState(session_id: 'str', ctx: 'BootstrapContext', client_id: 'str', process_pid: 'int', root_transport: 'MPClientTransport', module_transports: 'dict[str, MPClientTransport]') -> None`

Process-local attach state — one per attached process.
