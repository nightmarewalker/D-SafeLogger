"""Tests for BootstrapContext / mp.ConfigureLogger (UT-MPP, UT-MP-CL).

Covers:
    UT-MPP-001 to UT-MPP-008  (§29.1)
    UT-MP-CL-001 to UT-MP-CL-015  (§29.2)
"""
from __future__ import annotations

import logging
import os

import pytest

import dsafelogger.mp as mp
from dsafelogger._mp_protocol import BootstrapContext, LogEvent, _serialize_record, _reconstruct_record
from dsafelogger._formatter import (
    DSafeFormatter,
    DiagnosticFormatter,
    DiagnosticStructuredFormatter,
    StructuredFormatter,
)


# ── UT-MPP: BootstrapContext / protocol payload ───────────────────────────────

class TestBootstrapContextProtocol:

    def test_bootstrap_context_primitive_fields_consistent(self, tmp_path, mp_state):
        """UT-MPP-001: BootstrapContext primitive fields are correct after creation."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
        )
        # Verify primitive fields (Queue objects are not plain-picklable,
        # they are transferred via multiprocessing's internal ForkingPickler)
        assert ctx.protocol_version == 1
        assert len(ctx.session_id) == 32  # uuid4().hex
        assert ctx.writer_pid == os.getpid()
        assert ctx.log_queue_maxsize > 0
        assert ctx.ipc_log_timeout > 0
        assert ctx.overflow_policy == 'drop'
        assert isinstance(ctx.registry_hash, str)

    def test_log_event_ds_context_always_present(self):
        """UT-MPP-003: _serialize_record always includes _ds_context key."""
        rec = logging.makeLogRecord({'msg': 'hello', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'root')
        assert '_ds_context' in event
        assert isinstance(event['_ds_context'], dict)

    def test_log_event_ds_extra_always_present(self):
        """UT-MPP-004: _serialize_record always includes _ds_extra key."""
        rec = logging.makeLogRecord({'msg': 'hello', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'root')
        assert '_ds_extra' in event
        assert isinstance(event['_ds_extra'], dict)

    def test_log_event_exc_text_snapshotted(self):
        """UT-MPP-005: exception text is snapshotted on producer side."""
        try:
            raise ValueError('test error')
        except ValueError:
            import sys
            rec = logging.makeLogRecord({
                'msg': 'oops',
                'levelno': logging.ERROR,
                'exc_info': sys.exc_info(),
            })
        event = _serialize_record(rec, 'root')
        assert event.get('_ds_exc_text') is not None
        assert 'ValueError' in event['_ds_exc_text']

    def test_log_event_root_route(self):
        """UT-MPP-006: _serialize_record with ds_route='root'."""
        rec = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'root')
        assert event['_ds_route'] == 'root'

    def test_log_event_module_route(self):
        """UT-MPP-007: _serialize_record with module route."""
        rec = logging.makeLogRecord({'msg': 'x', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'module:myapp.db')
        assert event['_ds_route'] == 'module:myapp.db'

    def test_reconstruct_record_does_not_overwrite_msg(self):
        """UT-MPP-008: _ds_extra with standard key 'msg' does not overwrite record.msg."""
        rec = logging.makeLogRecord({'msg': 'original', 'levelno': logging.INFO})
        event = _serialize_record(rec, 'root')
        # Manually inject a standard key into _ds_extra to verify protection
        event['_ds_extra']['msg'] = 'injected'
        reconstructed = _reconstruct_record(event)
        # Standard keys in _ds_extra must not overwrite the reconstructed record
        assert reconstructed.msg == 'original'


# ── UT-MP-CL: dsafelogger.mp.ConfigureLogger ────────────────────────────────

class TestMpConfigureLogger:

    def test_returns_bootstrap_context(self, tmp_path, mp_state):
        """UT-MP-CL-001: default args return a BootstrapContext."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
        )
        assert isinstance(ctx, BootstrapContext)

    def test_second_call_raises_runtime_error(self, tmp_path, mp_state):
        """UT-MP-CL-002: calling ConfigureLogger twice raises RuntimeError."""
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        with pytest.raises(RuntimeError, match='already been called'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

    @pytest.mark.parametrize('model', ['process', 'pool', 'executor'])
    def test_valid_worker_models(self, tmp_path, mp_state, model):
        """UT-MP-CL-003/004/005: valid worker_model values succeed."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            worker_model=model,
        )
        assert isinstance(ctx, BootstrapContext)

    def test_invalid_worker_model_raises(self, tmp_path, mp_state):
        """UT-MP-CL-006: invalid worker_model raises ValueError."""
        with pytest.raises(ValueError, match='worker_model'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                worker_model='threads',
            )

    def test_ipc_log_timeout_applied(self, tmp_path, mp_state):
        """UT-MP-CL-007: ipc_log_timeout argument is reflected in ctx."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            ipc_log_timeout=1.5,
        )
        assert ctx.ipc_log_timeout == 1.5

    def test_ipc_log_timeout_env_override(self, tmp_path, mp_state, clean_env, monkeypatch):
        """UT-MP-CL-008: D_LOG_IPC_LOG_TIMEOUT env var overrides argument."""
        monkeypatch.setenv('D_LOG_IPC_LOG_TIMEOUT', '2.0')
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            ipc_log_timeout=0.5,
        )
        assert ctx.ipc_log_timeout == 2.0

    def test_ipc_log_timeout_zero_raises(self, tmp_path, mp_state):
        """UT-MP-CL-009: ipc_log_timeout <= 0 raises ValueError."""
        with pytest.raises(ValueError, match='ipc_log_timeout'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                ipc_log_timeout=0.0,
            )

    def test_ipc_log_timeout_clipped(self, tmp_path, mp_state, capsys):
        """UT-MP-CL-010: ipc_log_timeout > MAX clips to max with warning."""
        from dsafelogger._mp_control import MAX_IPC_LOG_TIMEOUT_SECONDS
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            ipc_log_timeout=MAX_IPC_LOG_TIMEOUT_SECONDS + 5.0,
        )
        assert ctx.ipc_log_timeout == MAX_IPC_LOG_TIMEOUT_SECONDS
        assert 'clip' in capsys.readouterr().err.lower()

    def test_mp_context_applied_to_resolved_config(self, tmp_path, mp_state):
        """UT-MP-CL-011: explicit mp_context start method is propagated."""
        spawn_ctx = __import__('multiprocessing').get_context('spawn')
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            mp_context=spawn_ctx,
        )
        assert ctx.resolved_config['mp_start_method'] == 'spawn'

    def test_caller_process_attached_after_configure(self, tmp_path, mp_state):
        """UT-MP-CL-012: GetLogger() succeeds immediately after ConfigureLogger."""
        mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        logger = mp.GetLogger('test.main')
        assert logger is not None
        assert logger.name == 'test.main'

    def test_bootstrap_ready_registry_hash_mismatch_raises(self, tmp_path, mp_state, monkeypatch):
        """UT-MP-CL-013: bootstrap ready ACK hash mismatch fails fast."""
        monkeypatch.setattr(
            mp,
            '_validate_bootstrap_ready_ack',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('registry hash mismatch')),
        )
        with pytest.raises(RuntimeError, match='registry hash mismatch'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

    def test_bootstrap_ready_protocol_version_mismatch_raises(self, tmp_path, mp_state, monkeypatch):
        """UT-MP-CL-016: bootstrap ready ACK protocol_version mismatch fails fast."""
        monkeypatch.setattr(
            mp,
            '_validate_bootstrap_ready_ack',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('protocol_version mismatch')),
        )
        with pytest.raises(RuntimeError, match='protocol_version mismatch'):
            mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)

    def test_non_allowlist_formatter_raises_type_error(self, tmp_path, mp_state):
        """UT-MP-CL-015: custom Formatter subclass raises TypeError."""
        class MyCustomFormatter(logging.Formatter):
            pass

        with pytest.raises(TypeError, match='allow-list'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                fmt=MyCustomFormatter(),
            )

    @pytest.mark.parametrize('fmt_arg', [
        logging.Formatter('%(message)s'),
        DSafeFormatter(fmt='%(message)s'),
        DiagnosticFormatter(fmt='%(message)s'),
        StructuredFormatter(),
        DiagnosticStructuredFormatter(),
    ])
    def test_allowlist_formatters_accepted(self, tmp_path, mp_state, fmt_arg):
        """UT-MP-CL-014: allow-list Formatter instances are accepted."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            fmt=fmt_arg,
        )
        assert isinstance(ctx, BootstrapContext)

    def test_ctx_is_bootstrap_context(self, tmp_path, mp_state):
        """ConfigureLogger returns a valid BootstrapContext with all required fields."""
        ctx = mp.ConfigureLogger(log_path=str(tmp_path), console_out=False)
        assert isinstance(ctx, BootstrapContext)
        assert ctx.log_queue is not None
        assert ctx.control_queue is not None
        assert ctx.session_id

    def test_invalid_routing_mode_raises(self, tmp_path, mp_state):
        """Standard validation: invalid routing_mode raises ValueError."""
        with pytest.raises(ValueError, match='routing_mode'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                routing_mode='invalid_mode',
            )

    def test_structured_and_fmt_mutual_exclusion(self, tmp_path, mp_state):
        """structured=True with fmt raises ValueError."""
        with pytest.raises(ValueError, match='structured'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                structured=True,
                fmt='%(message)s',
            )

    def test_structured_and_file_fmt_mutual_exclusion(self, tmp_path, mp_state):
        """structured=True with file_fmt raises ValueError."""
        with pytest.raises(ValueError, match='structured'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                structured=True,
                file_fmt='%(message)s',
            )

    def test_config_dict_invalid_default_level_raises(self, tmp_path, mp_state):
        """Merged config default_level is fail-fast validated."""
        with pytest.raises(ValueError, match='invalid level'):
            mp.ConfigureLogger(
                log_path=str(tmp_path),
                console_out=False,
                config_dict={'global': {'default_level': 'NOPE'}},
            )

    @pytest.mark.parametrize('key', ['is_async', 'archive_mode', 'console_out', 'structured', 'enable_hash'])
    def test_bool_args_reject_strings(self, key, tmp_path, mp_state):
        """Python API bool args reject string truthiness."""
        with pytest.raises(TypeError, match=key):
            mp.ConfigureLogger(log_path=str(tmp_path), **{key: 'false'})  # type: ignore[arg-type]

    def test_module_level_propagates_to_attached_logger(self, tmp_path, mp_state):
        """Module-specific level is applied on the capture side."""
        mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            config_dict={
                'dsafelogger:mymod': {
                    'level': 'ERROR',
                    'path': 'mymod.log',
                },
            },
        )
        assert logging.getLogger('mymod').level == logging.ERROR

    def test_module_level_only_is_preserved_in_bootstrap_context(self, tmp_path, mp_state):
        """Module-specific level without a dedicated path is preserved for workers."""
        ctx = mp.ConfigureLogger(
            log_path=str(tmp_path),
            console_out=False,
            config_dict={
                'dsafelogger:mymod': {
                    'level': 'DEBUG',
                },
            },
        )

        assert ctx.resolved_config['module_levels'] == {'mymod': 'DEBUG'}
        assert 'mymod' not in ctx.resolved_config['module_routes']

        mod_logger = logging.getLogger('mymod')
        assert mod_logger.level == logging.DEBUG
        assert mod_logger.propagate is True
