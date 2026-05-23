"""Tests for multiprocess shutdown report JSON output."""
from __future__ import annotations

import json
import logging
import os

import pytest

import dsafelogger.mp as mp
from dsafelogger._mp_protocol import BootstrapContext
from dsafelogger._mp_runtime import WriterRuntime
from dsafelogger._shutdown_report import ShutdownReportWriter


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _make_ctx(tmp_path, *, report_path=None, warning_path=None):
    import multiprocessing as _mp

    resolved_config: dict[str, object] = {
        'is_async': False,
        'log_level': 'DEBUG',
        'module_routes': [],
        'module_levels': {},
        'mp_start_method': _mp.get_context().get_start_method(),
        'runtime_warning_path': str(warning_path) if warning_path else None,
        'shutdown_report_path': str(report_path) if report_path else None,
    }
    return BootstrapContext(
        protocol_version=1,
        session_id='test-session',
        writer_pid=os.getpid(),
        log_queue=_mp.get_context().Queue(100),
        control_queue=_mp.get_context().Queue(100),
        resolved_config=resolved_config,
        resolved_config_digest='test',
        registry_hash='test_hash',
        log_queue_maxsize=100,
        ipc_client_queue_maxsize=100,
        writer_flush_batch=1,
        ipc_log_timeout=0.01,
        overflow_policy='drop',
    )


def _make_runtime(tmp_path, *, report_path=None, warning_path=None):
    ctx = _make_ctx(tmp_path, report_path=report_path, warning_path=warning_path)
    return WriterRuntime(ctx, {'root': [logging.NullHandler()]})


def _assert_writer_invariant(report):
    assert report['accepted'] == (
        report['delivered']
        + report['partial_delivered']
        + report['known_rejected']
        + sum(report['writer_drop_breakdown'].values())
        + report['unexplained_lost']
    )


class TestShutdownReportWriter:

    def test_atomic_write_replaces_existing_file(self, tmp_path):
        path = tmp_path / 'shutdown-report.json'
        path.write_text('{"old": true}\n', encoding='utf-8')

        ShutdownReportWriter(path).write({'schema_version': 1, 'value': 'new'})

        assert _read_json(path) == {'schema_version': 1, 'value': 'new'}
        assert not list(tmp_path.glob('.shutdown-report.json.*.tmp'))

    def test_replace_failure_cleans_temp_file(self, tmp_path, monkeypatch):
        import dsafelogger._shutdown_report as report_mod

        path = tmp_path / 'shutdown-report.json'

        def fail_replace(_src, _dst):
            raise PermissionError('target open')

        monkeypatch.setattr(report_mod.os, 'replace', fail_replace)

        with pytest.raises(PermissionError):
            ShutdownReportWriter(path).write({'schema_version': 1})
        assert not list(tmp_path.glob('.shutdown-report.json.*.tmp'))


class TestShutdownReportRuntime:

    def test_no_shutdown_report_path_writes_nothing(self, tmp_path):
        runtime = _make_runtime(tmp_path)

        runtime.stop(timeout=0.01)

        assert not list(tmp_path.glob('*.json'))

    def test_clean_shutdown_report_has_required_fields(self, tmp_path):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        required = {
            'schema_version',
            'session_id',
            'writer_pid',
            'started_at',
            'stopped_at',
            'duration_sec',
            'active_clients_peak',
            'attempted',
            'accepted',
            'delivered',
            'partial_delivered',
            'known_rejected',
            'known_dropped',
            'unexplained_lost',
            'writer_reject_breakdown',
            'worker_drop_breakdown',
            'writer_drop_breakdown',
            'best_effort_failures',
            'flush_error_count',
            'worker_crash_observed',
            'missing_detach_clients',
            'missing_detach_client_ids',
            'missing_detach_pids',
            'snapshot_complete',
            'warning_queue_drain_incomplete',
            'shutdown_result',
        }
        assert required <= set(report)
        assert report['shutdown_result'] == 'clean'
        assert report['snapshot_complete'] is True
        assert report['worker_crash_observed'] is False

    def test_configure_logger_shutdown_report_path_writes_on_shutdown(
        self, tmp_path, mp_state
    ):
        report_path = tmp_path / 'shutdown-report.json'

        mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            shutdown_report_path=str(report_path),
        )
        mp._mp_shutdown()

        report = _read_json(report_path)
        assert report['shutdown_result'] == 'clean'
        assert report['session_id']

    def test_shutdown_report_path_parent_must_exist(self, tmp_path, mp_state):
        report_path = tmp_path / 'missing' / 'shutdown-report.json'

        with pytest.raises(ValueError, match='shutdown_report_path parent'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                shutdown_report_path=str(report_path),
            )

    def test_worker_crash_report_includes_missing_client_identity(self, tmp_path):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        with runtime._active_lock:
            runtime._active_clients['client-a'] = {
                'pid': 12345,
                'session_id': runtime._ctx.session_id,
            }
            runtime._active_clients_peak = 1

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        assert report['worker_crash_observed'] is True
        assert report['missing_detach_clients'] == 1
        assert report['missing_detach_client_ids'] == ['client-a']
        assert report['missing_detach_pids'] == [12345]
        assert report['snapshot_complete'] is False
        assert report['shutdown_result'] == 'clean_with_worker_crash'

    def test_drain_deadline_exceeded_report(self, tmp_path):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        runtime._drain_deadline_exceeded = True

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        assert report['shutdown_result'] == 'drain_deadline_exceeded'
        assert report['snapshot_complete'] is False

    def test_report_write_failure_falls_back_to_warning_and_stderr(
        self, tmp_path, monkeypatch, capsys
    ):
        import dsafelogger._shutdown_report as report_mod

        report_path = tmp_path / 'shutdown-report.json'
        warning_path = tmp_path / 'runtime-warning.jsonl'
        runtime = _make_runtime(
            tmp_path,
            report_path=report_path,
            warning_path=warning_path,
        )

        def fail_replace(_src, _dst):
            raise PermissionError('target open')

        monkeypatch.setattr(report_mod.os, 'replace', fail_replace)

        runtime.stop(timeout=0.01)

        assert 'shutdown report write failed' in capsys.readouterr().err
        warning_rows = [
            json.loads(line)
            for line in warning_path.read_text(encoding='utf-8').splitlines()
        ]
        assert warning_rows[0]['event'] == 'shutdown_report_write_error'

    def test_writer_side_invariant_is_preserved(self, tmp_path):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        runtime._accepted = 4
        runtime._delivered = 1
        runtime._writer_partial_delivered = 1
        runtime._writer_sink_reject = 1
        runtime._writer_drain_deadline_loss = 1
        runtime._aggregate_worker_attempted = 4

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        _assert_writer_invariant(report)
        assert report['unexplained_lost'] == 0

    def test_attempted_side_invariant_is_preserved_when_snapshot_complete(
        self, tmp_path
    ):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        runtime._accepted = 8
        runtime._delivered = 8
        runtime._aggregate_worker_attempted = 12
        runtime._aggregate_worker_overload_shed = 1
        runtime._aggregate_worker_transport_closed_drop = 1
        runtime._aggregate_worker_writer_unavailable_drop = 1
        runtime._aggregate_worker_timeout_drop = 1

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        assert report['snapshot_complete'] is True
        assert report['attempted'] == (
            report['accepted'] + sum(report['worker_drop_breakdown'].values())
        )

    def test_snapshot_incomplete_unexplained_lost_uses_writer_side_estimate(
        self, tmp_path
    ):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        runtime._accepted = 3
        runtime._delivered = 1
        runtime._writer_sink_reject = 1
        with runtime._active_lock:
            runtime._active_clients['missing'] = {'pid': 222, 'session_id': 's'}

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        assert report['snapshot_complete'] is False
        assert report['unexplained_lost'] == 1
        _assert_writer_invariant(report)

    def test_drop_breakdowns_keep_writer_and_worker_sources_separate(self, tmp_path):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        runtime._writer_drain_deadline_loss = 2
        runtime._aggregate_worker_timeout_drop = 3

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        assert report['writer_drop_breakdown'] == {'writer_drain_deadline_loss': 2}
        assert report['worker_drop_breakdown']['worker_timeout_drop'] == 3
        assert 'writer_drain_deadline_loss' not in report['worker_drop_breakdown']

    def test_partial_delivered_is_independent_terminal_state(self, tmp_path):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        runtime._accepted = 1
        runtime._writer_partial_delivered = 1
        runtime._aggregate_worker_attempted = 1

        runtime.stop(timeout=0.01)

        report = _read_json(report_path)
        assert report['partial_delivered'] == 1
        assert report['delivered'] == 0
        assert report['known_rejected'] == 0
        _assert_writer_invariant(report)

    def test_warning_queue_drain_incomplete_is_reported(self, tmp_path):
        report_path = tmp_path / 'shutdown-report.json'
        runtime = _make_runtime(tmp_path, report_path=report_path)
        runtime._warning_queue_drain_incomplete = True

        runtime.stop(timeout=0.01)

        assert _read_json(report_path)['warning_queue_drain_incomplete'] is True
