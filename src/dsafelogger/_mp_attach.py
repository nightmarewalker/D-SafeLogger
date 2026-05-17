"""Process-local multiprocess attach state and client-side transport."""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from dsafelogger._context import _snapshot_context
from dsafelogger._mp_control import (
    _make_attach_request,
    _make_detach_request,
    _make_pipe_with_context,
    _raise_for_failed_ack,
    _send_control_request,
    _wait_control_ack,
)
from dsafelogger._mp_protocol import BootstrapContext, CloseMarker, LogEvent, _serialize_record

# ── Process-local state ──────────────────────────────────────────────────────

_mp_lifecycle_lock = threading.RLock()
_mp_runtime_state: MPProcessState | None = None  # type: ignore[name-defined]


@dataclass
class MPProcessState:
    """Process-local attach state — one per attached process."""
    session_id: str
    ctx: BootstrapContext
    client_id: str
    process_pid: int
    root_transport: MPClientTransport  # type: ignore[name-defined]
    module_transports: dict[str, MPClientTransport]  # type: ignore[name-defined]


# ── Client-side transport ────────────────────────────────────────────────────

class MPClientTransport:
    """Serialises LogRecord → LogEvent and puts it onto the Writer's log_queue.

    When is_async=True a process-local bounded queue + pump thread are used
    so that the calling thread is never blocked by the Writer's queue pressure.
    """

    def __init__(
        self,
        ctx: BootstrapContext,
        ds_route: str,
        is_async: bool = False,
    ) -> None:
        self._ctx = ctx
        self._ds_route = ds_route
        self._is_async = is_async
        self._local_queue: queue.Queue[LogEvent | None] | None = (
            queue.Queue(maxsize=ctx.ipc_client_queue_maxsize) if is_async else None
        )
        self._pump_thread: threading.Thread | None = None
        self._drop_counter: int = 0
        # cause-specific drop counters (v23c)
        self._overload_shed: int = 0
        self._transport_closed_drop: int = 0
        self._writer_unavailable_drop: int = 0
        self._timeout_drop: int = 0
        self._closed: bool = False
        self._stopping: bool = False
        self._writer_dead: bool = False
        # Stable handler returned to logging machinery
        self._handler = self._MPProxyHandler(self)

    def start(self) -> None:
        if self._local_queue is None:
            return
        if self._pump_thread is not None and self._pump_thread.is_alive():
            return
        self._pump_thread = threading.Thread(
            target=self._pump_loop,
            name='D-SafeLogger-MPClientPump',
            daemon=True,
        )
        self._pump_thread.start()

    def stop(self, timeout: float = 5.0) -> bool:
        if self._closed:
            return True
        self._stopping = True
        if self._local_queue is not None:
            try:
                self._local_queue.put(None, timeout=timeout)
            except queue.Full:
                self._closed = True
                return False
        else:
            self._closed = True
            return True
        if self._pump_thread is None:
            self._closed = True
            return True
        self._pump_thread.join(timeout)
        stopped = not self._pump_thread.is_alive()
        self._closed = True
        return stopped

    def send_close_marker(self, client_id: str) -> bool:
        """Put a CloseMarker on the log plane queue after all LogEvents are enqueued.

        Must be called after stop() so that for is_async=True the pump thread
        has already forwarded all local-queue events to log_queue.
        Returns True on success, False on close_marker_failed.
        """
        marker: CloseMarker = {
            'kind': 'close_marker',
            'client_id': client_id,
            'session_id': self._ctx.session_id,
        }
        try:
            self._ctx.log_queue.put(
                marker, block=True, timeout=self._ctx.ipc_log_timeout
            )
            return True
        except (queue.Full, BrokenPipeError, EOFError, OSError, ValueError) as exc:
            print(
                f'[D-SafeLogger] close_marker_failed for client {client_id!r}: {exc!r}',
                file=sys.stderr,
            )
            return False

    def get_root_handler(self) -> logging.Handler:
        return self._handler

    # ── Internal ──────────────────────────────────────────────────────────

    def _emit_record(self, record: logging.LogRecord) -> None:
        if self._closed or self._stopping:
            self._drop('transport closed')
            return
        if self._writer_dead:
            self._drop('writer unavailable')
            return
        event = _serialize_record(record, self._ds_route)
        if self._local_queue is None:
            self._send(event)
        else:
            try:
                self._local_queue.put_nowait(event)
            except queue.Full:
                self._drop('process-local async queue full')

    def _pump_loop(self) -> None:
        while True:
            item = self._local_queue.get()  # type: ignore[union-attr]
            if item is None:
                return
            self._send(item)

    def _send(self, event: LogEvent) -> None:
        if self._closed:
            self._drop('transport closed')
            return
        try:
            self._ctx.log_queue.put(
                event, block=True, timeout=self._ctx.ipc_log_timeout
            )
        except queue.Full:
            self._drop('log plane timeout/full')
        except (BrokenPipeError, EOFError, OSError, ValueError):
            self._writer_dead = True
            self._drop('writer unavailable')

    def _drop(self, reason: str) -> None:
        self._drop_counter += 1
        if reason == 'process-local async queue full':
            self._overload_shed += 1
        elif reason == 'transport closed':
            self._transport_closed_drop += 1
        elif reason == 'writer unavailable':
            self._writer_unavailable_drop += 1
        elif reason == 'log plane timeout/full':
            self._timeout_drop += 1
        if self._drop_counter == 1 or self._drop_counter % 100 == 0:
            print(
                f'[D-SafeLogger] multiprocess log dropped '
                f'({reason}, count={self._drop_counter})',
                file=sys.stderr,
            )

    class _MPProxyHandler(logging.Handler):
        """Thin handler that delegates to MPClientTransport._emit_record."""
        def __init__(self, transport: MPClientTransport) -> None:
            super().__init__()
            self._transport = transport

        def emit(self, record: logging.LogRecord) -> None:
            if not hasattr(record, '_ds_context'):
                record._ds_context = _snapshot_context()  # type: ignore[attr-defined]
            self._transport._emit_record(record)


# ── Attach implementation ────────────────────────────────────────────────────

def _rehydrate_if_needed(state: MPProcessState) -> None:
    """Restart pump threads that were lost due to a post-fork in the parent process."""
    for t in [state.root_transport, *state.module_transports.values()]:
        if t._is_async and (t._pump_thread is None or not t._pump_thread.is_alive()):
            t.start()


def _same_process_identity(state: MPProcessState) -> bool:
    return state.process_pid == os.getpid()


def _validate_bootstrap_context(ctx: BootstrapContext) -> None:
    if not isinstance(ctx.session_id, str) or not ctx.session_id:
        raise RuntimeError('invalid BootstrapContext: missing session_id')
    if ctx.log_queue is None or ctx.control_queue is None:
        raise RuntimeError('invalid BootstrapContext: missing IPC endpoints')


def _validate_protocol_version(protocol_version: int) -> None:
    if protocol_version != 1:
        raise RuntimeError(
            f'Unsupported protocol_version: expected 1, got {protocol_version!r}'
        )


def _validate_registry_hash(registry_hash: str) -> None:
    from dsafelogger.mp import _compute_registry_hash

    current = _compute_registry_hash()
    if registry_hash != current:
        raise RuntimeError(
            f'registry hash mismatch: ctx={registry_hash!r}, current={current!r}'
        )


def _validate_attach_ack(
    ack: dict[str, Any],
    *,
    expected_protocol_version: int,
    expected_registry_hash: str,
) -> None:
    result = ack.get('result', {})
    ack_protocol_version = result.get('protocol_version')
    ack_registry_hash = result.get('registry_hash')
    if ack_protocol_version != expected_protocol_version:
        raise RuntimeError(
            'protocol_version mismatch: '
            f'expected {expected_protocol_version!r}, got {ack_protocol_version!r}'
        )
    if ack_registry_hash != expected_registry_hash:
        raise RuntimeError(
            'registry hash mismatch: '
            f'expected {expected_registry_hash!r}, got {ack_registry_hash!r}'
        )


def _cleanup_process_local_state(state: MPProcessState) -> None:
    root = logging.getLogger()
    try:
        root.removeHandler(state.root_transport.get_root_handler())
    except Exception:
        pass
    for mod_name, transport in state.module_transports.items():
        mod_logger = logging.getLogger(mod_name)
        try:
            mod_logger.removeHandler(transport.get_root_handler())
        except Exception:
            pass
        mod_logger.propagate = True
    state.root_transport.stop()
    for transport in state.module_transports.values():
        transport.stop()


def _do_attach(ctx: BootstrapContext) -> None:
    """Attach the current process to an existing Writer runtime (3-phase).

    Phase 1 (lock): validate state, prepare reply queue and ATTACH request.
    Phase 2 (no lock): send ATTACH request and wait for ACK.
    Phase 3 (lock): finalise process-local state and attach root handler.

    Raises:
        RuntimeError: Already attached to a different session.
        TimeoutError: Writer ACK timed out.
        ValueError: Writer rejected the ATTACH (e.g. shutting down).
    """
    global _mp_runtime_state
    inherited_state: MPProcessState | None = None

    # ── Phase 1: validate + prepare ──────────────────────────────────────
    with _mp_lifecycle_lock:
        if _mp_runtime_state is not None:
            if _mp_runtime_state.session_id == ctx.session_id:
                if _same_process_identity(_mp_runtime_state):
                    _rehydrate_if_needed(_mp_runtime_state)
                    return
                inherited_state = _mp_runtime_state
            else:
                raise RuntimeError(
                    'Current process is already attached to a different Writer session. '
                    f'current={_mp_runtime_state.session_id!r}, new={ctx.session_id!r}'
                )
        _validate_bootstrap_context(ctx)
        _validate_protocol_version(ctx.protocol_version)
        _validate_registry_hash(ctx.registry_hash)
        client_id = f'{os.getpid()}-{uuid.uuid4().hex[:8]}'
        send_conn, recv_conn = _make_pipe_with_context(
            ctx.resolved_config.get('mp_start_method')
        )
        req = _make_attach_request(
            client_id=client_id,
            send_conn=send_conn,
            session_id=ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )

    # ── Phase 2: control plane I/O (outside lock) ─────────────────────────
    try:
        _send_control_request(ctx.control_queue, req)
        ack = _wait_control_ack(recv_conn, req['request_id'])
        _raise_for_failed_ack(ack)
        _validate_attach_ack(
            ack,
            expected_protocol_version=ctx.protocol_version,
            expected_registry_hash=ctx.registry_hash,
        )
    finally:
        try:
            send_conn.close()
        except Exception:
            pass

    # ── Phase 3: finalise process-local state ─────────────────────────────
    with _mp_lifecycle_lock:
        from dsafelogger._levels import install_convenience_methods
        from dsafelogger._logger import DSafeLogger

        if inherited_state is not None:
            _cleanup_process_local_state(inherited_state)

        logging.setLoggerClass(DSafeLogger)
        install_convenience_methods(DSafeLogger)

        is_async: bool = bool(ctx.resolved_config.get('is_async', False))

        root_transport = MPClientTransport(ctx, ds_route='root', is_async=is_async)
        root_transport.start()

        module_transports: dict[str, MPClientTransport] = {}
        for mod_name in ctx.resolved_config.get('module_routes', []):
            mt = MPClientTransport(
                ctx, ds_route=f'module:{mod_name}', is_async=is_async
            )
            mt.start()
            module_transports[mod_name] = mt

        _mp_runtime_state = MPProcessState(
            session_id=ctx.session_id,
            ctx=ctx,
            client_id=client_id,
            process_pid=os.getpid(),
            root_transport=root_transport,
            module_transports=module_transports,
        )

        # Attach client transport handler to root logger
        root = logging.getLogger()
        level_name = str(ctx.resolved_config.get('log_level', 'INFO'))
        root_level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
        root.setLevel(root_level)
        root.addHandler(root_transport.get_root_handler())

        # Module loggers
        module_levels = ctx.resolved_config.get('module_levels', {})
        if not isinstance(module_levels, dict):
            module_levels = {}
        for mod_name, mod_level_name in module_levels.items():
            mod_logger = logging.getLogger(str(mod_name))
            mod_logger.setLevel(
                logging.getLevelNamesMapping().get(str(mod_level_name), logging.DEBUG)
            )
            mod_logger.propagate = True
        for mod_name, mt in module_transports.items():
            mod_logger = logging.getLogger(mod_name)
            mod_level_name = str(module_levels.get(mod_name, 'DEBUG'))
            mod_logger.setLevel(logging.getLevelNamesMapping().get(mod_level_name, logging.DEBUG))
            mod_logger.propagate = False
            mod_logger.addHandler(mt.get_root_handler())


def _do_detach(*, best_effort: bool = False) -> None:
    """Detach the current process from the Writer runtime and clean local state.

    v23b ordering:
      Phase 1 — drain: stop all transports (joins pump threads for is_async=True).
      Phase 2 — close marker: put CloseMarker on log_queue so the Writer can
                confirm this client's drain on the log plane.
      Phase 3 — DETACH: send DETACH on the control plane with close_marker_failed
                flag if Phase 2 failed.
      Phase 4 — cleanup: remove handlers and clear process-local state.
    """
    global _mp_runtime_state

    with _mp_lifecycle_lock:
        state = _mp_runtime_state
        if state is None:
            return

    close_marker_sent = False
    send_conn = None
    try:
        # Phase 1: drain local queues (is_async=True: wait for pump thread)
        drain_ok = state.root_transport.stop()
        for transport in state.module_transports.values():
            if not transport.stop():
                drain_ok = False

        # Phase 2: send close marker on log plane (one per client)
        if drain_ok:
            close_marker_sent = state.root_transport.send_close_marker(state.client_id)
        else:
            print(
                f'[D-SafeLogger] local queue drain failed for client '
                f'{state.client_id!r}; skipping close marker',
                file=sys.stderr,
            )

        # Phase 3: send DETACH on control plane
        send_conn, recv_conn = _make_pipe_with_context(
            state.ctx.resolved_config.get('mp_start_method')
        )
        req = _make_detach_request(
            state.client_id, send_conn,
            close_marker_failed=not close_marker_sent,
        )
        try:
            _send_control_request(state.ctx.control_queue, req)
            ack = _wait_control_ack(recv_conn, req['request_id'])
            _raise_for_failed_ack(ack)
        finally:
            try:
                send_conn.close()
            except Exception:
                pass
    except Exception:
        if not best_effort:
            raise
    finally:
        # Phase 4: remove handlers and clear state (transports already stopped)
        with _mp_lifecycle_lock:
            current = _mp_runtime_state
            if current is not None:
                _cleanup_process_local_state(current)
                _mp_runtime_state = None
