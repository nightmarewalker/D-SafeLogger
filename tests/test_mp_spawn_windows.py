"""Windows spawn compatibility tests (WT-MP).

Covers:
    WT-MP-001 to WT-MP-005  (§29.8)

These tests run only on Windows. They exercise the spawn multiprocessing
context, which is the only context available on Windows by default.
"""
from __future__ import annotations

import concurrent.futures
import logging
import multiprocessing
import sys
import time

import pytest

import dsafelogger.mp as mp
from dsafelogger._mp_protocol import BootstrapContext

pytestmark = pytest.mark.skipif(
    sys.platform != 'win32',
    reason='Windows spawn tests only run on win32',
)


# ── Worker functions (module-level for spawn import) ──────────────────────────

def _spawn_worker_basic(ctx: BootstrapContext, result_queue) -> None:
    """WT-MP-001: basic attach + log in a spawned process."""
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.spawn.basic')
    logger.info('spawn_basic_message')
    time.sleep(0.1)
    result_queue.put('done')


def _spawn_worker_via_initializer() -> str:
    """WT-MP-002: worker body for real initializer-based spawn execution."""
    logger = mp.GetLogger('test.spawn.init')
    logger.info('spawn_init_message')
    return 'done'


def _spawn_worker_reregister_level() -> str:
    from dsafelogger import register_level

    register_level('TRACE', 5, 'TRC')
    register_level('TRACE', 5, 'TRC')
    logger = mp.GetLogger('test.spawn.level')
    logger.info('spawn_level_message')
    return 'done'


def _spawn_worker_reregister_level_process(ctx: BootstrapContext, result_queue) -> None:
    from dsafelogger import register_level

    register_level('TRACE', 5, 'TRC')
    register_level('TRACE', 5, 'TRC')
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.spawn.level')
    logger.info('spawn_level_message')
    time.sleep(0.1)
    result_queue.put('done')


def _spawn_worker_status_reopen(ctx: BootstrapContext, result_queue) -> None:
    """WT-MP-005: STATUS and REOPEN ACK round-trip from spawned process."""
    from dsafelogger._mp_control import (
        _make_pipe,
        _make_reopen_request,
        _send_control_request,
        _wait_control_ack,
    )
    import dsafelogger._mp_attach as mp_attach_mod

    mp.AttachCurrentProcess(ctx)
    state = mp_attach_mod._mp_runtime_state
    assert state is not None

    send_conn, recv_conn = _make_pipe()
    req = _make_reopen_request(state.client_id, send_conn)
    _send_control_request(state.ctx.control_queue, req)
    ack = _wait_control_ack(recv_conn, req['request_id'])
    # We expect success (NoneStrategy)
    result_queue.put(ack['success'])


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.timeout(30)
class TestWindowsSpawn:

    def test_spawn_end_to_end(self, tmp_path, mp_state):
        """WT-MP-001: spawn context end-to-end attach/log/shutdown."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
        )

        spawn_ctx = multiprocessing.get_context('spawn')
        result_q = spawn_ctx.Queue(1)
        p = spawn_ctx.Process(target=_spawn_worker_basic, args=(ctx, result_q))
        p.start()
        p.join(timeout=15.0)
        assert p.exitcode == 0
        result_q.get(timeout=5.0)

        time.sleep(0.3)
        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'spawn_basic_message' in content

    def test_get_worker_initializer_spawn(self, tmp_path, mp_state):
        """WT-MP-002: GetWorkerInitializer works with spawn Process."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
        )

        spawn_ctx = multiprocessing.get_context('spawn')
        init_fn, init_args = mp.GetWorkerInitializer(ctx)
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=1,
            mp_context=spawn_ctx,
            initializer=init_fn,
            initargs=init_args,
        ) as executor:
            assert executor.submit(_spawn_worker_via_initializer).result(timeout=15.0) == 'done'

        time.sleep(0.2)
        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'spawn_init_message' in content

    def test_no_double_init_on_spawn(self, tmp_path, mp_state):
        """WT-MP-003: spawned process does not double-initialize."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
        )
        spawn_ctx = multiprocessing.get_context('spawn')
        result_q = spawn_ctx.Queue(1)
        p = spawn_ctx.Process(target=_spawn_worker_basic, args=(ctx, result_q))
        p.start()
        p.join(timeout=15.0)
        # Worker should exit cleanly (no double-init crash)
        assert p.exitcode == 0

    def test_spawn_reregister_same_definition_noop(self, tmp_path, mp_state):
        """WT-MP-004: same-definition register_level re-import is a no-op."""
        from dsafelogger import register_level

        register_level('TRACE', 5, 'TRC')
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
        )
        spawn_ctx = multiprocessing.get_context('spawn')
        result_q = spawn_ctx.Queue(1)
        p = spawn_ctx.Process(
            target=_spawn_worker_reregister_level_process,
            args=(ctx, result_q),
        )
        p.start()
        p.join(timeout=15.0)
        assert p.exitcode == 0
        assert result_q.get(timeout=5.0) == 'done'

    def test_status_reopen_ack_roundtrip_from_spawn(self, tmp_path, mp_state):
        """WT-MP-005: REOPEN ACK round-trip from a spawned worker."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            routing_mode='none',
            console_out=False,
        )
        spawn_ctx = multiprocessing.get_context('spawn')
        result_q = spawn_ctx.Queue(1)
        p = spawn_ctx.Process(
            target=_spawn_worker_status_reopen,
            args=(ctx, result_q),
        )
        p.start()
        p.join(timeout=15.0)
        assert p.exitcode == 0
        success = result_q.get(timeout=5.0)
        assert success is True
