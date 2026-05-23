"""Tests for mp.GetDeliveryStatus() public API."""
from __future__ import annotations

import logging

import pytest

import dsafelogger.mp as mp


def _assert_writer_invariant(status: mp.DeliveryStatus) -> None:
    assert status['accepted'] == (
        status['delivered']
        + status['partial_delivered']
        + status['known_rejected']
        + sum(status['writer_drop_breakdown'].values())
        + status['unexplained_lost']
    )


class TestGetDeliveryStatus:

    def test_before_configure_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match='multiprocess runtime is not configured'):
            mp.GetDeliveryStatus()

    def test_normal_status_shape(self, tmp_path, mp_state):
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

        status = mp.GetDeliveryStatus()

        assert status['schema_version'] == 1
        assert status['session_id'] == ctx.session_id
        assert status['writer_pid'] == ctx.writer_pid
        assert isinstance(status, dict)

    def test_public_contract_fields_are_present(self, tmp_path, mp_state):
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

        status = mp.GetDeliveryStatus()

        for key in (
            'attempted',
            'accepted',
            'delivered',
            'partial_delivered',
            'known_rejected',
            'known_dropped',
            'unexplained_lost',
        ):
            assert key in status

    def test_breakdown_keys_are_present(self, tmp_path, mp_state):
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

        status = mp.GetDeliveryStatus()

        assert set(status['writer_reject_breakdown']) == {
            'writer_route_reject',
            'writer_reconstruct_reject',
            'writer_close_marker_reject',
            'writer_sink_reject',
            'writer_policy_reject',
        }
        assert set(status['worker_drop_breakdown']) == {
            'worker_overload_shed',
            'worker_transport_closed_drop',
            'worker_writer_unavailable_drop',
            'worker_timeout_drop',
        }
        assert set(status['writer_drop_breakdown']) == {'writer_drain_deadline_loss'}
        assert 'writer_drain_deadline_loss' not in status['worker_drop_breakdown']

    def test_ack_timeout_propagates_timeout_error(self, tmp_path, mp_state, monkeypatch):
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

        def raise_timeout(*_args, **_kwargs):
            raise TimeoutError('status timeout')

        monkeypatch.setattr(mp, '_wait_control_ack', raise_timeout)

        with pytest.raises(TimeoutError, match='status timeout'):
            mp.GetDeliveryStatus()

    def test_active_client_snapshot_is_incomplete(self, tmp_path, mp_state):
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

        status = mp.GetDeliveryStatus()

        assert status['active_clients'] > 0
        assert status['snapshot_complete'] is False
        assert status['missing_detach_clients'] == 0
        assert 'missing_detach_client_ids' not in status
        assert 'missing_detach_pids' not in status

    def test_runtime_status_missing_detach_zero_even_with_stale_clients(
        self, tmp_path, mp_state
    ):
        """Runtime STATUS does not classify active/stale clients as crashed."""
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        runtime = mp._mp_writer_runtime
        assert runtime is not None
        with runtime._active_lock:
            runtime._active_clients['stale-worker'] = {
                'pid': 99999,
                'session_id': runtime._ctx.session_id,
            }

        status = mp.GetDeliveryStatus()

        assert status['missing_detach_clients'] == 0
        assert status['active_clients'] >= 2
        assert status['snapshot_complete'] is False

    def test_sink_reject_is_reported(self, tmp_path, mp_state):
        class FailingHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                raise RuntimeError('sink failed intentionally')

        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        runtime = mp._mp_writer_runtime
        assert runtime is not None
        runtime._sink_groups['root'] = [FailingHandler()]
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]
        runtime._accepted += 1
        runtime._dispatch(record)

        status = mp.GetDeliveryStatus()

        assert status['known_rejected'] == 1
        assert status['writer_reject_breakdown']['writer_sink_reject'] == 1

    def test_partial_delivery_is_independent(self, tmp_path, mp_state):
        class GoodHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                pass

        class FailingHandler(logging.Handler):
            _ds_required = True

            def emit(self, record):
                raise RuntimeError('sink failed intentionally')

        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        runtime = mp._mp_writer_runtime
        assert runtime is not None
        runtime._sink_groups['root'] = [GoodHandler(), FailingHandler()]
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'root'  # type: ignore[attr-defined]
        runtime._accepted += 1
        runtime._dispatch(record)

        status = mp.GetDeliveryStatus()

        assert status['partial_delivered'] == 1
        assert status['delivered'] == 0
        assert status['known_rejected'] == 0

    def test_snapshot_complete_after_detach(self, tmp_path, mp_state):
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        mp.DetachCurrentProcess()

        status = mp.GetDeliveryStatus()

        assert status['active_clients'] == 0
        assert status['snapshot_complete'] is True

    def test_stopped_writer_raises_runtime_error(self, tmp_path, mp_state):
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        runtime = mp._mp_writer_runtime
        assert runtime is not None
        runtime.stop(timeout=1.0)

        with pytest.raises(RuntimeError, match='writer runtime has stopped'):
            mp.GetDeliveryStatus()

    def test_writer_side_invariant_when_complete(self, tmp_path, mp_state):
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        runtime = mp._mp_writer_runtime
        assert runtime is not None
        runtime._accepted = 4
        runtime._delivered = 1
        runtime._writer_partial_delivered = 1
        runtime._writer_sink_reject = 1
        runtime._writer_drain_deadline_loss = 1
        mp.DetachCurrentProcess()

        status = mp.GetDeliveryStatus()

        assert status['snapshot_complete'] is True
        _assert_writer_invariant(status)
