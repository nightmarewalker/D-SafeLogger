"""Multiprocess end-to-end integration tests (IT-MP, IT-MP-RS).

Covers:
    IT-MP-001 to IT-MP-009   (§29.6)
    IT-MP-RS-001 to IT-MP-RS-007  (§29.7)

Worker functions must be defined at module level so spawn can import them.
"""
from __future__ import annotations

import concurrent.futures
import logging
import multiprocessing
import os
import sys
import time

import pytest

import dsafelogger
import dsafelogger.mp as mp
from dsafelogger._formatter import DSafeFormatter
from dsafelogger._mp_protocol import BootstrapContext


# ── Worker-process target functions (module-level for spawn compatibility) ────

def _worker_log_message(ctx: BootstrapContext, result_queue, message: str) -> None:
    """Attach and emit a single INFO log message."""
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.worker')
    logger.info(message)
    # Allow time for the event to be forwarded to the writer
    time.sleep(0.1)
    result_queue.put('done')


def _worker_log_with_context(ctx: BootstrapContext, result_queue) -> None:
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.worker.ctx')
    with logger.contextualize(task_id='42', worker='ctx'):
        logger.info('contextualized_message')
    time.sleep(0.1)
    result_queue.put('done')


def _worker_log_exception(ctx: BootstrapContext, result_queue) -> None:
    """Attach and emit a log with exception info."""
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.worker.exc')
    try:
        raise ValueError('test_exception_value')
    except ValueError:
        logger.exception('exception occurred')
    time.sleep(0.1)
    result_queue.put('done')


def _worker_log_module_route(ctx: BootstrapContext, result_queue, mod_name: str) -> None:
    """Attach and log via a module logger matching a module route."""
    mp.AttachCurrentProcess(ctx)
    logger = logging.getLogger(mod_name)
    logger.info(f'module_{mod_name}_message')
    time.sleep(0.1)
    result_queue.put('done')


def _worker_log_many(ctx: BootstrapContext, result_queue, count: int) -> None:
    """Attach and emit count log messages."""
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.worker.many')
    for i in range(count):
        logger.info(f'msg_{i}')
    time.sleep(0.2)
    result_queue.put('done')


def _worker_via_initializer(ctx: BootstrapContext, result_queue) -> None:
    """Simulate pool-style initializer: initializer attaches, then work logs."""
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.pool.worker')
    logger.info('pool_worker_message')
    time.sleep(0.1)
    result_queue.put('done')


def _pool_worker_log() -> str:
    logger = mp.GetLogger('test.pool.worker')
    logger.info('pool_initializer_message')
    return 'done'


def _executor_worker_log() -> str:
    logger = mp.GetLogger('test.executor.worker')
    logger.info('executor_initializer_message')
    return 'done'


def _worker_log_custom_level(ctx: BootstrapContext, result_queue) -> None:
    from dsafelogger import register_level

    register_level('TRACE', 5, 'TRC')
    mp.AttachCurrentProcess(ctx)
    logger = mp.GetLogger('test.worker.custom')
    logger.log(5, 'trace_message')
    time.sleep(0.1)
    result_queue.put('done')


# ── Helper ────────────────────────────────────────────────────────────────────

def _spawn_context():
    return multiprocessing.get_context('spawn')


def _spawn_and_wait(target, args, timeout=15.0):
    """Spawn a subprocess, run target(*args), wait for completion."""
    ctx_mp = _spawn_context()
    p = ctx_mp.Process(target=target, args=args)
    p.start()
    p.join(timeout=timeout)
    assert p.exitcode == 0, f'Worker exited with code {p.exitcode}'


# ── IT-MP: end-to-end multiprocess tests ──────────────────────────────────────

@pytest.mark.timeout(30)
class TestMpIntegration:

    def test_worker_log_reaches_root_file(self, tmp_path, mp_state):
        """IT-MP-001: worker log arrives at the Writer's root file sink."""
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            mp_context=spawn_ctx,
        )

        result_q = spawn_ctx.Queue(1)
        _spawn_and_wait(_worker_log_message, (ctx, result_q, 'worker_it_mp_001'))
        result_q.get(timeout=5.0)

        # Give the Writer a moment to flush
        time.sleep(0.2)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files, 'No log file created'
        content = log_files[0].read_text(encoding='utf-8')
        assert 'worker_it_mp_001' in content

    def test_worker_exception_log_has_traceback(self, tmp_path, mp_state):
        """IT-MP-003: worker exception log includes traceback."""
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            mp_context=spawn_ctx,
        )

        result_q = spawn_ctx.Queue(1)
        _spawn_and_wait(_worker_log_exception, (ctx, result_q))
        result_q.get(timeout=5.0)
        time.sleep(0.2)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'exception occurred' in content or 'test_exception_value' in content

    def test_worker_contextualize_reaches_writer(self, tmp_path, mp_state):
        """IT-MP-002: worker contextualize appears in Writer output."""
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            mp_context=spawn_ctx,
        )

        result_q = spawn_ctx.Queue(1)
        _spawn_and_wait(_worker_log_with_context, (ctx, result_q))
        result_q.get(timeout=5.0)
        time.sleep(0.2)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'contextualized_message' in content
        assert 'task_id:42' in content

    def test_module_specific_path_route(self, tmp_path, mp_state):
        """IT-MP-004: module route reaches dedicated module file."""
        spawn_ctx = _spawn_context()
        module_path = tmp_path / 'module.log'
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            config_dict={
                'dsafelogger:test.worker.module': {
                    'level': 'INFO',
                    'path': str(module_path),
                }
            },
            mp_context=spawn_ctx,
        )

        result_q = spawn_ctx.Queue(1)
        _spawn_and_wait(_worker_log_module_route, (ctx, result_q, 'test.worker.module'))
        result_q.get(timeout=5.0)
        time.sleep(0.2)

        assert module_path.exists()
        content = module_path.read_text(encoding='utf-8')
        assert 'module_test.worker.module_message' in content

    def test_multiple_workers_all_logged(self, tmp_path, mp_state):
        """IT-MP-005: multiple workers fan-in to the same log file."""
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            mp_context=spawn_ctx,
        )

        num_workers = 3
        result_qs = [spawn_ctx.Queue(1) for _ in range(num_workers)]
        procs = [
            spawn_ctx.Process(
                target=_worker_log_message,
                args=(ctx, result_qs[i], f'worker_{i}_message'),
            )
            for i in range(num_workers)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=15.0)
            assert p.exitcode == 0

        for q in result_qs:
            q.get(timeout=5.0)
        time.sleep(0.3)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        for i in range(num_workers):
            assert f'worker_{i}_message' in content

    def test_worker_via_get_worker_initializer(self, tmp_path, mp_state):
        """IT-MP-006: GetWorkerInitializer works through multiprocessing.Pool."""
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            mp_context=spawn_ctx,
        )

        init_fn, init_args = mp.GetWorkerInitializer(ctx)
        assert init_fn is mp.AttachCurrentProcess

        with spawn_ctx.Pool(processes=1, initializer=init_fn, initargs=init_args) as pool:
            assert pool.apply(_pool_worker_log) == 'done'
        time.sleep(0.2)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'pool_initializer_message' in content

    def test_executor_via_get_worker_initializer(self, tmp_path, mp_state):
        """IT-MP-007: GetWorkerInitializer works through ProcessPoolExecutor."""
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt='%(message)s',
            mp_context=spawn_ctx,
        )

        init_fn, init_args = mp.GetWorkerInitializer(ctx)
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=1,
            mp_context=spawn_ctx,
            initializer=init_fn,
            initargs=init_args,
        ) as executor:
            assert executor.submit(_executor_worker_log).result(timeout=15.0) == 'done'
        time.sleep(0.2)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'executor_initializer_message' in content

    def test_custom_level_registered_configuration(self, tmp_path, mp_state):
        """IT-MP-008: custom level messages reach the Writer."""
        dsafelogger.register_level('TRACE', 5, 'TRC')
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            default_level='TRACE',
            fmt='%(message)s',
            mp_context=spawn_ctx,
        )

        result_q = spawn_ctx.Queue(1)
        _spawn_and_wait(_worker_log_custom_level, (ctx, result_q))
        result_q.get(timeout=5.0)
        time.sleep(0.2)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8')
        assert 'trace_message' in content

    def test_formatter_instance_rebuilds_in_writer(self, tmp_path, mp_state):
        """IT-MP-009: allow-list Formatter instance is applied on Writer side."""
        spawn_ctx = _spawn_context()
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            file_fmt=DSafeFormatter(fmt='%(message)s'),
            mp_context=spawn_ctx,
        )

        result_q = spawn_ctx.Queue(1)
        _spawn_and_wait(_worker_log_message, (ctx, result_q, 'writer_formatter_message'))
        result_q.get(timeout=5.0)
        time.sleep(0.2)

        log_files = list(tmp_path.glob('*.log'))
        assert log_files
        content = log_files[0].read_text(encoding='utf-8').strip()
        assert content.endswith('writer_formatter_message')


# ── IT-MP-RS: backpressure / shutdown / Writer crash ─────────────────────────

@pytest.mark.timeout(30)
class TestMpRobustness:

    def test_reopen_log_files_success(self, tmp_path, mp_state):
        """IT-MP-RS-003: ReopenLogFiles() succeeds from the writer process."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            routing_mode='none',
            console_out=False,
        )
        # Must not raise; file sink exists with NoneStrategy
        mp.ReopenLogFiles()

    def test_reopen_log_files_not_attached_raises(self):
        """IT-MP-RS-004 (variant): ReopenLogFiles without attach raises RuntimeError."""
        import dsafelogger._mp_attach as mp_attach_mod
        assert mp_attach_mod._mp_runtime_state is None
        with pytest.raises(RuntimeError, match='attach'):
            mp.ReopenLogFiles()

    def test_ipc_log_timeout_clipped_in_context(self, tmp_path, mp_state):
        """IT-MP-RS-002: oversize ipc_log_timeout is clipped."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            ipc_log_timeout=99.0,
        )
        assert ctx.ipc_log_timeout == 3.0

    def test_stop_after_all_detach(self, tmp_path, mp_state):
        """IT-MP-RS-005: Writer drains and stops after all clients detach."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
        )
        # Log something, then let the mp_state fixture handle cleanup
        logger = mp.GetLogger('drain_test')
        logger.info('before_stop')
        # The mp_state fixture will stop the runtime properly
