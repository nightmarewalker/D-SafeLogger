"""POSIX fork tests for D-SafeLogger multiprocess (WT/IT-MP-FORK).

Covers:
    IT-MP-FORK-001 to IT-MP-FORK-003  (§29.8a)

These tests run only on POSIX systems where the 'fork' start method is
available (Linux, macOS).  They verify that after a fork the child process
can call AttachCurrentProcess(ctx) safely, that pump threads are
re-created, and that a stopped Writer is handled gracefully.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import time

import pytest

import dsafelogger.mp as mp
from dsafelogger._mp_protocol import BootstrapContext

pytestmark = pytest.mark.skipif(
    sys.platform == 'win32',
    reason='fork tests are POSIX-only',
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _fork_worker_sync(ctx: BootstrapContext, result_queue) -> None:
    """IT-MP-FORK-001: is_async=False fork child attaches and logs."""
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.fork.sync')
    logger.info('fork_sync_message')
    time.sleep(0.1)
    result_queue.put('done')


def _fork_worker_async(ctx: BootstrapContext, result_queue) -> None:
    """IT-MP-FORK-002: is_async=True fork child re-creates pump thread."""
    import dsafelogger._mp_attach as mp_attach_mod
    mp.AttachCurrentProcess(ctx)
    state = mp_attach_mod._mp_runtime_state
    assert state is not None
    assert state.root_transport._is_async
    assert state.root_transport._pump_thread is not None
    assert state.root_transport._pump_thread.is_alive()

    logger = mp.GetLogger('test.fork.async')
    logger.info('fork_async_message')
    time.sleep(0.2)
    result_queue.put('done')


def _fork_worker_dead_writer(ctx: BootstrapContext, result_queue) -> None:
    """IT-MP-FORK-003: emit after Writer death → drop + warning, no crash."""
    # Don't attach (simulate forking after Writer has already died)
    # Instead, attach but then force _writer_dead on the transport
    import dsafelogger._mp_attach as mp_attach_mod
    mp.AttachCurrentProcess(ctx)
    state = mp_attach_mod._mp_runtime_state
    if state is not None:
        state.root_transport._writer_dead = True

    logger = mp.GetLogger('test.fork.dead')
    try:
        logger.info('should_be_dropped')
    except Exception as exc:
        result_queue.put(f'exception:{exc!r}')
        return
    time.sleep(0.1)
    result_queue.put('dropped_ok')


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.timeout(30)
class TestForkIntegration:

    def test_fork_sync_attach_and_log(self, tmp_path, mp_state):
        """IT-MP-FORK-001: fork + is_async=False → attach success, log arrives."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            is_async=False,
            fmt='%(message)s',
        )

        fork_ctx = multiprocessing.get_context('fork')
        result_q = fork_ctx.Queue(1)
        p = fork_ctx.Process(target=_fork_worker_sync, args=(ctx, result_q))
        p.start()
        p.join(timeout=10.0)
        assert p.exitcode == 0
        result_q.get(timeout=5.0)

        time.sleep(0.3)
        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'fork_sync_message' in content

    def test_fork_async_pump_thread_recreated(self, tmp_path, mp_state):
        """IT-MP-FORK-002: fork + is_async=True → pump thread re-created in child."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            is_async=True,
            fmt='%(message)s',
        )

        fork_ctx = multiprocessing.get_context('fork')
        result_q = fork_ctx.Queue(1)
        p = fork_ctx.Process(target=_fork_worker_async, args=(ctx, result_q))
        p.start()
        p.join(timeout=10.0)
        assert p.exitcode == 0
        result_q.get(timeout=5.0)

        time.sleep(0.3)
        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'fork_async_message' in content

    def test_fork_child_dead_writer_no_crash(self, tmp_path, mp_state, capsys):
        """IT-MP-FORK-003: emit to dead Writer → drop + warning, child does not crash."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
        )

        fork_ctx = multiprocessing.get_context('fork')
        result_q = fork_ctx.Queue(1)
        p = fork_ctx.Process(target=_fork_worker_dead_writer, args=(ctx, result_q))
        p.start()
        p.join(timeout=10.0)
        assert p.exitcode == 0

        status = result_q.get(timeout=5.0)
        assert status == 'dropped_ok', f'Expected dropped_ok, got {status!r}'
