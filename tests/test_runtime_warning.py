"""Tests for RuntimeWarningSink and multiprocess runtime warning plumbing."""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time

import pytest

import dsafelogger.mp as mp
from dsafelogger._mp_attach import MPClientTransport
from dsafelogger._mp_protocol import BootstrapContext
from dsafelogger._mp_runtime import WriterRuntime
from dsafelogger._runtime_warning import (
    RUNTIME_WARNING_SCHEMA_VERSION,
    RuntimeWarningSink,
    make_runtime_warning_payload,
)


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]


def _make_ctx(tmp_path, *, warning_path=None, warning_queue=None):
    import multiprocessing as _mp

    resolved_config: dict[str, object] = {
        'is_async': False,
        'log_level': 'DEBUG',
        'module_routes': [],
        'module_levels': {},
        'mp_start_method': _mp.get_context().get_start_method(),
        'runtime_warning_path': str(warning_path) if warning_path is not None else None,
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
        runtime_warning_queue=warning_queue,
    )


def _stop_runtime(runtime):
    runtime._stop_requested = True
    runtime._accept_new_clients = False
    with runtime._active_lock:
        runtime._active_clients.clear()
        runtime._close_markers_received.update(runtime._expected_close_markers)
    runtime.stop(timeout=1.0)


class TestRuntimeWarningSink:

    def test_write_jsonl_required_fields(self, tmp_path):
        path = tmp_path / 'runtime-warning.jsonl'
        sink = RuntimeWarningSink(path)

        assert sink.write(component='writer', event='sink_reject') is True

        rows = _read_jsonl(path)
        assert len(rows) == 1
        row = rows[0]
        assert row['schema_version'] == RUNTIME_WARNING_SCHEMA_VERSION
        assert row['component'] == 'writer'
        assert row['event'] == 'sink_reject'
        assert row['level'] == 'warning'
        assert row['pid'] == os.getpid()
        assert isinstance(row['ts'], str)

    def test_write_jsonl_optional_fields(self, tmp_path):
        path = tmp_path / 'runtime-warning.jsonl'
        sink = RuntimeWarningSink(path)

        sink.write(
            component='worker',
            event='timeout_drop',
            classification='KnownDropped',
            reason='queue full',
            counter_name='worker_timeout_drop',
            counter_value=3,
            context={'client_id': 'c1'},
        )

        row = _read_jsonl(path)[0]
        assert row['classification'] == 'KnownDropped'
        assert row['reason'] == 'queue full'
        assert row['counter_name'] == 'worker_timeout_drop'
        assert row['counter_value'] == 3
        assert row['context'] == {'client_id': 'c1'}

    def test_fallback_path_includes_pid(self, tmp_path):
        path = tmp_path / 'runtime-warning.jsonl'
        payload = make_runtime_warning_payload(
            component='worker',
            event='writer_unavailable_drop',
        )

        assert RuntimeWarningSink.write_fallback(path, payload, pid=12345) is True

        fallback = tmp_path / 'runtime-warning.jsonl.12345.fallback.jsonl'
        assert _read_jsonl(fallback)[0]['event'] == 'writer_unavailable_drop'

    def test_write_failure_uses_stderr_without_raising(self, tmp_path, capsys):
        sink = RuntimeWarningSink(tmp_path)

        assert sink.write(component='writer', event='flush_error') is False

        assert 'runtime warning sink write failed' in capsys.readouterr().err

    def test_concurrent_writes_keep_one_json_object_per_line(self, tmp_path):
        path = tmp_path / 'runtime-warning.jsonl'
        sink = RuntimeWarningSink(path)

        def emit_many():
            for _ in range(20):
                assert sink.write(component='writer', event='sink_reject') is True

        threads = [threading.Thread(target=emit_many) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)

        rows = _read_jsonl(path)
        assert len(rows) == 100
        assert {row['event'] for row in rows} == {'sink_reject'}


class TestRuntimeWarningMpPlumbing:

    def test_configure_runtime_warning_path_propagates_absolute_path(
        self, tmp_path, mp_state
    ):
        warning_path = tmp_path / 'runtime-warning.jsonl'

        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            runtime_warning_path=str(warning_path),
        )

        assert ctx.resolved_config['runtime_warning_path'] == str(warning_path.resolve())
        assert ctx.runtime_warning_queue is not None
        assert mp._mp_writer_runtime is not None
        assert mp._mp_writer_runtime._warning_thread is not None

    def test_configure_runtime_warning_path_parent_must_exist(
        self, tmp_path, mp_state
    ):
        missing_path = tmp_path / 'missing' / 'runtime-warning.jsonl'

        with pytest.raises(ValueError, match='runtime_warning_path parent'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                runtime_warning_path=str(missing_path),
            )

    def test_writer_warning_goes_to_runtime_warning_file(self, tmp_path):
        warning_path = tmp_path / 'runtime-warning.jsonl'
        ctx = _make_ctx(tmp_path, warning_path=warning_path)
        runtime = WriterRuntime(ctx, {'root': [logging.NullHandler()]})

        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        record._ds_route = 'module:missing'  # type: ignore[attr-defined]
        runtime._dispatch(record)

        rows = _read_jsonl(warning_path)
        assert rows[0]['component'] == 'writer'
        assert rows[0]['event'] == 'route_reject'
        assert rows[0]['classification'] == 'KnownRejected'
        assert rows[0]['counter_name'] == 'writer_route_reject'

    def test_worker_warning_queue_full_uses_fallback_file(self, tmp_path):
        class FullWarningQueue:
            def put_nowait(self, _item):
                raise queue.Full

        warning_path = tmp_path / 'runtime-warning.jsonl'
        ctx = _make_ctx(
            tmp_path,
            warning_path=warning_path,
            warning_queue=FullWarningQueue(),
        )
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        transport._closed = True

        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        transport._emit_record(record)

        fallback = tmp_path / f'runtime-warning.jsonl.{os.getpid()}.fallback.jsonl'
        rows = _read_jsonl(fallback)
        assert rows[0]['component'] == 'worker'
        assert rows[0]['event'] == 'transport_closed_drop'
        assert rows[0]['classification'] == 'KnownDropped'

    def test_warning_queue_consumer_writes_worker_payload(self, tmp_path):
        import multiprocessing as _mp

        warning_path = tmp_path / 'runtime-warning.jsonl'
        warning_queue = _mp.get_context().Queue(10)
        ctx = _make_ctx(
            tmp_path,
            warning_path=warning_path,
            warning_queue=warning_queue,
        )
        runtime = WriterRuntime(ctx, {'root': [logging.NullHandler()]})
        runtime.start()

        warning_queue.put_nowait(
            make_runtime_warning_payload(
                component='worker',
                event='timeout_drop',
                classification='KnownDropped',
            )
        )

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if warning_path.exists() and _read_jsonl(warning_path):
                break
            time.sleep(0.05)

        _stop_runtime(runtime)
        rows = _read_jsonl(warning_path)
        assert any(row['event'] == 'timeout_drop' for row in rows)

    def test_repeated_same_warning_is_rate_limited(self, tmp_path):
        warning_path = tmp_path / 'runtime-warning.jsonl'
        ctx = _make_ctx(tmp_path, warning_path=warning_path)
        runtime = WriterRuntime(ctx, {'root': [logging.NullHandler()]})

        for count in range(1, 1001):
            runtime._maybe_warn(
                count,
                'same sink warning',
                event='sink_reject',
                classification='KnownRejected',
                counter_name='writer_sink_reject',
            )

        rows = _read_jsonl(warning_path)
        assert len(rows) == 11
        assert [row['counter_value'] for row in rows] == [
            1, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
        ]

    def test_worker_warning_path_does_not_block_on_full_warning_queue(
        self, tmp_path
    ):
        class FullWarningQueue:
            def put_nowait(self, _item):
                raise queue.Full

            def put(self, *_args, **_kwargs):
                raise AssertionError('worker warning path must not call blocking put')

        warning_path = tmp_path / 'runtime-warning.jsonl'
        ctx = _make_ctx(
            tmp_path,
            warning_path=warning_path,
            warning_queue=FullWarningQueue(),
        )
        transport = MPClientTransport(ctx, ds_route='root', is_async=False)
        transport._closed = True

        start = time.monotonic()
        record = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        transport._emit_record(record)
        elapsed = time.monotonic() - start

        assert elapsed < 0.5
        fallback = tmp_path / f'runtime-warning.jsonl.{os.getpid()}.fallback.jsonl'
        assert _read_jsonl(fallback)[0]['event'] == 'transport_closed_drop'

    def test_module_transport_worker_drop_emits_warning(self, tmp_path):
        class FullWarningQueue:
            def put_nowait(self, _item):
                raise queue.Full

        warning_path = tmp_path / 'runtime-warning.jsonl'
        ctx = _make_ctx(
            tmp_path,
            warning_path=warning_path,
            warning_queue=FullWarningQueue(),
        )
        transport = MPClientTransport(ctx, ds_route='module:myapp', is_async=False)
        transport._closed = True

        record = logging.makeLogRecord({'msg': 'module drop', 'levelno': logging.INFO})
        transport._emit_record(record)

        fallback = tmp_path / f'runtime-warning.jsonl.{os.getpid()}.fallback.jsonl'
        row = _read_jsonl(fallback)[0]
        assert row['component'] == 'worker'
        assert row['event'] == 'transport_closed_drop'
        assert row['counter_name'] == 'worker_transport_closed_drop'

    def test_warning_consumer_clean_stop_marks_drain_complete(self, tmp_path):
        import multiprocessing as _mp

        warning_path = tmp_path / 'runtime-warning.jsonl'
        warning_queue = _mp.get_context().Queue(10)
        ctx = _make_ctx(
            tmp_path,
            warning_path=warning_path,
            warning_queue=warning_queue,
        )
        runtime = WriterRuntime(ctx, {'root': [logging.NullHandler()]})
        runtime.start()

        warning_queue.put_nowait(
            make_runtime_warning_payload(component='worker', event='timeout_drop')
        )

        _stop_runtime(runtime)

        assert runtime._warning_queue_drain_incomplete is False
        assert any(row['event'] == 'timeout_drop' for row in _read_jsonl(warning_path))

    def test_warning_consumer_drain_incomplete_when_sentinel_cannot_be_queued(
        self, tmp_path
    ):
        class FullWarningQueue:
            def put_nowait(self, _item):
                raise queue.Full

        class AlwaysAliveThread:
            def join(self, timeout=None):
                return None
            def is_alive(self):
                return True

        warning_path = tmp_path / 'runtime-warning.jsonl'
        ctx = _make_ctx(
            tmp_path,
            warning_path=warning_path,
            warning_queue=FullWarningQueue(),
        )
        runtime = WriterRuntime(ctx, {'root': [logging.NullHandler()]})

        runtime._warning_thread = AlwaysAliveThread()  # type: ignore[assignment]
        runtime._stop_runtime_warning_consumer()

        assert runtime._warning_queue_drain_incomplete is True
