"""Tests for control plane helpers (UT-MP-WR control plane / ACK timeout).

Covers:
    _send_control_request, _wait_control_ack, _raise_for_failed_ack
    _make_* request builders
"""
from __future__ import annotations

import uuid

import pytest

from dsafelogger._mp_control import (
    CONTROL_PLANE_ACK_TIMEOUT_SEC,
    _make_attach_request,
    _make_detach_request,
    _make_pipe,
    _make_reopen_request,
    _make_stop_request,
    _raise_for_failed_ack,
    _send_control_request,
    _wait_control_ack,
)
from dsafelogger._mp_protocol import ControlAck


# ── _wait_control_ack ─────────────────────────────────────────────────────────

class TestWaitControlAck:

    def test_returns_ack_when_available(self):
        send_conn, recv_conn = _make_pipe()
        request_id = uuid.uuid4().hex
        ack = ControlAck(
            request_id=request_id,
            success=True,
            error_category=None,
            error_message=None,
            result={},
        )
        send_conn.send(ack)
        result = _wait_control_ack(recv_conn, request_id)
        assert result['success'] is True
        assert result['request_id'] == request_id

    def test_timeout_raises_timeout_error(self):
        """Empty pipe causes TimeoutError after the timeout expires."""
        send_conn, recv_conn = _make_pipe()
        request_id = uuid.uuid4().hex
        # Use a very short timeout by patching the constant
        import dsafelogger._mp_control as ctrl_mod
        original = ctrl_mod.CONTROL_PLANE_ACK_TIMEOUT_SEC
        ctrl_mod.CONTROL_PLANE_ACK_TIMEOUT_SEC = 0.2
        try:
            with pytest.raises(TimeoutError, match='Control plane ACK timed out'):
                _wait_control_ack(recv_conn, request_id)
        finally:
            ctrl_mod.CONTROL_PLANE_ACK_TIMEOUT_SEC = original

    def test_mismatched_request_id_raises_runtime_error(self):
        send_conn, recv_conn = _make_pipe()
        request_id = uuid.uuid4().hex
        wrong_id = uuid.uuid4().hex
        ack = ControlAck(
            request_id=wrong_id,
            success=True,
            error_category=None,
            error_message=None,
            result={},
        )
        send_conn.send(ack)
        with pytest.raises(RuntimeError, match='mismatch'):
            _wait_control_ack(recv_conn, request_id)

    def test_closed_pipe_raises_runtime_error(self):
        send_conn, recv_conn = _make_pipe()
        send_conn.close()
        with pytest.raises(RuntimeError, match='failed to receive control ACK'):
            _wait_control_ack(recv_conn, uuid.uuid4().hex)


# ── _raise_for_failed_ack ─────────────────────────────────────────────────────

class TestRaiseForFailedAck:

    def test_success_ack_does_not_raise(self):
        ack = ControlAck(
            request_id='r1', success=True,
            error_category=None, error_message=None, result={},
        )
        _raise_for_failed_ack(ack)  # must not raise

    def test_timeout_category_raises_timeout_error(self):
        ack = ControlAck(
            request_id='r1', success=False,
            error_category='timeout', error_message='timed out', result={},
        )
        with pytest.raises(TimeoutError, match='timed out'):
            _raise_for_failed_ack(ack)

    def test_validation_category_raises_value_error(self):
        ack = ControlAck(
            request_id='r1', success=False,
            error_category='validation', error_message='bad value', result={},
        )
        with pytest.raises(ValueError, match='bad value'):
            _raise_for_failed_ack(ack)

    def test_runtime_category_raises_runtime_error(self):
        ack = ControlAck(
            request_id='r1', success=False,
            error_category='runtime', error_message='runtime failure', result={},
        )
        with pytest.raises(RuntimeError, match='runtime failure'):
            _raise_for_failed_ack(ack)

    def test_unknown_category_raises_runtime_error(self):
        ack = ControlAck(
            request_id='r1', success=False,
            error_category='unknown_category', error_message='oops', result={},
        )
        with pytest.raises(RuntimeError, match='oops'):
            _raise_for_failed_ack(ack)

    def test_no_message_uses_fallback(self):
        ack = ControlAck(
            request_id='r1', success=False,
            error_category='runtime', error_message=None, result={},
        )
        with pytest.raises(RuntimeError):
            _raise_for_failed_ack(ack)


# ── Request builders ──────────────────────────────────────────────────────────

class TestRequestBuilders:

    def test_make_attach_request_fields(self):
        send_conn, _ = _make_pipe()
        req = _make_attach_request(
            'client-1', send_conn, 'session-abc',
            protocol_version=1, registry_hash='hash-abc',
        )
        assert req['command'] == 'ATTACH'
        assert req['client_id'] == 'client-1'
        assert req['payload']['session_id'] == 'session-abc'
        assert req['payload']['protocol_version'] == 1
        assert req['payload']['registry_hash'] == 'hash-abc'
        assert 'pid' in req['payload']

    def test_make_detach_request_fields(self):
        send_conn, _ = _make_pipe()
        req = _make_detach_request('client-2', send_conn)
        assert req['command'] == 'DETACH'

    def test_make_reopen_request_fields(self):
        send_conn, _ = _make_pipe()
        req = _make_reopen_request('client-3', send_conn)
        assert req['command'] == 'REOPEN'

    def test_make_stop_request_fields(self):
        send_conn, _ = _make_pipe()
        req = _make_stop_request('client-4', send_conn)
        assert req['command'] == 'STOP'

    def test_request_has_unique_request_id(self):
        send_conn, _ = _make_pipe()
        r1 = _make_attach_request('c', send_conn, 's', protocol_version=1, registry_hash='h')
        r2 = _make_attach_request('c', send_conn, 's', protocol_version=1, registry_hash='h')
        assert r1['request_id'] != r2['request_id']
