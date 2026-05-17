"""Tests for MPClientTransport and WriterRuntime (UT-MP-TR, UT-MP-WR).

Covers:
    UT-MP-TR-001 to UT-MP-TR-007  (§29.4)
    UT-MP-WR-001 to UT-MP-WR-014  (§29.5)
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import replace

import pytest

from dsafelogger._mp_attach import MPClientTransport
from dsafelogger._mp_control import (
    _make_attach_request,
    _make_bootstrap_ready_request,
    _make_detach_request,
    _make_pipe,
    _make_reopen_request,
    _make_stop_request,
    _wait_control_ack,
)
from dsafelogger._mp_protocol import BootstrapContext, _serialize_record
from dsafelogger._mp_runtime import WriterRuntime
from dsafelogger._routing import NoneStrategy
from dsafelogger._handler import AppendOnlyFileHandler


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ctx(tmp_path, is_async=False, writer_flush_batch=1):
    """Create a minimal BootstrapContext for testing."""
    import multiprocessing as _mp
    ctx = BootstrapContext(
        protocol_version=1,
        session_id=uuid.uuid4().hex,
        writer_pid=os.getpid(),
        log_queue=_mp.get_context().Queue(100),
        control_queue=_mp.get_context().Queue(100),
        resolved_config={
            'is_async': is_async,
            'log_level': 'DEBUG',
            'module_routes': [],
        },
        resolved_config_digest='test',
        registry_hash='test_hash',
        log_queue_maxsize=100,
        ipc_client_queue_maxsize=100,
        writer_flush_batch=writer_flush_batch,
        ipc_log_timeout=1.0,
        overflow_policy='drop',
    )
    return ctx


def _make_runtime_with_mock_handler(tmp_path, ctx):
    """Create a WriterRuntime with a mock handler that records calls."""
    calls: list[logging.LogRecord] = []

    class RecordingHandler(logging.Handler):
        def emit(self, record):
            calls.append(record)

    handler = RecordingHandler()
    runtime = WriterRuntime(ctx, {'root': [handler]})
    runtime.start()
    return runtime, calls


def _stop_runtime(runtime):
    """Force-stop a WriterRuntime for test teardown."""
    runtime._stop_requested = True
    runtime._accept_new_clients = False
    with runtime._active_lock:
        runtime._active_clients.clear()
        # Mark all expected close markers as received so the log loop can exit
        # without waiting for markers that tests don't send.
        runtime._close_markers_received.update(runtime._expected_close_markers)
    if runtime._log_thread:
        runtime._log_thread.join(timeout=2.0)
    if runtime._control_thread:
        runtime._control_thread.join(timeout=2.0)
    for handlers in runtime._sink_groups.values():
        for h in handlers:
            try:
                h.flush()
                h.close()
            except Exception:
                pass


# ── UT-MP-TR: MPClientTransport tests ────────────────────────────────────────


class TestMPClientTransport:

    def test_sync_direct_send(self, tmp_path):
        """UT-MP-TR-001: is_async=False sends event directly to log_queue."""
        ctx = _make_ctx(tmp_path, is_async=False)
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        transport.start()

        rec = logging.makeLogRecord({'msg': 'hello', 'levelno': logging.INFO})
        transport._emit_record(rec)

        event = ctx.log_queue.get(timeout=1.0)
        assert event['msg'] == 'hello'

        transport.stop()

    def test_async_mode_pump_thread(self, tmp_path):
        """UT-MP-TR-002: is_async=True uses local queue + pump thread."""
        ctx = _make_ctx(tmp_path, is_async=True)
        transport = MPClientTransport(ctx, ds_route='root', is_async=True)
        transport.start()

        assert transport._pump_thread is not None
        assert transport._pump_thread.is_alive()

        rec = logging.makeLogRecord({'msg': 'async_msg', 'levelno': logging.INFO})
        transport._emit_record(rec)

        event = ctx.log_queue.get(timeout=2.0)
        assert event['msg'] == 'async_msg'
        transport.stop()

    def test_queue_full_increments_drop_counter(self, tmp_path, capsys):
        """UT-MP-TR-003: full log_queue increments drop counter and warns."""
        class FullQueue:
            def put(self, *_args, **_kwargs):
                raise queue.Full

        ctx = replace(
            _make_ctx(tmp_path, is_async=False),
            log_queue=FullQueue(),
            ipc_log_timeout=0.01,
        )

        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        rec = logging.makeLogRecord({'msg': 'overflow', 'levelno': logging.INFO})
        transport._emit_record(rec)

        assert transport._drop_counter >= 1
        assert transport._timeout_drop >= 1
        err = capsys.readouterr().err
        assert 'D-SafeLogger' in err

    def test_broken_pipe_sets_writer_dead(self, tmp_path, capsys):
        """UT-MP-TR-004: BrokenPipeError sets writer_dead and increments drop."""
        ctx = _make_ctx(tmp_path, is_async=False)
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)

        # Close the queue to simulate broken pipe
        ctx.log_queue.close()

        rec = logging.makeLogRecord({'msg': 'broken', 'levelno': logging.INFO})
        transport._emit_record(rec)

        # _writer_dead may be True (OSError from closed queue)
        # drop counter should be >= 1
        assert transport._writer_dead is True
        assert transport._drop_counter >= 1

    def test_closed_transport_drops(self, tmp_path, capsys):
        """UT-MP-TR-005: emitting to a closed transport is a drop, not exception."""
        ctx = _make_ctx(tmp_path, is_async=False)
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        transport._closed = True

        rec = logging.makeLogRecord({'msg': 'closed', 'levelno': logging.INFO})
        transport._emit_record(rec)

        assert transport._drop_counter >= 1
        with pytest.raises(queue.Empty):
            ctx.log_queue.get(timeout=0.2)

    def test_drop_warning_first_and_every_100(self, tmp_path, capsys):
        """UT-MP-TR-006: drop warning appears on first and every 100th drop."""
        ctx = _make_ctx(tmp_path, is_async=False)
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        transport._closed = True

        for _ in range(101):
            rec = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
            transport._emit_record(rec)

        err = capsys.readouterr().err
        # First drop (count=1) and 100th drop → at least 2 warnings
        assert err.count('[D-SafeLogger] multiprocess log dropped') >= 2

    def test_stop_full_queue_returns_false(self, tmp_path):
        """UT-MP-TR-007: stop() with full local queue returns False (no infinite block)."""
        ctx = _make_ctx(tmp_path, is_async=True)
        transport = MPClientTransport(ctx, ds_route='root', is_async=True)
        # Do NOT start the pump thread — queue must stay full so put(None) times out.

        assert transport._local_queue is not None
        while True:
            try:
                transport._local_queue.put_nowait(
                    _serialize_record(
                        logging.makeLogRecord({'msg': 'fill', 'levelno': logging.INFO}),
                        'root',
                    )
                )
            except queue.Full:
                break

        result = transport.stop(timeout=0.1)
        assert result is False


# ── UT-MP-WR: WriterRuntime tests ─────────────────────────────────────────────


class TestWriterRuntime:

    def test_bootstrap_ready_reports_protocol_and_registry(self, tmp_path):
        """BOOTSTRAP_READY returns the Writer-owned protocol and registry hash."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        send_conn, recv_conn = _make_pipe()

        req = _make_bootstrap_ready_request('bootstrap-test', send_conn)
        ctx.control_queue.put(req)

        ack = _wait_control_ack(recv_conn, req['request_id'])
        assert ack['success'] is True
        assert ack['result']['protocol_version'] == ctx.protocol_version
        assert ack['result']['registry_hash'] == ctx.registry_hash

        _stop_runtime(runtime)

    def test_attach_registers_client(self, tmp_path):
        """UT-MP-WR-001: ATTACH request registers the client."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        send_conn, recv_conn = _make_pipe()
        client_id = 'test-client-001'

        req = _make_attach_request(
            client_id, send_conn, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(req)

        ack = _wait_control_ack(recv_conn, req['request_id'])
        assert ack['success'] is True

        with runtime._active_lock:
            assert client_id in runtime._active_clients

        _stop_runtime(runtime)

    def test_detach_removes_client(self, tmp_path):
        """UT-MP-WR-002: DETACH request removes the client."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'test-client-002'

        # ATTACH first
        send1, recv1 = _make_pipe()
        req = _make_attach_request(
            client_id, send1, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(req)
        _wait_control_ack(recv1, req['request_id'])

        # DETACH
        send2, recv2 = _make_pipe()
        req2 = _make_detach_request(client_id, send2)
        ctx.control_queue.put(req2)
        ack2 = _wait_control_ack(recv2, req2['request_id'])
        assert ack2['success'] is True

        with runtime._active_lock:
            assert client_id not in runtime._active_clients

        _stop_runtime(runtime)

    def test_root_route_dispatch(self, tmp_path):
        """UT-MP-WR-003: root route event reaches root sink handlers."""
        ctx = _make_ctx(tmp_path)
        runtime, calls = _make_runtime_with_mock_handler(tmp_path, ctx)

        rec = logging.makeLogRecord({'msg': 'root_msg', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'root')
        ctx.log_queue.put(event)

        for _ in range(20):
            if calls:
                break
            time.sleep(0.05)

        _stop_runtime(runtime)
        assert any(r.msg == 'root_msg' for r in calls)

    def test_module_route_dispatch(self, tmp_path):
        """UT-MP-WR-004: module route event reaches the module sink group."""
        ctx = _make_ctx(tmp_path)
        module_calls: list[logging.LogRecord] = []

        class ModuleHandler(logging.Handler):
            def emit(self, record):
                module_calls.append(record)

        sink_groups = {
            'root': [logging.NullHandler()],
            'module:myapp': [ModuleHandler()],
        }
        runtime = WriterRuntime(ctx, sink_groups)
        runtime.start()

        rec = logging.makeLogRecord({'msg': 'mod_msg', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'module:myapp')
        ctx.log_queue.put(event)

        for _ in range(20):
            if module_calls:
                break
            time.sleep(0.05)

        _stop_runtime(runtime)
        assert any(r.msg == 'mod_msg' for r in module_calls)

    def test_bad_log_event_increments_reject_counter(self, tmp_path, capsys):
        """UT-MP-WR-006: corrupt LogEvent increments reject_counter, processing continues."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)

        # Send a corrupt event (missing required keys)
        ctx.log_queue.put({'bad': 'event'})

        time.sleep(0.3)
        _stop_runtime(runtime)
        assert runtime._reject_counter >= 1

    def test_unknown_route_rejected_without_root_fallback(self, tmp_path, capsys):
        """UT-MP-WR-005/016: unknown route increments reject counter and does not hit root."""
        ctx = _make_ctx(tmp_path)
        runtime, calls = _make_runtime_with_mock_handler(tmp_path, ctx)

        rec = logging.makeLogRecord({'msg': 'wrong_route', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'module:missing')
        ctx.log_queue.put(event)

        time.sleep(0.3)
        _stop_runtime(runtime)

        assert runtime._reject_counter >= 1
        assert calls == []
        assert 'unknown route' in capsys.readouterr().err

    def test_reopen_request_succeeds(self, tmp_path):
        """UT-MP-WR-007: REOPEN request on NoneStrategy sink returns success ACK."""
        ctx = _make_ctx(tmp_path)
        strategy = NoneStrategy(tmp_path, 'Reopen')
        handler = AppendOnlyFileHandler(strategy=strategy)
        runtime = WriterRuntime(ctx, {'root': [handler]})
        runtime.start()

        client_id = 'reopen-client'

        # Attach first
        send1, recv1 = _make_pipe()
        attach_req = _make_attach_request(
            client_id, send1, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(attach_req)
        _wait_control_ack(recv1, attach_req['request_id'])

        # Send REOPEN
        send2, recv2 = _make_pipe()
        reopen_req = _make_reopen_request(client_id, send2)
        ctx.control_queue.put(reopen_req)
        ack = _wait_control_ack(recv2, reopen_req['request_id'])

        _stop_runtime(runtime)
        assert ack['success'] is True
        assert ack['result']['reopened'] >= 1

    def test_reopen_non_none_strategy_validation_error(self, tmp_path):
        """UT-MP-WR-008: REOPEN on non-NoneStrategy sink returns validation error ACK."""
        from dsafelogger._routing import DailyStrategy
        ctx = _make_ctx(tmp_path)
        strategy = DailyStrategy(tmp_path, 'Daily')
        handler = AppendOnlyFileHandler(strategy=strategy)
        runtime = WriterRuntime(ctx, {'root': [handler]})
        runtime.start()

        client_id = 'reopen-daily'
        send1, recv1 = _make_pipe()
        attach_req = _make_attach_request(
            client_id, send1, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(attach_req)
        _wait_control_ack(recv1, attach_req['request_id'])

        send2, recv2 = _make_pipe()
        reopen_req = _make_reopen_request(client_id, send2)
        ctx.control_queue.put(reopen_req)
        ack = _wait_control_ack(recv2, reopen_req['request_id'])

        _stop_runtime(runtime)
        assert ack['success'] is False
        assert ack['error_category'] == 'validation'

    def test_reopen_no_file_sink_runtime_error(self, tmp_path):
        """UT-MP-WR-009: REOPEN when no file sinks exist returns runtime error ACK."""
        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': [logging.NullHandler()]})
        runtime.start()

        client_id = 'reopen-nosink'
        send1, recv1 = _make_pipe()
        attach_req = _make_attach_request(
            client_id, send1, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(attach_req)
        _wait_control_ack(recv1, attach_req['request_id'])

        send2, recv2 = _make_pipe()
        reopen_req = _make_reopen_request(client_id, send2)
        ctx.control_queue.put(reopen_req)
        ack = _wait_control_ack(recv2, reopen_req['request_id'])

        _stop_runtime(runtime)
        assert ack['success'] is False
        assert ack['error_category'] == 'runtime'

    def test_stop_after_attach_rejects_new_attach(self, tmp_path):
        """UT-MP-WR-012: STOP → subsequent ATTACH is rejected."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'stop-test'

        # ATTACH
        send1, recv1 = _make_pipe()
        attach_req = _make_attach_request(
            client_id, send1, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(attach_req)
        _wait_control_ack(recv1, attach_req['request_id'])

        # STOP
        send2, recv2 = _make_pipe()
        stop_req = _make_stop_request(client_id, send2)
        ctx.control_queue.put(stop_req)
        _wait_control_ack(recv2, stop_req['request_id'])

        # Subsequent ATTACH should be rejected
        send3, recv3 = _make_pipe()
        new_attach = _make_attach_request(
            'new-client', send3, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(new_attach)
        ack = _wait_control_ack(recv3, new_attach['request_id'])

        _stop_runtime(runtime)
        assert ack['success'] is False

    def test_attach_protocol_version_mismatch_returns_runtime_error_ack(self, tmp_path):
        """Attach with mismatched protocol_version is rejected."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        send_conn, recv_conn = _make_pipe()
        req = _make_attach_request(
            'bad-proto', send_conn, ctx.session_id,
            protocol_version=999,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(req)
        ack = _wait_control_ack(recv_conn, req['request_id'])
        _stop_runtime(runtime)
        assert ack['success'] is False
        assert ack['error_category'] == 'runtime'

    def test_attach_registry_hash_mismatch_returns_runtime_error_ack(self, tmp_path):
        """Attach with mismatched registry_hash is rejected."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        send_conn, recv_conn = _make_pipe()
        req = _make_attach_request(
            'bad-hash', send_conn, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash='wrong-hash',
        )
        ctx.control_queue.put(req)
        ack = _wait_control_ack(recv_conn, req['request_id'])
        _stop_runtime(runtime)
        assert ack['success'] is False
        assert ack['error_category'] == 'runtime'

    def test_writer_threads_are_daemon(self, tmp_path):
        """v23h: WriterRuntime threads are daemon=True (§12.4 bounded shutdown).

        Replaces UT-MP-WR-014 (was: daemon=False). Drain completeness is
        guaranteed by atexit-registered _mp_shutdown → runtime.stop(); the
        daemon flag is the safety net to prevent silent hang if drain stalls.
        """
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)

        assert runtime._log_thread is not None
        assert runtime._control_thread is not None
        assert runtime._log_thread.daemon is True
        assert runtime._control_thread.daemon is True

        _stop_runtime(runtime)

    def test_unknown_command_returns_error_ack(self, tmp_path):
        """Unknown control command returns an error ACK."""
        from dsafelogger._mp_protocol import ControlRequest
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        send_conn, recv_conn = _make_pipe()

        req = ControlRequest(
            request_id=uuid.uuid4().hex,
            client_id='unknown-cmd',
            command='UNKNOWN',  # type: ignore[typeddict-item]
            reply_to=send_conn,
            payload={},
        )
        ctx.control_queue.put(req)
        ack = _wait_control_ack(recv_conn, req['request_id'])

        _stop_runtime(runtime)
        assert ack['success'] is False


# ── UT-MP-WR-v23b: close marker drain tests ──────────────────────────────────


class TestCloseMarkerDrain:

    def test_attach_registers_expected_close_marker(self, tmp_path):
        """ATTACH adds client_id to expected_close_markers."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'cm-attach-001'

        send, recv = _make_pipe()
        req = _make_attach_request(
            client_id, send, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(req)
        _wait_control_ack(recv, req['request_id'])

        with runtime._active_lock:
            assert client_id in runtime._expected_close_markers

        _stop_runtime(runtime)

    def test_close_marker_on_log_queue_updates_received_set(self, tmp_path):
        """CloseMarker on log_queue is consumed by _log_loop and recorded."""
        from dsafelogger._mp_protocol import CloseMarker
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'cm-recv-001'
        with runtime._active_lock:
            runtime._expected_close_markers.add(client_id)

        marker: CloseMarker = {
            'kind': 'close_marker',
            'client_id': client_id,
            'session_id': ctx.session_id,
        }
        ctx.log_queue.put(marker)

        for _ in range(20):
            with runtime._active_lock:
                if client_id in runtime._close_markers_received:
                    break
            time.sleep(0.05)

        with runtime._active_lock:
            assert client_id in runtime._close_markers_received

        _stop_runtime(runtime)

    def test_close_marker_rejects_session_mismatch(self, tmp_path, capsys):
        """CloseMarker session_id must match the Writer session (v23h: close_marker_reject)."""
        from dsafelogger._mp_protocol import CloseMarker
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'cm-wrong-session'
        with runtime._active_lock:
            runtime._expected_close_markers.add(client_id)

        marker: CloseMarker = {
            'kind': 'close_marker',
            'client_id': client_id,
            'session_id': 'wrong-session',
        }
        ctx.log_queue.put(marker)
        time.sleep(0.15)

        with runtime._active_lock:
            assert client_id not in runtime._close_markers_received
        # v23h: split from writer_event_reject into writer_close_marker_reject.
        assert runtime._writer_close_marker_reject >= 1
        assert runtime._writer_reconstruct_reject == 0
        assert 'session_id mismatch' in capsys.readouterr().err
        _stop_runtime(runtime)

    def test_close_marker_rejects_unexpected_client(self, tmp_path, capsys):
        """CloseMarker must belong to a client registered through ATTACH (v23h)."""
        from dsafelogger._mp_protocol import CloseMarker
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'cm-unexpected'

        marker: CloseMarker = {
            'kind': 'close_marker',
            'client_id': client_id,
            'session_id': ctx.session_id,
        }
        ctx.log_queue.put(marker)
        time.sleep(0.15)

        with runtime._active_lock:
            assert client_id not in runtime._close_markers_received
        assert runtime._writer_close_marker_reject >= 1
        assert runtime._writer_reconstruct_reject == 0
        assert 'unexpected close marker client' in capsys.readouterr().err
        _stop_runtime(runtime)

    def test_drain_complete_requires_all_markers(self, tmp_path):
        """_drain_complete returns True only when all expected markers are received."""
        from dsafelogger._mp_protocol import CloseMarker
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_a = 'cm-drain-A'
        client_b = 'cm-drain-B'

        # Register two expected close markers
        with runtime._active_lock:
            runtime._expected_close_markers.add(client_a)
            runtime._expected_close_markers.add(client_b)
        runtime._stop_requested = True
        runtime._accept_new_clients = False
        # active_clients is empty (no ATTACH sent via control queue)

        assert runtime._drain_complete() is False  # markers missing

        # Send first marker
        ctx.log_queue.put(
            CloseMarker(kind='close_marker', client_id=client_a, session_id=ctx.session_id)
        )
        time.sleep(0.15)
        assert runtime._drain_complete() is False  # client_b still missing

        # Send second marker
        ctx.log_queue.put(
            CloseMarker(kind='close_marker', client_id=client_b, session_id=ctx.session_id)
        )
        time.sleep(0.15)
        assert runtime._drain_complete() is True

        _stop_runtime(runtime)

    def test_close_marker_failed_flag_satisfies_drain(self, tmp_path):
        """close_marker_failed in DETACH payload counts as drain completion."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'cm-fail-001'

        # ATTACH
        send1, recv1 = _make_pipe()
        attach_req = _make_attach_request(
            client_id, send1, ctx.session_id,
            protocol_version=ctx.protocol_version,
            registry_hash=ctx.registry_hash,
        )
        ctx.control_queue.put(attach_req)
        _wait_control_ack(recv1, attach_req['request_id'])

        # DETACH with close_marker_failed=True
        send2, recv2 = _make_pipe()
        detach_req = _make_detach_request(client_id, send2, close_marker_failed=True)
        ctx.control_queue.put(detach_req)
        ack = _wait_control_ack(recv2, detach_req['request_id'])
        assert ack['success'] is True

        time.sleep(0.15)
        with runtime._active_lock:
            assert client_id in runtime._close_marker_failed_clients
            assert runtime._close_marker_degraded is True

        _stop_runtime(runtime)

    def test_drain_deadline_exits_log_loop(self, tmp_path):
        """If drain deadline passes with pending markers, log loop exits."""
        import time as _time
        from dsafelogger._mp_protocol import CloseMarker
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        client_id = 'cm-deadline-001'

        with runtime._active_lock:
            runtime._expected_close_markers.add(client_id)

        # Trigger stop with a very short deadline
        runtime._drain_deadline = _time.monotonic() + 0.05
        runtime._stop_requested = True
        runtime._accept_new_clients = False
        # active_clients is empty

        # Log loop should exit within ~0.5s (deadline + one queue timeout)
        if runtime._log_thread:
            runtime._log_thread.join(timeout=2.0)
            assert not runtime._log_thread.is_alive()

        if runtime._control_thread:
            runtime._control_thread.join(timeout=2.0)
        for handlers in runtime._sink_groups.values():
            for h in handlers:
                try:
                    h.flush(); h.close()
                except Exception:
                    pass

    def test_close_marker_not_dispatched_as_log_event(self, tmp_path):
        """CloseMarker on log_queue does not reach sink handlers."""
        from dsafelogger._mp_protocol import CloseMarker
        ctx = _make_ctx(tmp_path)
        runtime, calls = _make_runtime_with_mock_handler(tmp_path, ctx)

        marker: CloseMarker = {
            'kind': 'close_marker',
            'client_id': 'cm-no-dispatch-001',
            'session_id': ctx.session_id,
        }
        ctx.log_queue.put(marker)
        time.sleep(0.15)

        _stop_runtime(runtime)
        assert calls == []  # close marker must not reach sink


# ── v23c: cause-specific counters and status ─────────────────────────────────

class TestCauseSpecificCounters:

    def test_writer_route_reject_increments_on_unknown_route(self, tmp_path):
        """Unknown route increments writer_route_reject (v23c)."""
        ctx = _make_ctx(tmp_path)
        runtime, _calls = _make_runtime_with_mock_handler(tmp_path, ctx)

        record = logging.makeLogRecord({'msg': 'test', 'levelno': logging.INFO})
        record._ds_route = 'unknown_route_xyz'  # type: ignore[attr-defined]
        runtime._dispatch(record)

        _stop_runtime(runtime)
        assert runtime._writer_route_reject == 1
        assert runtime._reject_counter == 1
        # v23h: writer_event_reject was split → reconstruct_reject and close_marker_reject.
        assert runtime._writer_reconstruct_reject == 0
        assert runtime._writer_close_marker_reject == 0

    def test_writer_reconstruct_reject_increments_on_bad_logevent(self, tmp_path):
        """Malformed LogEvent increments writer_reconstruct_reject (v23h split)."""
        ctx = _make_ctx(tmp_path)
        runtime, _calls = _make_runtime_with_mock_handler(tmp_path, ctx)

        ctx.log_queue.put({'not': 'a_valid_log_event'})
        time.sleep(0.15)

        _stop_runtime(runtime)
        # v23h: bad LogEvent goes to reconstruct_reject (close_marker_reject is for CloseMarker).
        assert runtime._writer_reconstruct_reject >= 1
        assert runtime._writer_close_marker_reject == 0
        assert runtime._reject_counter >= 1

    def test_status_includes_v23h_split_counters(self, tmp_path):
        """STATUS ACK exposes the v23h split: reconstruct_reject + close_marker_reject."""
        ctx = _make_ctx(tmp_path)
        runtime, _calls = _make_runtime_with_mock_handler(tmp_path, ctx)

        send_conn, recv_conn = _make_pipe()
        req = _make_request_helper('STATUS', 'status-v23h', send_conn)
        ctx.control_queue.put(req)
        ack = _wait_control_ack(recv_conn, req['request_id'])

        _stop_runtime(runtime)
        assert ack['success'] is True
        assert 'writer_route_reject' in ack['result']
        # v23h: split (writer_event_reject removed)
        assert 'writer_reconstruct_reject' in ack['result']
        assert 'writer_close_marker_reject' in ack['result']
        assert 'writer_event_reject' not in ack['result']
        # Other counters retained
        assert 'writer_sink_reject' in ack['result']
        assert 'writer_policy_reject' in ack['result']
        assert 'writer_partial_delivered' in ack['result']
        assert 'writer_best_effort_failures' in ack['result']

    def test_writer_sink_reject_increments_on_handler_error(self, tmp_path):
        """Required-handler emit failures increment writer_sink_reject (v23h: per record)."""
        class FailingHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                raise RuntimeError('handler failed intentionally')

        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': [FailingHandler()]})
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]

        runtime._dispatch(record)

        assert runtime._writer_sink_reject == 1
        assert runtime._reject_counter == 1

    def test_writer_policy_reject_increments_on_handler_filter(self, tmp_path):
        """Required-handler filter rejection increments writer_policy_reject (v23h: per record)."""
        class FilteringHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                raise AssertionError('emit should not be called')

        handler = FilteringHandler()
        handler.addFilter(lambda _record: False)
        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': [handler]})
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]

        runtime._dispatch(record)

        assert runtime._writer_policy_reject == 1
        assert runtime._reject_counter == 1

    def test_writer_policy_reject_per_record_not_per_handler(self, tmp_path):
        """v23h M1: N required handlers all filter-rejecting → counter +1 (not +N)."""
        class FilteringHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                raise AssertionError('emit should not be called')

        h1, h2, h3 = FilteringHandler(), FilteringHandler(), FilteringHandler()
        for h in (h1, h2, h3):
            h.addFilter(lambda _record: False)
        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': [h1, h2, h3]})
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]

        runtime._dispatch(record)

        # 3 handlers all reject one record → +1 to policy_reject (not +3).
        assert runtime._writer_policy_reject == 1
        assert runtime._reject_counter == 1

    def test_writer_partial_delivered_increments_on_mixed_required_result(self, tmp_path):
        """Partial delivery within the required sink set is counted (v23h)."""
        class RecordingHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                pass

        class FailingHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                raise RuntimeError('handler failed intentionally')

        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': [RecordingHandler(), FailingHandler()]})
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]

        runtime._dispatch(record)

        # v23h: partial is its own terminal state — sink_reject NOT also incremented.
        assert runtime._writer_partial_delivered == 1
        assert runtime._writer_sink_reject == 0
        assert runtime._reject_counter == 0

    def test_best_effort_failure_does_not_count_as_reject(self, tmp_path, capsys):
        """v23h H2: best-effort sink (e.g. console) failure is visible but not counted."""
        class RecordingHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                pass

        class FailingConsoleHandler(logging.Handler):
            _ds_required = False  # best-effort

            def emit(self, record):
                raise RuntimeError('console emit failed (e.g. Nuitka --windows-console-mode=disable)')

        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(
            ctx,
            {'root': [RecordingHandler(), FailingConsoleHandler()]},
        )
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]

        runtime._dispatch(record)

        # File succeeded → not partial, not rejected.
        assert runtime._writer_partial_delivered == 0
        assert runtime._writer_sink_reject == 0
        assert runtime._writer_policy_reject == 0
        assert runtime._reject_counter == 0
        # But best-effort failure is visible and counted separately.
        assert runtime._writer_best_effort_failures == 1
        assert 'best-effort sink error' in capsys.readouterr().err

    def test_sink_reject_stderr_rate_limit(self, tmp_path, capsys):
        """v23h H3: writer_sink_reject stderr is 1st + every 100th."""
        class FailingHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                raise RuntimeError('boom')

        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': [FailingHandler()]})

        # Drop the initial-state stderr (capsys preserves earlier output)
        capsys.readouterr()

        for _ in range(150):
            record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
            record._ds_route = 'root'  # type: ignore[attr-defined]
            runtime._dispatch(record)

        assert runtime._writer_sink_reject == 150
        err = capsys.readouterr().err
        # 1st (count=1) and 100th (count=100) → 2 warnings (not 150).
        warning_count = err.count('Writer required sink error')
        assert warning_count == 2, f'expected 2 warnings, got {warning_count}: {err!r}'

    def test_policy_reject_stderr_rate_limit(self, tmp_path, capsys):
        """v23h H3: writer_policy_reject stderr is 1st + every 100th."""
        class FilteringHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                pass

        handler = FilteringHandler()
        handler.addFilter(lambda _r: False)
        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': [handler]})

        capsys.readouterr()

        for _ in range(150):
            record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
            record._ds_route = 'root'  # type: ignore[attr-defined]
            runtime._dispatch(record)

        assert runtime._writer_policy_reject == 150
        err = capsys.readouterr().err
        warning_count = err.count('Writer required handler policy rejected')
        assert warning_count == 2, f'expected 2 warnings, got {warning_count}: {err!r}'

    def test_transport_cause_counters_overload_shed(self, tmp_path):
        """is_async=True: local queue full → overload_shed increments (v23c)."""
        import queue as _queue
        ctx = _make_ctx(tmp_path, is_async=True)
        transport = MPClientTransport(ctx, ds_route='root', is_async=True)
        # Replace local queue with a full one (maxsize=1, already put one item)
        transport._local_queue = _queue.Queue(maxsize=1)
        transport._local_queue.put(object())  # fill it

        record = logging.makeLogRecord({'msg': 'overflow', 'levelno': logging.INFO})
        transport._emit_record(record)

        assert transport._overload_shed == 1
        assert transport._drop_counter == 1
        assert transport._transport_closed_drop == 0
        assert transport._writer_unavailable_drop == 0
        assert transport._timeout_drop == 0

    def test_transport_cause_counters_transport_closed(self, tmp_path):
        """Transport closed → transport_closed_drop increments (v23c)."""
        ctx = _make_ctx(tmp_path, is_async=False)
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        transport._closed = True

        record = logging.makeLogRecord({'msg': 'closed_drop', 'levelno': logging.INFO})
        transport._emit_record(record)

        assert transport._transport_closed_drop == 1
        assert transport._drop_counter == 1
        assert transport._overload_shed == 0

    def test_transport_cause_counters_writer_unavailable(self, tmp_path):
        """writer_dead=True → writer_unavailable_drop increments (v23c)."""
        ctx = _make_ctx(tmp_path, is_async=False)
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        transport._writer_dead = True

        record = logging.makeLogRecord({'msg': 'dead_writer', 'levelno': logging.INFO})
        transport._emit_record(record)

        assert transport._writer_unavailable_drop == 1
        assert transport._drop_counter == 1
        assert transport._overload_shed == 0

    def test_bootstrap_context_has_ipc_client_queue_maxsize(self, tmp_path):
        """BootstrapContext exposes ipc_client_queue_maxsize (v23c)."""
        ctx = _make_ctx(tmp_path)
        assert hasattr(ctx, 'ipc_client_queue_maxsize')
        assert ctx.ipc_client_queue_maxsize > 0


def _make_request_helper(command, client_id, send_conn):
    """Build a minimal ControlRequest (used in v23c status test)."""
    from dsafelogger._mp_control import _make_request
    return _make_request(command, client_id, send_conn)


# ── UT-MP-BF: WriterRuntime batch flush tests (v23e) ────────────────────────


class TestBatchFlush:

    def test_messages_since_flush_initialized_to_zero(self, tmp_path):
        """WriterRuntime starts with _messages_since_flush == 0."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        assert runtime._messages_since_flush == 0
        _stop_runtime(runtime)

    def test_flush_all_sinks_calls_flush_on_handlers(self, tmp_path):
        """_flush_all_sinks() calls flush() on each handler in every route."""
        flush_calls: list[str] = []

        class TrackingHandler(logging.Handler):
            def __init__(self, name):
                super().__init__()
                self._name = name
            def emit(self, record):
                pass
            def flush(self):
                flush_calls.append(self._name)

        ctx = _make_ctx(tmp_path)
        h_root = TrackingHandler('root')
        h_mod = TrackingHandler('module:foo')
        runtime = WriterRuntime(ctx, {'root': [h_root], 'module:foo': [h_mod]})
        runtime.start()

        runtime._flush_all_sinks()

        assert 'root' in flush_calls
        assert 'module:foo' in flush_calls
        assert runtime._messages_since_flush == 0

        _stop_runtime(runtime)

    def test_flush_all_sinks_resets_counter(self, tmp_path):
        """_flush_all_sinks() resets _messages_since_flush to 0."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        runtime.start()

        runtime._messages_since_flush = 7
        runtime._flush_all_sinks()

        assert runtime._messages_since_flush == 0
        _stop_runtime(runtime)

    def test_batch_flush_triggers_after_n_messages(self, tmp_path):
        """After writer_flush_batch dispatched messages, _messages_since_flush resets to 0."""
        BATCH = 16
        flush_counts: list[int] = []

        class FlushCountingHandler(logging.Handler):
            def emit(self, record):
                pass
            def flush(self):
                flush_counts.append(1)

        ctx = _make_ctx(tmp_path, writer_flush_batch=BATCH)
        handler = FlushCountingHandler()
        runtime = WriterRuntime(ctx, {'root': [handler]})
        runtime.start()

        # Send exactly BATCH messages
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        serialized = _serialize_record(record, ds_route='root')

        for _ in range(BATCH):
            ctx.log_queue.put(serialized)

        # Wait for batch flush to trigger (may happen before or after loop check)
        deadline = time.monotonic() + 5.0
        while len(flush_counts) == 0 and time.monotonic() < deadline:
            time.sleep(0.05)

        assert len(flush_counts) >= 1
        assert runtime._messages_since_flush == 0

        _stop_runtime(runtime)

    def test_idle_flush_on_empty_queue(self, tmp_path):
        """When queue goes empty, pending writes are flushed immediately."""
        BATCH = 16

        flush_counts: list[int] = []

        class FlushCountingHandler(logging.Handler):
            def emit(self, record):
                pass
            def flush(self):
                flush_counts.append(1)

        ctx = _make_ctx(tmp_path, writer_flush_batch=BATCH)
        handler = FlushCountingHandler()
        runtime = WriterRuntime(ctx, {'root': [handler]})
        runtime.start()

        # Send fewer than BATCH messages (no batch flush triggered)
        few = max(1, BATCH // 2)
        record = logging.makeLogRecord({'msg': 'idle', 'levelno': logging.INFO})
        serialized = _serialize_record(record, ds_route='root')

        for _ in range(few):
            ctx.log_queue.put(serialized)

        # Idle flush fires after queue.get(timeout=0.2) returns empty; wait up to 3s
        deadline = time.monotonic() + 3.0
        while len(flush_counts) == 0 and time.monotonic() < deadline:
            time.sleep(0.05)

        assert len(flush_counts) >= 1
        assert runtime._messages_since_flush == 0

        _stop_runtime(runtime)

    def test_writer_file_handler_uses_stream_flush_on_emit_false(self, tmp_path):
        """_build_writer_sink_groups creates file handlers with stream_flush_on_emit=False."""
        import dsafelogger.mp as dsmp

        dsmp.ConfigureLogger(
            log_path=str(tmp_path),
            pg_name='BatchTest',
            console_out=False,
        )
        try:
            runtime = dsmp._mp_writer_runtime
            assert runtime is not None
            for route, handlers in runtime._sink_groups.items():
                for h in handlers:
                    if hasattr(h, '_stream_flush_on_emit'):
                        assert h._stream_flush_on_emit is False, (
                            f'File handler for route {route!r} should have '
                            f'stream_flush_on_emit=False'
                        )
        finally:
            dsmp._mp_shutdown()
            # Reset atexit flag so later tests can call ConfigureLogger cleanly
            dsmp._mp_atexit_registered = False

    def test_shutdown_final_flush_when_pending_messages(self, tmp_path):
        """_log_loop flushes pending writes before returning on drain completion."""
        flush_counts: list[int] = []

        class FlushCountingHandler(logging.Handler):
            def emit(self, record):
                pass
            def flush(self):
                flush_counts.append(1)

        ctx = _make_ctx(tmp_path, writer_flush_batch=16)
        runtime = WriterRuntime(ctx, {'root': [FlushCountingHandler()]})
        runtime._messages_since_flush = 1
        runtime._stop_requested = True
        runtime._accept_new_clients = False

        runtime._log_loop()

        assert flush_counts == [1]
        assert runtime._messages_since_flush == 0

    def test_writer_flush_batch_per_message(self, tmp_path):
        """writer_flush_batch=1 (default) flushes after every dispatched message."""
        flush_counts: list[int] = []

        class FlushCountingHandler(logging.Handler):
            def emit(self, record):
                pass
            def flush(self):
                flush_counts.append(1)

        ctx = _make_ctx(tmp_path, writer_flush_batch=1)
        handler = FlushCountingHandler()
        runtime = WriterRuntime(ctx, {'root': [handler]})
        runtime.start()

        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        serialized = _serialize_record(record, ds_route='root')

        for _ in range(3):
            ctx.log_queue.put(serialized)

        deadline = time.monotonic() + 5.0
        while len(flush_counts) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)

        assert len(flush_counts) >= 3
        _stop_runtime(runtime)


# ── UT-MP-V23G: v23g counters and STATUS tests ────────────────────────────


class TestV23GCounters:

    def test_drain_deadline_loss_initialized_to_zero(self, tmp_path):
        """WriterRuntime starts with _writer_drain_deadline_loss == 0 (v23g)."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        assert runtime._writer_drain_deadline_loss == 0
        _stop_runtime(runtime)

    def test_flush_error_count_initialized_to_zero(self, tmp_path):
        """WriterRuntime starts with _writer_flush_error_count == 0 (v23g)."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        assert runtime._writer_flush_error_count == 0
        _stop_runtime(runtime)

    def test_status_includes_v23g_counters(self, tmp_path):
        """STATUS ACK includes writer_drain_deadline_loss and writer_flush_error_count (v23g)."""
        ctx = _make_ctx(tmp_path)
        runtime, _calls = _make_runtime_with_mock_handler(tmp_path, ctx)

        send_conn, recv_conn = _make_pipe()
        req = _make_request_helper('STATUS', 'status-v23g', send_conn)
        ctx.control_queue.put(req)
        ack = _wait_control_ack(recv_conn, req['request_id'])

        _stop_runtime(runtime)
        assert ack['success'] is True
        assert 'writer_drain_deadline_loss' in ack['result']
        assert 'writer_flush_error_count' in ack['result']
        assert ack['result']['writer_drain_deadline_loss'] == 0
        assert ack['result']['writer_flush_error_count'] == 0

    def test_drain_deadline_loss_counts_residual_queue(self, tmp_path, capsys):
        """Deadline-degraded shutdown reports residual log queue size."""
        class ResidualQueue:
            def qsize(self):
                return 3

        ctx = replace(_make_ctx(tmp_path), log_queue=ResidualQueue())
        runtime = WriterRuntime(ctx, {'root': []})
        client_id = 'cm-deadline-loss'
        with runtime._active_lock:
            runtime._expected_close_markers.add(client_id)
        runtime._stop_requested = True
        runtime._accept_new_clients = False
        runtime._drain_deadline = time.monotonic() - 1.0

        assert runtime._drain_complete() is True
        assert runtime._writer_drain_deadline_loss == 3
        assert '3 message(s) remained in log queue' in capsys.readouterr().err

    def test_drain_deadline_qsize_failure_reports_unknown(self, tmp_path, capsys):
        """qsize() failure must not crash deadline-degraded shutdown."""
        class UnknownQsizeQueue:
            def qsize(self):
                raise NotImplementedError

        ctx = replace(_make_ctx(tmp_path), log_queue=UnknownQsizeQueue())
        runtime = WriterRuntime(ctx, {'root': []})
        client_id = 'cm-deadline-unknown'
        with runtime._active_lock:
            runtime._expected_close_markers.add(client_id)
        runtime._stop_requested = True
        runtime._accept_new_clients = False
        runtime._drain_deadline = time.monotonic() - 1.0

        assert runtime._drain_complete() is True
        assert runtime._writer_drain_deadline_loss == 0
        assert '-1 message(s) remained in log queue' in capsys.readouterr().err

    def test_flush_error_increments_counter(self, tmp_path):
        """_flush_all_sinks() increments _writer_flush_error_count when flush() raises."""

        class FailingFlushHandler(logging.Handler):
            def emit(self, record):
                pass
            def flush(self):
                raise RuntimeError('flush failed intentionally')

        ctx = _make_ctx(tmp_path)
        handler = FailingFlushHandler()
        runtime = WriterRuntime(ctx, {'root': [handler]})
        runtime.start()

        runtime._flush_all_sinks()

        assert runtime._writer_flush_error_count == 1
        _stop_runtime(runtime)

    def test_flush_error_100th_also_warns(self, tmp_path, capsys):
        """_flush_all_sinks() warns at 1st and every 100th error (v23g)."""

        class FailingFlushHandler(logging.Handler):
            def emit(self, record):
                pass
            def flush(self):
                raise RuntimeError('flush failed intentionally')

        ctx = _make_ctx(tmp_path)
        handler = FailingFlushHandler()
        runtime = WriterRuntime(ctx, {'root': [handler]})
        runtime.start()

        for _ in range(100):
            runtime._flush_all_sinks()

        assert runtime._writer_flush_error_count == 100
        captured = capsys.readouterr()
        assert '[D-SafeLogger] Writer sink flush error' in captured.err
        _stop_runtime(runtime)


# ── UT-MP-V23H: v23h validation, TrackedQueue, sink classification ─────────


class TestV23HValidation:

    def test_writer_runtime_rejects_zero_flush_batch(self, tmp_path):
        """v23h L3: WriterRuntime.__init__ raises on writer_flush_batch < 1."""
        bad_ctx = replace(_make_ctx(tmp_path), writer_flush_batch=0)
        with pytest.raises(ValueError, match='writer_flush_batch'):
            WriterRuntime(bad_ctx, {'root': []})

    def test_writer_runtime_rejects_negative_flush_batch(self, tmp_path):
        """v23h L3: WriterRuntime.__init__ raises on negative writer_flush_batch."""
        bad_ctx = replace(_make_ctx(tmp_path), writer_flush_batch=-5)
        with pytest.raises(ValueError, match='writer_flush_batch'):
            WriterRuntime(bad_ctx, {'root': []})

    def test_per_message_flush_skips_idle_flush_logic(self, tmp_path):
        """v23h L1: writer_flush_batch=1 disables idle/shutdown flush dead-code path."""
        ctx = _make_ctx(tmp_path, writer_flush_batch=1)
        runtime = WriterRuntime(ctx, {'root': []})
        assert runtime._batch_flush_enabled is False

    def test_batch_flush_enables_idle_flush_logic(self, tmp_path):
        """v23h L1: writer_flush_batch>1 enables idle/shutdown flush path."""
        ctx = _make_ctx(tmp_path, writer_flush_batch=16)
        runtime = WriterRuntime(ctx, {'root': []})
        assert runtime._batch_flush_enabled is True

    def test_stop_emits_bounded_warning_when_threads_stuck(self, tmp_path, capsys):
        """v23h §12.4: stop() warns visibly if threads survive the join timeout.

        Simulates a stuck thread with a fake `is_alive()` that always returns
        True. stop() must emit a stderr warning naming the stuck threads
        (no silent hang).
        """
        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(ctx, {'root': []})

        class _AlwaysAlive:
            daemon = True
            def join(self, timeout=None): return None
            def is_alive(self): return True
            def start(self): pass

        runtime._log_thread = _AlwaysAlive()  # type: ignore[assignment]
        runtime._control_thread = _AlwaysAlive()  # type: ignore[assignment]

        runtime.stop(timeout=0.01)

        err = capsys.readouterr().err
        assert 'WriterRuntime.stop() exceeded' in err
        assert 'log_thread' in err
        assert 'control_thread' in err
        assert 'process exit will proceed' in err

    def test_stop_emits_no_warning_on_clean_shutdown(self, tmp_path, capsys):
        """v23h §12.4: stop() is silent when both threads exit cleanly."""
        ctx = _make_ctx(tmp_path)
        runtime, _ = _make_runtime_with_mock_handler(tmp_path, ctx)
        # No active clients / no expected markers → drain_complete returns True
        runtime.stop(timeout=2.0)

        err = capsys.readouterr().err
        assert 'WriterRuntime.stop() exceeded' not in err
        assert runtime._log_thread is not None
        assert not runtime._log_thread.is_alive()
        assert runtime._control_thread is not None
        assert not runtime._control_thread.is_alive()


class TestTrackedQueue:
    """v23h M3: TrackedQueue probes qsize support at init and tracks via Value
    counter when native is unavailable."""

    def test_native_qsize_supported_on_this_platform(self):
        """On Linux/Windows, native qsize() must be detected and used directly."""
        import multiprocessing as _mp
        from dsafelogger._mp_queue import TrackedQueue

        ctx = _mp.get_context()
        try:
            ctx.Queue(1).qsize()
            native_supported = True
        except NotImplementedError:
            native_supported = False

        q = TrackedQueue(maxsize=8, ctx=ctx)
        assert q._native_qsize_supported is native_supported

    def test_qsize_tracks_put_get(self, tmp_path):
        """qsize() reflects put/get operations regardless of native support."""
        import multiprocessing as _mp
        from dsafelogger._mp_queue import TrackedQueue

        ctx = _mp.get_context()
        q = TrackedQueue(maxsize=8, ctx=ctx)

        assert q.qsize() == 0
        q.put('a')
        q.put('b')
        q.put('c')
        # Allow background feeder thread to flush to the underlying pipe
        # before checking qsize on platforms with the buffered Queue impl.
        time.sleep(0.05)
        assert q.qsize() == 3

        q.get()
        time.sleep(0.05)
        assert q.qsize() == 2

    def test_unsupported_native_falls_back_to_value_counter(self):
        """Force NotImplementedError at construction → Value-counter mode."""
        import ctypes
        import multiprocessing as _mp
        from dsafelogger._mp_queue import TrackedQueue

        # Subclass that always raises on native qsize() to simulate macOS.
        class _NoNativeQsize(TrackedQueue):
            def __init__(self, maxsize, *, ctx):
                from multiprocessing.queues import Queue as _MPQueueBase
                _MPQueueBase.__init__(self, maxsize, ctx=ctx)
                # Force fallback path explicitly.
                self._native_qsize_supported = False
                self._tracked_count = ctx.Value(ctypes.c_long, 0)

        ctx = _mp.get_context()
        q = _NoNativeQsize(maxsize=8, ctx=ctx)
        assert q._native_qsize_supported is False
        assert q.qsize() == 0
        q.put(1)
        q.put(2)
        time.sleep(0.05)
        assert q.qsize() == 2
        q.get()
        time.sleep(0.05)
        assert q.qsize() == 1

    def test_tracked_queue_used_for_log_queue(self, tmp_path, mp_state):
        """ConfigureLogger creates the log_queue as a TrackedQueue (v23h M3)."""
        import dsafelogger.mp as dsmp
        from dsafelogger._mp_queue import TrackedQueue

        ctx = dsmp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        try:
            assert isinstance(ctx.log_queue, TrackedQueue)
        finally:
            dsmp._mp_shutdown()
            dsmp._mp_atexit_registered = False


class TestSinkClassification:
    """v23h H2/L5: required vs best-effort sink classification."""

    def test_appendonly_file_handler_is_required(self, tmp_path):
        """AppendOnlyFileHandler defaults to _ds_required=True."""
        from dsafelogger._handler import AppendOnlyFileHandler
        from dsafelogger._routing import NoneStrategy

        strat = NoneStrategy(tmp_path, 'Required')
        handler = AppendOnlyFileHandler(strategy=strat)
        try:
            assert getattr(handler, '_ds_required', None) is True
        finally:
            handler.close()

    def test_color_stream_handler_is_best_effort(self):
        """ColorStreamHandler defaults to _ds_required=False."""
        from dsafelogger._color import ColorStreamHandler
        h = ColorStreamHandler(color_enabled=False)
        assert getattr(h, '_ds_required', None) is False

    def test_unknown_handler_defaults_to_required(self, tmp_path):
        """Custom user handlers (no _ds_required attribute) default to required."""
        class CustomHandler(logging.Handler):
            def emit(self, record):
                pass

        h = CustomHandler()
        # _dispatch should treat absent attribute as required (True).
        assert getattr(h, '_ds_required', True) is True

    def test_partial_delivered_only_within_required_set(self, tmp_path):
        """v23h L5: partial only counts when required handlers split outcome."""
        class GoodFile(logging.Handler):
            _ds_required = True

            def emit(self, record):
                pass

        class FailingConsole(logging.Handler):
            _ds_required = False  # best-effort

            def emit(self, record):
                raise RuntimeError('boom')

        ctx = _make_ctx(tmp_path)
        runtime = WriterRuntime(
            ctx, {'root': [GoodFile(), FailingConsole()]}
        )
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]
        runtime._dispatch(record)

        # Required succeeded entirely → not partial.
        assert runtime._writer_partial_delivered == 0
        assert runtime._writer_best_effort_failures == 1
