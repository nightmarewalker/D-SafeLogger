"""Control plane helpers for D-SafeLogger multiprocess."""
from __future__ import annotations

import multiprocessing
import os
import uuid
from typing import Any

from dsafelogger._mp_protocol import ControlAck, ControlRequest

CONTROL_PLANE_ACK_TIMEOUT_SEC: float = 5.0
MAX_IPC_LOG_TIMEOUT_SECONDS: float = 3.0
WRITER_STOP_WAIT_TIMEOUT_SEC: float = 10.0


def _resolve_mp_context(mp_context: Any = None) -> Any:
    """Normalize a multiprocessing context or start-method string.

    Args:
        mp_context: None, a start-method string, or a BaseContext-like object.
    """
    if mp_context is None:
        return multiprocessing.get_context()
    if isinstance(mp_context, str):
        return multiprocessing.get_context(mp_context)
    return mp_context


def _send_control_request(control_queue: Any, req: ControlRequest) -> None:
    """Put a ControlRequest onto the Writer's control queue (blocking)."""
    try:
        control_queue.put(req, block=True)
    except (BrokenPipeError, EOFError, OSError, ValueError) as exc:
        raise RuntimeError(f'failed to send control request: {exc!r}') from exc


def _wait_control_ack(recv_conn: Any, request_id: str) -> ControlAck:
    """Block until the Writer sends the matching ACK via recv_conn.

    Uses multiprocessing.Connection.poll() for timeout, then .recv() to
    retrieve the ACK.  Connection objects (from Pipe()) are picklable and
    can be embedded in ControlRequest dicts sent through another Queue.

    Raises:
        TimeoutError: If no ACK arrives within CONTROL_PLANE_ACK_TIMEOUT_SEC.
        RuntimeError: If the received ACK has a mismatched request_id.
    """
    try:
        if not recv_conn.poll(CONTROL_PLANE_ACK_TIMEOUT_SEC):
            raise TimeoutError(
                f'Control plane ACK timed out after {CONTROL_PLANE_ACK_TIMEOUT_SEC}s '
                f'(request_id={request_id!r})'
            )
        ack: ControlAck = recv_conn.recv()
        if ack['request_id'] != request_id:
            raise RuntimeError(
                f'Control plane request/ACK mismatch: '
                f'expected {request_id!r}, got {ack["request_id"]!r}'
            )
        return ack
    except TimeoutError:
        raise
    except (BrokenPipeError, EOFError, OSError, ValueError) as exc:
        raise RuntimeError(
            f'failed to receive control ACK for {request_id!r}: {exc!r}'
        ) from exc
    finally:
        try:
            recv_conn.close()
        except Exception:
            pass


def _raise_for_failed_ack(ack: ControlAck) -> None:
    """Raise the appropriate exception if the ACK signals failure.

    Raises:
        TimeoutError: error_category == 'timeout'
        ValueError: error_category == 'validation'
        RuntimeError: any other failure
    """
    if ack['success']:
        return
    category = ack.get('error_category')
    msg = ack.get('error_message') or 'Writer returned an error.'
    if category == 'timeout':
        raise TimeoutError(msg)
    if category == 'validation':
        raise ValueError(msg)
    raise RuntimeError(msg)


def _make_request(
    command: str,
    client_id: str,
    send_conn: Any,
    payload: dict[str, Any] | None = None,
) -> ControlRequest:
    """Build a ControlRequest using a Pipe send-end as the reply channel.

    Args:
        send_conn: The send end of a multiprocessing.Pipe(duplex=False) pair.
                   Connection objects are picklable and can be placed inside
                   a ControlRequest dict that travels through a Queue.
    """
    return ControlRequest(
        request_id=str(uuid.uuid4()),
        client_id=client_id,
        command=command,  # type: ignore[typeddict-item]
        reply_to=send_conn,
        payload=payload or {},
    )


def _make_pipe() -> tuple[Any, Any]:
    """Create a unidirectional Pipe.  Returns (send_conn, recv_conn)."""
    recv_conn, send_conn = multiprocessing.Pipe(duplex=False)
    return send_conn, recv_conn


def _make_pipe_with_context(mp_context: Any = None) -> tuple[Any, Any]:
    """Create a unidirectional Pipe using the normalized multiprocessing context."""
    resolved = _resolve_mp_context(mp_context)
    recv_conn, send_conn = resolved.Pipe(duplex=False)
    return send_conn, recv_conn


def _make_attach_request(
    client_id: str,
    send_conn: Any,
    session_id: str,
    *,
    protocol_version: int,
    registry_hash: str,
    pid: int | None = None,
) -> ControlRequest:
    return _make_request(
        'ATTACH', client_id, send_conn,
        {
            'session_id': session_id,
            'pid': os.getpid() if pid is None else pid,
            'protocol_version': protocol_version,
            'registry_hash': registry_hash,
        },
    )


def _make_bootstrap_ready_request(client_id: str, send_conn: Any) -> ControlRequest:
    return _make_request('BOOTSTRAP_READY', client_id, send_conn)


def _make_detach_request(
    client_id: str,
    send_conn: Any,
    *,
    close_marker_failed: bool = False,
    local_drop_summary: dict[str, int] | None = None,
) -> ControlRequest:
    return _make_request(
        'DETACH', client_id, send_conn,
        {
            'close_marker_failed': close_marker_failed,
            'local_drop_summary': local_drop_summary or {
                'attempted': 0,
                'drop_counter': 0,
                'overload_shed': 0,
                'transport_closed_drop': 0,
                'writer_unavailable_drop': 0,
                'timeout_drop': 0,
                'module_transport_count': 0,
            },
        },
    )


def _make_reopen_request(client_id: str, send_conn: Any) -> ControlRequest:
    return _make_request('REOPEN', client_id, send_conn)


def _make_status_request(client_id: str, send_conn: Any) -> ControlRequest:
    return _make_request('STATUS', client_id, send_conn)


def _make_stop_request(client_id: str, send_conn: Any) -> ControlRequest:
    return _make_request('STOP', client_id, send_conn)


def _send_control_ack(send_conn: Any, ack: ControlAck) -> None:
    """Send an ACK through the Pipe reply path and always close the endpoint."""
    try:
        send_conn.send(ack)
    except (BrokenPipeError, EOFError, OSError, ValueError) as exc:
        raise RuntimeError(f'failed to send control ACK: {exc!r}') from exc
    finally:
        try:
            send_conn.close()
        except Exception:
            pass
