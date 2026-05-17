"""Writer runtime for D-SafeLogger multiprocess.

WriterRuntime runs in the parent (Writer) process as two background threads:
  - _log_loop: drains the log plane queue, reconstructs LogRecords, dispatches to sinks
  - _control_loop: handles ATTACH / DETACH / REOPEN / STOP / STATUS requests

The WriterRuntime owns all file and console sink handlers; worker processes
only send serialised LogEvent dicts via the log_queue.

v23b: drain completion is determined by client close markers on the log plane,
not by Queue.empty(). Each client registered via ATTACH is expected to send a
CloseMarker on the log_queue before sending DETACH on the control_queue.
If a client cannot send its close marker (close_marker_failed=True in the DETACH
payload), the Writer records it as degraded and includes it in drain completion.

v23h: counters revised for spec §12.3 alignment.
  - `_writer_sink_reject` / `_writer_policy_reject` now count *per record*
    over the *required* sink set (best-effort sinks such as ColorStreamHandler
    do not contribute).
  - `_writer_event_reject` was split into `_writer_reconstruct_reject`
    (LogEvent reconstruct failure) and `_writer_close_marker_reject`
    (invalid CloseMarker / session mismatch / unknown client).
  - `_writer_best_effort_failures` is a visibility-only counter for
    best-effort sink failures (not aggregated into `_reject_counter`).
  - stderr warnings for sink/policy/best-effort/reconstruct/close-marker
    rejects are rate-limited (1st + every 100th).
  - idle / shutdown flush logic only runs when `writer_flush_batch > 1`.
  - `__init__` validates `ctx.writer_flush_batch >= 1`.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any

from dsafelogger._mp_control import WRITER_STOP_WAIT_TIMEOUT_SEC
from dsafelogger._mp_control import _send_control_ack
from dsafelogger._mp_protocol import (
    BootstrapContext,
    ControlAck,
    ControlRequest,
    _is_close_marker,
    _reconstruct_record,
)

# Rate limit for repetitive stderr warnings (1st + every Nth).
_REJECT_WARN_INTERVAL = 100


class WriterRuntime:
    """Owns sink handlers and drives log/control event loops."""

    def __init__(
        self,
        ctx: BootstrapContext,
        sink_groups: dict[str, list[logging.Handler]],
    ) -> None:
        if ctx.writer_flush_batch < 1:
            raise ValueError(
                f'writer_flush_batch must be >= 1, got {ctx.writer_flush_batch}'
            )
        self._ctx = ctx
        self._sink_groups = sink_groups  # route → handler list
        self._active_clients: dict[str, dict[str, Any]] = {}
        self._active_lock = threading.Lock()
        self._reopen_lock = threading.Lock()
        self._stop_requested = False
        self._accept_new_clients = True

        # Per-record reject counters (v23h)
        self._reject_counter = 0
        self._writer_route_reject: int = 0           # unknown route
        self._writer_reconstruct_reject: int = 0     # LogEvent reconstruct failure (v23h: split from event_reject)
        self._writer_close_marker_reject: int = 0    # invalid CloseMarker (v23h: split from event_reject)
        self._writer_sink_reject: int = 0            # required handler emit error (per record, v23h)
        self._writer_policy_reject: int = 0          # required handler filter false (per record, v23h)
        self._writer_partial_delivered: int = 0      # required sink set partial (v23h)
        self._writer_best_effort_failures: int = 0   # best-effort sink failures (v23h, visibility only)

        # Batch flush state (v23e + v23g opt-in)
        self._messages_since_flush: int = 0
        self._writer_flush_batch: int = ctx.writer_flush_batch
        self._batch_flush_enabled: bool = self._writer_flush_batch > 1

        # Drain / shutdown counters (v23g)
        self._writer_drain_deadline_loss: int = 0
        self._writer_flush_error_count: int = 0

        self._log_thread: threading.Thread | None = None
        self._control_thread: threading.Thread | None = None

        # v23b: close marker drain tracking (all protected by _active_lock)
        self._expected_close_markers: set[str] = set()
        self._close_markers_received: set[str] = set()
        self._close_marker_failed_clients: set[str] = set()
        self._drain_deadline: float | None = None
        self._close_marker_degraded: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start log and control plane threads.

        v23h: threads are `daemon=True`. Drain completeness is guaranteed by
        the explicit `stop()` call (registered via atexit through
        `_mp_shutdown`); the daemon flag is the safety net so a stop() that
        cannot drain in time still allows the interpreter to exit (§12.4
        bounded shutdown). This reverses the v22h non-daemon decision —
        rationale recorded in the v23h changelog.
        """
        if self._log_thread is not None or self._control_thread is not None:
            if (
                self._log_thread is not None and self._log_thread.is_alive()
                and self._control_thread is not None and self._control_thread.is_alive()
            ):
                return
            raise RuntimeError('WriterRuntime cannot be restarted after stop')
        self._log_thread = threading.Thread(
            target=self._log_loop,
            name='D-SafeLogger-WriterLog',
            daemon=True,
        )
        self._control_thread = threading.Thread(
            target=self._control_loop,
            name='D-SafeLogger-WriterControl',
            daemon=True,
        )
        self._log_thread.start()
        self._control_thread.start()

    def stop(self, timeout: float = WRITER_STOP_WAIT_TIMEOUT_SEC) -> None:
        """Request graceful shutdown and wait for threads to finish.

        v23h: bounded shutdown contract per §12.4. If the threads do not
        exit within `timeout`, a stderr warning is emitted enumerating the
        stuck threads. Because the threads are daemon=True, the interpreter
        will still exit (process survives instead of hanging). silent hang
        is forbidden.
        """
        self._drain_deadline = time.monotonic() + timeout
        self._stop_requested = True
        self._accept_new_clients = False
        if self._log_thread is not None:
            self._log_thread.join(timeout=timeout)
        if self._control_thread is not None:
            self._control_thread.join(timeout=timeout)
        # _log_loop already issued its final flush; close() handles its own flush.
        for handlers in self._sink_groups.values():
            for h in handlers:
                try:
                    h.close()
                except Exception:
                    pass
        # v23h §12.4 bounded shutdown: announce stuck threads (no silent hang).
        stuck: list[str] = []
        if self._log_thread is not None and self._log_thread.is_alive():
            stuck.append('log_thread')
        if self._control_thread is not None and self._control_thread.is_alive():
            stuck.append('control_thread')
        if stuck:
            print(
                f'[D-SafeLogger] WriterRuntime.stop() exceeded {timeout}s; '
                f'threads still alive: {stuck}. Drain incomplete; '
                'process exit will proceed (residual messages may be lost).',
                file=sys.stderr,
            )

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _maybe_warn(count: int, message: str) -> None:
        """Print to stderr on the 1st and every _REJECT_WARN_INTERVAL'th occurrence."""
        if count == 1 or count % _REJECT_WARN_INTERVAL == 0:
            print(
                f'[D-SafeLogger] {message} (count={count})',
                file=sys.stderr,
            )

    def _has_active_clients(self) -> bool:
        with self._active_lock:
            return bool(self._active_clients)

    def _drain_complete(self) -> bool:
        """Return True when it is safe for the log loop to exit.

        Conditions (all must hold):
        - stop has been requested
        - no active clients remain (all sent DETACH)
        - all expected close markers have arrived, OR are known to have failed,
          OR the drain deadline has been exceeded (degraded shutdown)
        """
        if not self._stop_requested:
            return False
        with self._active_lock:
            if self._active_clients:
                return False
            pending = self._expected_close_markers - (
                self._close_markers_received | self._close_marker_failed_clients
            )
            if not pending:
                return True
        # Outstanding markers — check deadline before waiting further
        deadline = self._drain_deadline
        if deadline is not None and time.monotonic() >= deadline:
            with self._active_lock:
                remaining = self._expected_close_markers - (
                    self._close_markers_received | self._close_marker_failed_clients
                )
            try:
                queued_loss = self._ctx.log_queue.qsize()
            except (NotImplementedError, OSError):
                queued_loss = -1  # unknown on this platform
            if queued_loss > 0:
                self._writer_drain_deadline_loss += queued_loss
            if remaining or queued_loss != 0:
                print(
                    f'[D-SafeLogger] drain deadline reached; '
                    f'{len(remaining)} close marker(s) outstanding: {remaining!r}; '
                    f'{queued_loss} message(s) remained in log queue',
                    file=sys.stderr,
                )
            return True
        return False

    def _record_close_marker(self, item: dict[str, Any]) -> None:
        """Validate a CloseMarker against session_id and registered clients."""
        client_id = item.get('client_id')
        session_id = item.get('session_id')
        if not isinstance(client_id, str) or not client_id:
            self._reject_counter += 1
            self._writer_close_marker_reject += 1
            self._maybe_warn(
                self._writer_close_marker_reject,
                'Writer rejected close marker: invalid client_id',
            )
            return
        if session_id != self._ctx.session_id:
            self._reject_counter += 1
            self._writer_close_marker_reject += 1
            self._maybe_warn(
                self._writer_close_marker_reject,
                f'Writer rejected close marker: session_id mismatch '
                f'for client {client_id!r}',
            )
            return
        with self._active_lock:
            if client_id not in self._expected_close_markers:
                self._reject_counter += 1
                self._writer_close_marker_reject += 1
                self._maybe_warn(
                    self._writer_close_marker_reject,
                    f'Writer rejected close marker: unexpected close marker '
                    f'client {client_id!r}',
                )
                return
            self._close_markers_received.add(client_id)

    def _flush_all_sinks(self) -> None:
        """Flush all file sink handlers and reset the batch counter."""
        for handlers in self._sink_groups.values():
            for h in handlers:
                try:
                    h.flush()
                except Exception as e:
                    self._writer_flush_error_count += 1
                    self._maybe_warn(
                        self._writer_flush_error_count,
                        f'Writer sink flush error: {e!r}',
                    )
        self._messages_since_flush = 0

    def _log_loop(self) -> None:
        # Hoist batch-flush flag out of the loop so per-message mode skips
        # the always-False idle/shutdown flush checks (v23h L1).
        do_idle_flush = self._batch_flush_enabled
        while True:
            if self._drain_complete():
                if do_idle_flush and self._messages_since_flush > 0:
                    self._flush_all_sinks()
                return
            try:
                item = self._ctx.log_queue.get(timeout=0.05)
            except Exception:
                # Queue momentarily empty: flush any pending writes immediately.
                if do_idle_flush and self._messages_since_flush > 0:
                    self._flush_all_sinks()
                continue
            if _is_close_marker(item):
                self._record_close_marker(item)
                continue
            try:
                record = _reconstruct_record(item)
                self._dispatch(record)
                self._messages_since_flush += 1
                if self._messages_since_flush >= self._writer_flush_batch:
                    self._flush_all_sinks()
            except Exception as e:
                self._reject_counter += 1
                self._writer_reconstruct_reject += 1
                self._maybe_warn(
                    self._writer_reconstruct_reject,
                    f'Writer rejected LogEvent: {e!r}',
                )

    def _control_loop(self) -> None:
        while True:
            try:
                req: ControlRequest = self._ctx.control_queue.get(timeout=0.2)
            except Exception:
                # On empty-queue timeout: check whether we can exit.
                if self._stop_requested and not self._has_active_clients():
                    return
                continue
            ack = self._handle(req)
            try:
                _send_control_ack(req['reply_to'], ack)
            except Exception as e:
                print(f'[D-SafeLogger] Writer failed to send ACK: {e!r}', file=sys.stderr)

    def _dispatch(self, record: logging.LogRecord) -> None:
        """Dispatch a record to the route's sink group (v23h: required vs best-effort).

        Counter accounting per spec §12.3:
            - required sink set: AppendOnlyFileHandler etc.
                (`_ds_required = True`; default for unknown handlers).
            - best-effort sink set: ColorStreamHandler etc.
                (`_ds_required = False`).

        All required handlers in the route are tried.  Outcome per record:
            - all required delivered → success (no counter)
            - all required failed → `_reject_counter += 1`,
              `_writer_sink_reject += 1` if any handler raised,
              `_writer_policy_reject += 1` if any handler filter returned False
            - some required delivered, some failed → `_writer_partial_delivered += 1`
              (rejection-counters NOT incremented; partial is its own terminal state)
            - best-effort failures → `_writer_best_effort_failures += 1`
              (never aggregated into `_reject_counter`)

        rate-limited stderr per the `_maybe_warn` helper.
        """
        route = getattr(record, '_ds_route', 'root')
        handlers = self._sink_groups.get(route)
        if handlers is None:
            self._reject_counter += 1
            self._writer_route_reject += 1
            self._maybe_warn(
                self._writer_route_reject,
                f'Writer rejected unknown route: {route!r}',
            )
            return

        required_total = 0
        required_delivered = 0
        required_sink_failed = False
        required_policy_failed = False
        last_sink_error: BaseException | None = None

        for h in handlers:
            is_required = getattr(h, '_ds_required', True)
            if not is_required:
                # Best-effort sink: visible on failure but not part of
                # delivered / partial / reject accounting.
                try:
                    h.handle(record)
                except Exception as e:
                    self._writer_best_effort_failures += 1
                    self._maybe_warn(
                        self._writer_best_effort_failures,
                        f'Writer best-effort sink error: {e!r}',
                    )
                continue

            required_total += 1
            try:
                if h.handle(record):
                    required_delivered += 1
                else:
                    required_policy_failed = True
            except Exception as e:
                required_sink_failed = True
                last_sink_error = e

        if required_total == 0:
            # Route has no required sinks — nothing to account for.
            return
        if required_delivered == required_total:
            return  # full delivery
        if required_delivered == 0:
            # Total failure of the required sink set.
            self._reject_counter += 1
            if required_sink_failed:
                self._writer_sink_reject += 1
                self._maybe_warn(
                    self._writer_sink_reject,
                    f'Writer required sink error: {last_sink_error!r}',
                )
            if required_policy_failed:
                self._writer_policy_reject += 1
                self._maybe_warn(
                    self._writer_policy_reject,
                    'Writer required handler policy rejected LogRecord',
                )
            return
        # Some required delivered, some failed → partial delivery.
        self._writer_partial_delivered += 1
        self._maybe_warn(
            self._writer_partial_delivered,
            f'Writer partial delivery: '
            f'{required_delivered}/{required_total} required handlers',
        )

    # ── Control request handlers ─────────────────────────────────────────────

    def _handle(self, req: ControlRequest) -> ControlAck:
        command = req.get('command', '')
        request_id = req.get('request_id', '')
        client_id = req.get('client_id', '')
        payload = req.get('payload', {})
        if command == 'BOOTSTRAP_READY':
            return self._cmd_bootstrap_ready(request_id)
        if command == 'ATTACH':
            return self._cmd_attach(request_id, client_id, payload)
        if command == 'DETACH':
            return self._cmd_detach(request_id, client_id, payload)
        if command == 'REOPEN':
            return self._cmd_reopen(request_id, client_id)
        if command == 'STOP':
            return self._cmd_stop(request_id, client_id)
        if command == 'STATUS':
            return self._cmd_status(request_id, client_id)
        return ControlAck(
            request_id=request_id, success=False,
            error_category='validation',
            error_message=f'Unknown command: {command!r}',
            result={},
        )

    def _cmd_bootstrap_ready(self, request_id: str) -> ControlAck:
        return ControlAck(
            request_id=request_id,
            success=True,
            error_category=None,
            error_message=None,
            result={
                'registry_hash': self._ctx.registry_hash,
                'protocol_version': self._ctx.protocol_version,
            },
        )

    def _cmd_attach(
        self, request_id: str, client_id: str, payload: dict[str, Any]
    ) -> ControlAck:
        if not self._accept_new_clients:
            return ControlAck(
                request_id=request_id, success=False,
                error_category='validation',
                error_message='Writer is shutting down; ATTACH rejected.',
                result={},
            )
        if payload.get('session_id') != self._ctx.session_id:
            return ControlAck(
                request_id=request_id,
                success=False,
                error_category='runtime',
                error_message='session_id mismatch during ATTACH',
                result={},
            )
        if payload.get('protocol_version') != self._ctx.protocol_version:
            return ControlAck(
                request_id=request_id,
                success=False,
                error_category='runtime',
                error_message='protocol_version mismatch during ATTACH',
                result={},
            )
        if payload.get('registry_hash') != self._ctx.registry_hash:
            return ControlAck(
                request_id=request_id,
                success=False,
                error_category='runtime',
                error_message='registry hash mismatch during ATTACH',
                result={},
            )
        with self._active_lock:
            self._active_clients[client_id] = {
                'pid': payload.get('pid', 0),
                'session_id': payload.get('session_id', ''),
            }
            self._expected_close_markers.add(client_id)
        return ControlAck(
            request_id=request_id, success=True,
            error_category=None, error_message=None,
            result={
                'registry_hash': self._ctx.registry_hash,
                'protocol_version': self._ctx.protocol_version,
            },
        )

    def _cmd_detach(
        self, request_id: str, client_id: str, payload: dict[str, Any]
    ) -> ControlAck:
        close_marker_failed = bool(payload.get('close_marker_failed', False))
        with self._active_lock:
            self._active_clients.pop(client_id, None)
            if close_marker_failed:
                self._close_marker_failed_clients.add(client_id)
                self._close_marker_degraded = True
        if close_marker_failed:
            print(
                f'[D-SafeLogger] close_marker_failed for client {client_id!r}: '
                'shutdown result is degraded',
                file=sys.stderr,
            )
        return ControlAck(
            request_id=request_id, success=True,
            error_category=None, error_message=None, result={},
        )

    def _cmd_reopen(self, request_id: str, client_id: str) -> ControlAck:
        with self._reopen_lock:
            try:
                count = 0
                seen: set[int] = set()
                for handlers in self._sink_groups.values():
                    for h in handlers:
                        hid = id(h)
                        if hid in seen:
                            continue
                        seen.add(hid)
                        if hasattr(h, 'reopen'):
                            h.reopen()
                            count += 1
                if count == 0:
                    return ControlAck(
                        request_id=request_id, success=False,
                        error_category='runtime',
                        error_message='No file sinks to reopen.',
                        result={},
                    )
                return ControlAck(
                    request_id=request_id, success=True,
                    error_category=None, error_message=None,
                    result={'reopened': count},
                )
            except ValueError as e:
                return ControlAck(
                    request_id=request_id, success=False,
                    error_category='validation',
                    error_message=str(e), result={},
                )
            except Exception as e:
                return ControlAck(
                    request_id=request_id, success=False,
                    error_category='runtime',
                    error_message=str(e), result={},
                )

    def _cmd_stop(self, request_id: str, client_id: str) -> ControlAck:
        self._stop_requested = True
        self._accept_new_clients = False
        with self._active_lock:
            self._active_clients.pop(client_id, None)
        return ControlAck(
            request_id=request_id, success=True,
            error_category=None, error_message=None, result={},
        )

    def _cmd_status(self, request_id: str, client_id: str) -> ControlAck:
        with self._active_lock:
            client_count = len(self._active_clients)
        return ControlAck(
            request_id=request_id, success=True,
            error_category=None, error_message=None,
            result={
                'active_clients': client_count,
                'reject_counter': self._reject_counter,
                'writer_route_reject': self._writer_route_reject,
                'writer_reconstruct_reject': self._writer_reconstruct_reject,
                'writer_close_marker_reject': self._writer_close_marker_reject,
                'writer_sink_reject': self._writer_sink_reject,
                'writer_policy_reject': self._writer_policy_reject,
                'writer_partial_delivered': self._writer_partial_delivered,
                'writer_best_effort_failures': self._writer_best_effort_failures,
                'writer_drain_deadline_loss': self._writer_drain_deadline_loss,
                'writer_flush_error_count': self._writer_flush_error_count,
                'stop_requested': self._stop_requested,
            },
        )
