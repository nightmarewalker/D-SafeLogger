"""Tests for AttachCurrentProcess / GetWorkerInitializer / mp.GetLogger (UT-MP-AT).

Covers:
    UT-MP-AT-001 to UT-MP-AT-010  (§29.3)
"""
from __future__ import annotations

import errno
import logging
import os
import sys
import threading

import pytest

import dsafelogger._mp_attach as mp_attach_mod
import dsafelogger.mp as mp
from dsafelogger._mp_protocol import BootstrapContext


class TestAttachCurrentProcess:

    def test_same_ctx_reattach_is_noop(self, tmp_path, mp_state):
        """UT-MP-AT-001: re-attaching to the same session is a no-op."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        state_before = mp_attach_mod._mp_runtime_state
        mp.AttachCurrentProcess(ctx)
        state_after = mp_attach_mod._mp_runtime_state
        assert state_before is state_after

    def test_different_ctx_reattach_raises(self, tmp_path, mp_state):
        """UT-MP-AT-002: attaching to a different session raises RuntimeError."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

        # Build a second BootstrapContext with a different session_id
        import multiprocessing, uuid, hashlib, json
        ipc_mp_ctx = multiprocessing.get_context()
        ctx2 = BootstrapContext(
            protocol_version=1,
            session_id=uuid.uuid4().hex,
            writer_pid=ctx.writer_pid,
            log_queue=ipc_mp_ctx.Queue(1),
            control_queue=ipc_mp_ctx.Queue(1),
            resolved_config={'is_async': False, 'log_level': 'INFO', 'module_routes': []},
            resolved_config_digest='abc',
            registry_hash=ctx.registry_hash,
            log_queue_maxsize=10,
            ipc_client_queue_maxsize=10,
            writer_flush_batch=1,
            ipc_log_timeout=0.5,
            overflow_policy='drop',
        )
        with pytest.raises(RuntimeError, match='different Writer session'):
            mp.AttachCurrentProcess(ctx2)

    def test_set_logger_class_on_attach(self, tmp_path, mp_state):
        """UT-MP-AT-004: logging.setLoggerClass is applied after attach."""
        from dsafelogger._logger import DSafeLogger
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = logging.getLogger('attach_test_logger')
        assert isinstance(logger, DSafeLogger)

    def test_get_logger_without_attach_raises(self):
        """UT-MP-AT-005: mp.GetLogger() without attach raises RuntimeError."""
        # mp_state fixture not used — _mp_runtime_state should already be None
        # (reset_logger_state ensures clean state)
        assert mp_attach_mod._mp_runtime_state is None
        with pytest.raises(RuntimeError, match='attach'):
            mp.GetLogger('some.module')

    def test_get_worker_initializer_returns_callable_tuple(self, tmp_path, mp_state):
        """UT-MP-AT-006: GetWorkerInitializer returns (callable, tuple)."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        init_fn, init_args = mp.GetWorkerInitializer(ctx)
        assert callable(init_fn)
        assert isinstance(init_args, tuple)
        assert len(init_args) == 1
        assert init_args[0] is ctx

    def test_get_worker_initializer_fn_is_attach(self, tmp_path, mp_state):
        """UT-MP-AT-007: GetWorkerInitializer callable is equivalent to AttachCurrentProcess."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        init_fn, init_args = mp.GetWorkerInitializer(ctx)
        assert init_fn is mp.AttachCurrentProcess

    def test_concurrent_attach_no_deadlock(self, tmp_path, mp_state):
        """UT-MP-AT-009: concurrent AttachCurrentProcess calls don't deadlock."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        errors: list[Exception] = []

        def try_attach():
            try:
                mp.AttachCurrentProcess(ctx)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=try_attach) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == [], f'Errors in concurrent attach: {errors}'

    def test_detach_current_process_clears_state(self, tmp_path, mp_state):
        """UT-MP-AT-012: DetachCurrentProcess removes process-local state."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert mp_attach_mod._mp_runtime_state is not None
        mp.DetachCurrentProcess()
        assert mp_attach_mod._mp_runtime_state is None
        with pytest.raises(RuntimeError, match='attach'):
            mp.GetLogger('after.detach')

    def test_attach_protocol_version_mismatch_raises(self, tmp_path, mp_state):
        """UT-MP-AT-011: AttachCurrentProcess fails fast on protocol mismatch."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

        import multiprocessing, uuid
        ipc_mp_ctx = multiprocessing.get_context()
        bad_ctx = BootstrapContext(
            protocol_version=999,
            session_id=ctx.session_id,
            writer_pid=ctx.writer_pid,
            log_queue=ctx.log_queue,
            control_queue=ctx.control_queue,
            resolved_config=dict(ctx.resolved_config),
            resolved_config_digest=ctx.resolved_config_digest,
            registry_hash=ctx.registry_hash,
            log_queue_maxsize=ctx.log_queue_maxsize,
            ipc_client_queue_maxsize=ctx.ipc_client_queue_maxsize,
            writer_flush_batch=ctx.writer_flush_batch,
            ipc_log_timeout=ctx.ipc_log_timeout,
            overflow_policy='drop',
        )
        mp.DetachCurrentProcess()
        with pytest.raises(RuntimeError, match='protocol_version'):
            mp.AttachCurrentProcess(bad_ctx)

    def test_same_session_fork_like_attach_reassigns_client_id(self, tmp_path, mp_state):
        """UT-MP-AT-013: same session with different pid gets a new client_id."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        state = mp_attach_mod._mp_runtime_state
        assert state is not None
        original_client_id = state.client_id
        original_pid = state.process_pid

        state.process_pid = original_pid + 1
        try:
            mp.AttachCurrentProcess(ctx)
            new_state = mp_attach_mod._mp_runtime_state
            assert new_state is not None
            assert new_state.client_id != original_client_id
            assert new_state.process_pid == os.getpid()
        finally:
            if mp_attach_mod._mp_runtime_state is not None:
                mp_attach_mod._mp_runtime_state.process_pid = os.getpid()


class TestGetLogger:

    def test_get_logger_returns_logger_after_configure(self, tmp_path, mp_state):
        """After ConfigureLogger, GetLogger returns a logger for the given name."""
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = mp.GetLogger('myapp')
        assert logger.name == 'myapp'

    def test_get_logger_root_returns_root(self, tmp_path, mp_state):
        """GetLogger('') or GetLogger() returns the root logger."""
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = mp.GetLogger()
        assert logger.name == 'root'

    def test_get_logger_does_not_autofire(self):
        """UT-MP-AT-005: GetLogger does not auto-fire ConfigureLogger."""
        assert mp_attach_mod._mp_runtime_state is None
        with pytest.raises(RuntimeError):
            mp.GetLogger('test')


# ── v23c: queue maxsize configuration ────────────────────────────────────────

class TestQueueMaxsizeConfig:

    def test_configure_default_log_queue_maxsize(self, tmp_path, mp_state):
        """Default log_queue_maxsize is 10000 (v23g: aligned with spec §11.16.1)."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert ctx.log_queue_maxsize == 10000

    def test_configure_custom_log_queue_maxsize(self, tmp_path, mp_state):
        """ipc_log_queue_maxsize overrides default (v23c)."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            ipc_log_queue_maxsize=512,
        )
        assert ctx.log_queue_maxsize == 512

    def test_configure_custom_client_queue_maxsize(self, tmp_path, mp_state):
        """ipc_client_queue_maxsize overrides default (v23c)."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            ipc_client_queue_maxsize=256,
        )
        assert ctx.ipc_client_queue_maxsize == 256

    def test_client_queue_defaults_to_log_queue_when_unset(self, tmp_path, mp_state):
        """ipc_client_queue_maxsize defaults to log queue size when not set (v23c)."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            ipc_log_queue_maxsize=400,
        )
        assert ctx.ipc_client_queue_maxsize == 400

    def test_zero_log_queue_maxsize_raises(self, tmp_path, mp_state):
        """ipc_log_queue_maxsize=0 raises ValueError (v23c)."""
        with pytest.raises(ValueError, match='ipc_log_queue_maxsize'):
            mp.ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                ipc_log_queue_maxsize=0,
            )

    def test_negative_client_queue_maxsize_raises(self, tmp_path, mp_state):
        """ipc_client_queue_maxsize=-1 raises ValueError (v23c)."""
        with pytest.raises(ValueError, match='ipc_client_queue_maxsize'):
            mp.ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                ipc_client_queue_maxsize=-1,
            )

    def test_env_var_overrides_log_queue_maxsize(self, tmp_path, mp_state, monkeypatch):
        """D_LOG_IPC_LOG_QUEUE_MAXSIZE env var overrides default (v23c)."""
        monkeypatch.setenv('D_LOG_IPC_LOG_QUEUE_MAXSIZE', '750')
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert ctx.log_queue_maxsize == 750

    def test_env_var_overrides_client_queue_maxsize(self, tmp_path, mp_state, monkeypatch):
        """D_LOG_IPC_CLIENT_QUEUE_MAXSIZE env var overrides default (v23c)."""
        monkeypatch.setenv('D_LOG_IPC_CLIENT_QUEUE_MAXSIZE', '300')
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert ctx.ipc_client_queue_maxsize == 300

    def test_large_log_queue_maxsize_warns(self, tmp_path, mp_state, capsys):
        """ipc_log_queue_maxsize > 100000 warns; OS semaphore limits may reject it."""
        if sys.platform == 'darwin':
            with pytest.raises(ValueError, match='ipc_log_queue_maxsize'):
                mp.ConfigureLogger(
                    log_path=str(tmp_path), console_out=False,
                    ipc_log_queue_maxsize=100_001,
                )
            assert 'ipc_log_queue_maxsize' in capsys.readouterr().err
            return

        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            ipc_log_queue_maxsize=100_001,
        )
        assert ctx.log_queue_maxsize == 100_001
        assert 'ipc_log_queue_maxsize' in capsys.readouterr().err

    def test_unsupported_log_queue_maxsize_raises_before_sinks(
        self, tmp_path, mp_state, monkeypatch
    ):
        """Platform queue-size rejection is a config error before sinks are built."""
        def raise_invalid_argument(*args, **kwargs):
            raise OSError(errno.EINVAL, 'invalid argument')

        def fail_if_sinks_built(*args, **kwargs):
            raise AssertionError('sink groups should not be built')

        monkeypatch.setattr(mp, 'TrackedQueue', raise_invalid_argument)
        monkeypatch.setattr(mp, '_build_writer_sink_groups', fail_if_sinks_built)

        with pytest.raises(ValueError, match='ipc_log_queue_maxsize'):
            mp.ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                ipc_log_queue_maxsize=100_001,
            )
        assert not list(tmp_path.iterdir())

    def test_log_queue_os_failure_is_runtime_error(
        self, tmp_path, mp_state, monkeypatch
    ):
        """Non-validation OS failures are not reported as user config errors."""
        def raise_too_many_open_files(*args, **kwargs):
            raise OSError(errno.EMFILE, 'too many open files')

        monkeypatch.setattr(mp, 'TrackedQueue', raise_too_many_open_files)

        with pytest.raises(RuntimeError, match='multiprocess log queue'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

    def test_invalid_log_queue_env_raises(
        self, tmp_path, mp_state, monkeypatch
    ):
        """v23h: invalid IPC_LOG_QUEUE_MAXSIZE env var raises ValueError (was: warning)."""
        monkeypatch.setenv('D_LOG_IPC_LOG_QUEUE_MAXSIZE', 'not-an-int')
        with pytest.raises(ValueError, match='IPC_LOG_QUEUE_MAXSIZE'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

    def test_invalid_client_queue_env_raises(
        self, tmp_path, mp_state, monkeypatch
    ):
        """v23h: invalid IPC_CLIENT_QUEUE_MAXSIZE env var raises ValueError."""
        monkeypatch.setenv('D_LOG_IPC_CLIENT_QUEUE_MAXSIZE', 'not-an-int')
        with pytest.raises(ValueError, match='IPC_CLIENT_QUEUE_MAXSIZE'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

    def test_invalid_log_timeout_env_raises(
        self, tmp_path, mp_state, monkeypatch
    ):
        """v23h: invalid IPC_LOG_TIMEOUT env var raises ValueError."""
        monkeypatch.setenv('D_LOG_IPC_LOG_TIMEOUT', 'not-a-float')
        with pytest.raises(ValueError, match='IPC_LOG_TIMEOUT'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)


# ── v23g: writer_flush_batch configuration ───────────────────────────────────

class TestWriterFlushBatchConfig:

    def test_configure_default_writer_flush_batch(self, tmp_path, mp_state):
        """Default writer_flush_batch is 1 (v23g: per-message flush, §12.2)."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert ctx.writer_flush_batch == 1

    def test_configure_custom_writer_flush_batch(self, tmp_path, mp_state):
        """writer_flush_batch=16 opt-in enables batch flush (v23g)."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            writer_flush_batch=16,
        )
        assert ctx.writer_flush_batch == 16

    def test_zero_writer_flush_batch_raises(self, tmp_path, mp_state):
        """writer_flush_batch=0 raises ValueError (v23g)."""
        with pytest.raises(ValueError, match='writer_flush_batch'):
            mp.ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                writer_flush_batch=0,
            )

    def test_negative_writer_flush_batch_raises(self, tmp_path, mp_state):
        """writer_flush_batch=-1 raises ValueError (v23g)."""
        with pytest.raises(ValueError, match='writer_flush_batch'):
            mp.ConfigureLogger(
                log_path=str(tmp_path), console_out=False,
                writer_flush_batch=-1,
            )

    def test_env_var_overrides_writer_flush_batch(self, tmp_path, mp_state, monkeypatch):
        """D_LOG_WRITER_FLUSH_BATCH env var overrides default (v23g)."""
        monkeypatch.setenv('D_LOG_WRITER_FLUSH_BATCH', '32')
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert ctx.writer_flush_batch == 32

    def test_writer_flush_batch_propagates_to_runtime(self, tmp_path, mp_state):
        """writer_flush_batch propagates from ctx to WriterRuntime (v23g)."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            writer_flush_batch=8,
        )
        import dsafelogger.mp as dsmp
        runtime = dsmp._mp_writer_runtime
        assert runtime is not None
        assert runtime._writer_flush_batch == 8

    def test_large_writer_flush_batch_warns(self, tmp_path, mp_state, capsys):
        """writer_flush_batch > 1024 warns but remains allowed (v23g)."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path), console_out=False,
            writer_flush_batch=1025,
        )
        assert ctx.writer_flush_batch == 1025
        assert 'writer_flush_batch' in capsys.readouterr().err

    def test_invalid_writer_flush_batch_env_raises(
        self, tmp_path, mp_state, monkeypatch
    ):
        """v23h: invalid WRITER_FLUSH_BATCH env var raises ValueError (was: warning)."""
        monkeypatch.setenv('D_LOG_WRITER_FLUSH_BATCH', 'not-an-int')
        with pytest.raises(ValueError, match='WRITER_FLUSH_BATCH'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
