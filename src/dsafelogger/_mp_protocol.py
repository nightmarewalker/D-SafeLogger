"""Multiprocess protocol types and record serialization for D-SafeLogger."""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from dsafelogger._context import _snapshot_context

# Keys present on every LogRecord (never go into _ds_extra)
_STD_RECORD_KEYS: frozenset[str] = (
    frozenset(logging.makeLogRecord({}).__dict__) | {'message', 'asctime'}
)
_DS_INTERNAL_KEYS: frozenset[str] = frozenset({
    '_ds_route', '_ds_context', '_ds_exc_text', '_ds_diag_frames', '_ds_extra',
})


class CloseMarker(TypedDict):
    """Sentinel sent on the log plane queue after all LogEvents from a client.

    Ordering guarantee: CloseMarker is sent on the same log_queue as LogEvents,
    so the Writer processes it in FIFO order after all preceding LogEvents.
    """
    kind: Literal['close_marker']
    client_id: str
    session_id: str


def _is_close_marker(item: Any) -> bool:
    """Return True if item is a CloseMarker-like sentinel.

    Full validation requires Writer runtime state (session_id and expected
    client_id set), so it is performed in WriterRuntime._record_close_marker().
    """
    return isinstance(item, dict) and item.get('kind') == 'close_marker'


class LogEvent(TypedDict):
    """Picklable snapshot of a LogRecord for cross-process transport."""
    name: str
    levelno: int
    levelname: str
    pathname: str
    filename: str
    module: str
    lineno: int
    funcName: str
    msg: str
    created: float
    msecs: float
    relativeCreated: float
    process: int | None
    processName: str | None
    thread: int | None
    threadName: str | None
    _ds_route: str
    _ds_context: dict[str, Any]
    _ds_exc_text: str | None
    _ds_diag_frames: list[dict[str, Any]] | None
    _ds_extra: dict[str, Any]


class ControlRequest(TypedDict):
    request_id: str
    client_id: str
    command: Literal['ATTACH', 'DETACH', 'REOPEN', 'STOP', 'STATUS']
    reply_to: Any  # multiprocessing.Connection — send end of a Pipe
    payload: dict[str, Any]


class ControlAck(TypedDict):
    request_id: str
    success: bool
    error_category: str | None
    error_message: str | None
    result: dict[str, Any]


@dataclass(frozen=True)
class BootstrapContext:
    """Opaque, picklable context passed to worker processes via mp.GetWorkerInitializer."""
    protocol_version: int
    session_id: str
    writer_pid: int
    log_queue: Any                          # multiprocessing.Queue — log plane
    control_queue: Any                      # multiprocessing.Queue — control plane
    resolved_config: dict[str, object]      # config summary for worker-side setup
    resolved_config_digest: str
    registry_hash: str
    log_queue_maxsize: int
    ipc_client_queue_maxsize: int           # process-local async queue per transport
    writer_flush_batch: int                 # v23g: flush every N messages (1 = per-message)
    ipc_log_timeout: float
    overflow_policy: Literal['drop']


def _serialize_record(record: logging.LogRecord, ds_route: str) -> LogEvent:
    """Snapshot a LogRecord into a picklable LogEvent on the producer thread."""
    # Context: from record (snapshot already taken) or current TLS
    if hasattr(record, '_ds_context'):
        raw_ctx = getattr(record, '_ds_context')
        ctx: dict[str, Any] = dict(raw_ctx) if raw_ctx else {}
    else:
        snap = _snapshot_context()
        ctx = dict(snap) if snap else {}

    # Exception text: pre-computed snapshot or live format
    exc_text: str | None = getattr(record, '_ds_exc_text', None)
    if exc_text is None and record.exc_info and record.exc_info[1] is not None:
        try:
            exc_text = ''.join(traceback.format_exception(*record.exc_info))
        except Exception:
            exc_text = repr(record.exc_info[1])

    # Diagnostic frames (already snapshotted by DiagnosticFormatter)
    diag_frames: list[dict[str, Any]] | None = getattr(record, '_ds_diag_frames', None)

    # Pre-format the message so args don't need pickling
    try:
        msg = record.getMessage()
    except Exception:
        msg = str(record.msg)

    # Extra user-defined attributes (skip standard keys and internal _ds_* keys)
    extra: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STD_RECORD_KEYS or key in _DS_INTERNAL_KEYS or key.startswith('_'):
            continue
        try:
            import pickle
            pickle.dumps(value)
            extra[key] = value
        except Exception:
            extra[key] = repr(value)

    return LogEvent(
        name=record.name,
        levelno=record.levelno,
        levelname=record.levelname,
        pathname=record.pathname,
        filename=record.filename,
        module=record.module,
        lineno=record.lineno,
        funcName=record.funcName,
        msg=msg,
        created=record.created,
        msecs=record.msecs,
        relativeCreated=record.relativeCreated,
        process=record.process,
        processName=record.processName,
        thread=record.thread,
        threadName=record.threadName,
        _ds_route=ds_route,
        _ds_context=ctx,
        _ds_exc_text=exc_text,
        _ds_diag_frames=diag_frames,
        _ds_extra=extra,
    )


def _reconstruct_record(event: LogEvent) -> logging.LogRecord:
    """Reconstruct a LogRecord from a LogEvent for Writer-side dispatch.

    The Writer does NOT re-evaluate logger hierarchy or level filters —
    it dispatches directly to sink handlers.
    """
    d: dict[str, Any] = {
        'name': event['name'],
        'levelno': event['levelno'],
        'levelname': event['levelname'],
        'pathname': event['pathname'],
        'filename': event['filename'],
        'module': event['module'],
        'lineno': event['lineno'],
        'funcName': event['funcName'],
        'msg': event['msg'],
        'args': None,
        'created': event['created'],
        'msecs': event['msecs'],
        'relativeCreated': event['relativeCreated'],
        'process': event['process'],
        'processName': event['processName'],
        'thread': event['thread'],
        'threadName': event['threadName'],
        'exc_info': None,
        'exc_text': None,
    }
    record = logging.makeLogRecord(d)

    record._ds_route = event['_ds_route']
    record._ds_context = event['_ds_context']

    exc_text = event.get('_ds_exc_text')
    if exc_text:
        record._ds_exc_text = exc_text
        record.exc_text = exc_text

    diag_frames = event.get('_ds_diag_frames')
    if diag_frames:
        record._ds_diag_frames = diag_frames

    for key, value in event['_ds_extra'].items():
        if key not in _STD_RECORD_KEYS and key not in _DS_INTERNAL_KEYS:
            setattr(record, key, value)

    return record
