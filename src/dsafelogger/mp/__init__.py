"""D-SafeLogger multiprocess public API.

Public API:
    ConfigureLogger       - Initialize Writer runtime and attach caller process
    AttachCurrentProcess  - Attach a worker process to an existing Writer runtime
    GetLogger             - Get a DSafeLogger instance (requires prior attach)
    GetWorkerInitializer  - Return (init_fn, init_args) for Pool/Executor initializer
    GetDeliveryStatus     - Return current Writer delivery accounting snapshot
    ReopenLogFiles        - Signal Writer to reopen file sinks after external log rotation
"""
from __future__ import annotations

import atexit
import configparser
import errno
import hashlib
import json
import logging
import multiprocessing
import os
import sys
import threading
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from dsafelogger import _mp_attach
from dsafelogger._constants import (
    BUILTIN_SENSITIVE_KEYWORDS,
    DEFAULT_FMT,
    VALID_ROUTING_MODES,
)
from dsafelogger._config_validation import (
    validate_bool_args,
    validate_resolved_file_config,
)
from dsafelogger._env_parser import EnvParser
from dsafelogger._formatter import (
    DSafeFormatter,
    DiagnosticFormatter,
    DiagnosticStructuredFormatter,
    StructuredFormatter,
)
from dsafelogger._handler import AppendOnlyFileHandler
from dsafelogger._ini_loader import DictLoader, IniLoader
from dsafelogger._levels import (
    get_all_level_map,
    get_valid_abbreviations,
    get_valid_level_names,
)
from dsafelogger._logger import DSafeLogger
from dsafelogger._mp_control import (
    MAX_IPC_LOG_TIMEOUT_SECONDS,
    _make_bootstrap_ready_request,
    _resolve_mp_context,
    _make_pipe_with_context,
    _make_reopen_request,
    _make_status_request,
    _raise_for_failed_ack,
    _send_control_request,
    _wait_control_ack,
)
from dsafelogger._mp_protocol import BootstrapContext, ControlAck
from dsafelogger._mp_queue import TrackedQueue
from dsafelogger._mp_runtime import WriterRuntime
from dsafelogger._routing import create_strategy
from dsafelogger._validator import PathValidator
from dsafelogger._writer_formatter import _KIND_MAP

__all__ = [
    'ConfigureLogger',
    'AttachCurrentProcess',
    'DetachCurrentProcess',
    'GetLogger',
    'GetWorkerInitializer',
    'GetDeliveryStatus',
    'DeliveryStatus',
    'ReopenLogFiles',
]


class DeliveryStatus(TypedDict):
    """Runtime snapshot of multiprocess delivery accounting counters.

    `partial_delivered` is a terminal state separate from `delivered` and
    `known_rejected`. Runtime STATUS snapshots report
    `missing_detach_clients=0`; crash classification is finalized in the
    shutdown report when `shutdown_report_path` is configured.
    """

    schema_version: int
    session_id: str
    writer_pid: int
    active_clients: int
    attempted: int
    accepted: int
    delivered: int
    partial_delivered: int
    known_rejected: int
    known_dropped: int
    unexplained_lost: int
    writer_reject_breakdown: dict[str, int]
    worker_drop_breakdown: dict[str, int]
    writer_drop_breakdown: dict[str, int]
    snapshot_complete: bool
    missing_detach_clients: int
    stop_requested: bool

# ── Process-local Writer state ────────────────────────────────────────────────

_mp_configure_lock = threading.RLock()
_mp_writer_runtime: WriterRuntime | None = None
_mp_atexit_registered: bool = False

_LOG_QUEUE_MAXSIZE = 10000
_CONTROL_QUEUE_MAXSIZE = 256

_PG_NAME_FORBIDDEN = set('/\\:*?"<>|')


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sanitize_pg_name(pg_name: str) -> str:
    return ''.join('_' if c in _PG_NAME_FORBIDDEN else c for c in pg_name)


def _validate_routing_thresholds(
    routing_mode: str,
    *,
    max_bytes: int | None,
    max_lines: int | None,
    scope: str,
) -> None:
    if routing_mode == 'size' and (max_bytes is None or max_bytes <= 0):
        raise ValueError(
            f"{scope}: routing_mode='size' requires max_bytes > 0, got {max_bytes!r}"
        )
    if routing_mode == 'count' and (max_lines is None or max_lines <= 0):
        raise ValueError(
            f"{scope}: routing_mode='count' requires max_lines > 0, got {max_lines!r}"
        )


def _compute_registry_hash() -> str:
    level_map = get_all_level_map()
    payload = json.dumps(sorted(level_map.items()), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _merge_module_configs(
    ini_modules: dict[str, dict[str, Any]],
    env_modules: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for mod, cfg in ini_modules.items():
        merged[mod] = cfg.copy()
    for mod, env_cfg in env_modules.items():
        if mod in merged:
            if 'level' in env_cfg:
                merged[mod]['level'] = env_cfg['level']
            if 'path' in env_cfg and env_cfg['path'] is not None:
                merged[mod]['path'] = env_cfg['path']
        else:
            merged[mod] = env_cfg
    return merged


def _make_formatter(
    fmt_val: str | logging.Formatter | None,
    is_structured: bool,
    datefmt: str | None,
    diagnose: bool,
    sensitive_keywords: frozenset[str] | None,
) -> logging.Formatter:
    if isinstance(fmt_val, logging.Formatter):
        return fmt_val
    if is_structured:
        if diagnose:
            return DiagnosticStructuredFormatter(sensitive_keywords=sensitive_keywords)
        return StructuredFormatter()
    fmt_str = fmt_val if isinstance(fmt_val, str) and fmt_val else DEFAULT_FMT
    if diagnose:
        return DiagnosticFormatter(
            fmt=fmt_str, datefmt=datefmt, sensitive_keywords=sensitive_keywords
        )
    return DSafeFormatter(fmt=fmt_str, datefmt=datefmt)


def _build_writer_sink_groups(
    args_config: dict[str, Any],
    module_configs: dict[str, dict[str, Any]],
    sensitive_keywords: frozenset[str],
) -> dict[str, list[logging.Handler]]:
    """Build Writer-side sink handler groups keyed by route string."""
    from dsafelogger import _constants

    diagnose = _constants._diagnose_enabled
    log_path_obj = Path(args_config['log_path'])
    routing_kwargs = {
        'interval': args_config['interval'],
        'max_bytes': args_config['max_bytes'],
        'max_lines': args_config['max_lines'],
        'max_count': args_config['max_count'],
        'suffix_digits': args_config['suffix_digits'],
    }
    is_structured = bool(args_config.get('structured'))
    datefmt = args_config.get('datefmt')
    skws = sensitive_keywords if diagnose else None

    file_fmt_value = args_config.get('file_fmt') or args_config.get('fmt')
    if isinstance(file_fmt_value, logging.Formatter):
        from dsafelogger._writer_formatter import freeze_formatter, rebuild_formatter

        file_fmt_value = rebuild_formatter(freeze_formatter(file_fmt_value))

    file_formatter = _make_formatter(
        file_fmt_value,
        is_structured, datefmt, diagnose, skws,
    )

    # Root file handler
    strategy = create_strategy(
        routing_mode=args_config['routing_mode'],
        base_dir=log_path_obj,
        pg_name=args_config['pg_name'],
        **routing_kwargs,
    )
    file_handler = AppendOnlyFileHandler(
        strategy=strategy,
        backup_count=args_config['backup_count'],
        archive_mode=args_config['archive_mode'],
        enable_hash=args_config['enable_hash'],
        manifest_path=str(args_config['manifest_path']) if args_config.get('manifest_path') else None,
        encoding=args_config.get('encoding', 'utf-8'),
        stream_flush_on_emit=False,  # Writer batch-flushes explicitly (v23e)
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.NOTSET)
    root_handlers: list[logging.Handler] = [file_handler]

    # Console handler
    if args_config.get('console_out', True):
        from dsafelogger._color import ColorStreamHandler
        console_fmt_value = args_config.get('console_fmt') or args_config.get('fmt')
        if isinstance(console_fmt_value, logging.Formatter):
            from dsafelogger._writer_formatter import freeze_formatter, rebuild_formatter

            console_fmt_value = rebuild_formatter(freeze_formatter(console_fmt_value))
        console_formatter = _make_formatter(
            console_fmt_value,
            is_structured, datefmt, diagnose, skws,
        )
        console_handler = ColorStreamHandler(
            stream=sys.stderr,
            color_enabled=bool(args_config.get('color_stream', False)),
            color_overrides=args_config.get('color_overrides') or None,
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.NOTSET)
        root_handlers.append(console_handler)

    sink_groups: dict[str, list[logging.Handler]] = {'root': root_handlers}

    # Module-specific handlers
    for mod_name, mod_conf in module_configs.items():
        mod_path = mod_conf.get('path')
        if not mod_path:
            continue
        mod_path_str = str(mod_path)
        if os.sep in mod_path_str or '/' in mod_path_str:
            mod_full_path = Path(mod_path_str)
        else:
            mod_full_path = log_path_obj / mod_path_str

        mod_strategy = create_strategy(
            routing_mode=mod_conf.get('routing_mode', 'none'),
            base_dir=mod_full_path.parent,
            pg_name=mod_full_path.stem,
            interval=mod_conf.get('interval', routing_kwargs['interval']),
            max_bytes=mod_conf.get('max_bytes', routing_kwargs['max_bytes']),
            max_lines=mod_conf.get('max_lines', routing_kwargs['max_lines']),
            max_count=mod_conf.get('max_count', routing_kwargs['max_count']),
            suffix_digits=mod_conf.get('suffix_digits', routing_kwargs['suffix_digits']),
        )
        mod_handler = AppendOnlyFileHandler(
            strategy=mod_strategy,
            backup_count=mod_conf.get('backup_count', args_config['backup_count']),
            archive_mode=mod_conf.get('archive_mode', args_config['archive_mode']),
            enable_hash=args_config['enable_hash'],
            manifest_path=str(args_config['manifest_path']) if args_config.get('manifest_path') else None,
            stream_flush_on_emit=False,  # Writer batch-flushes explicitly (v23e)
        )
        mod_handler.setFormatter(file_formatter)
        mod_handler.setLevel(logging.NOTSET)
        sink_groups[f'module:{mod_name}'] = [mod_handler]

    return sink_groups


def _create_log_queue(maxsize: int, ipc_mp_ctx: Any) -> TrackedQueue:
    """Create the Writer log queue and classify platform maxsize failures."""
    try:
        return TrackedQueue(maxsize=maxsize, ctx=ipc_mp_ctx)
    except OSError as exc:
        if exc.errno in {errno.EINVAL, errno.ERANGE}:
            raise ValueError(
                f'ipc_log_queue_maxsize {maxsize} is not supported by '
                f'multiprocessing context {ipc_mp_ctx.get_start_method()!r}'
            ) from exc
        raise RuntimeError('failed to create multiprocess log queue') from exc


def _mp_shutdown() -> None:
    global _mp_writer_runtime
    with _mp_configure_lock:
        runtime = _mp_writer_runtime
        _mp_writer_runtime = None
    if runtime is not None:
        try:
            _mp_attach._do_detach(best_effort=True)
        except Exception:
            pass
        try:
            runtime.stop()
        except Exception as e:
            try:
                print(f'[D-SafeLogger] Warning: mp shutdown error: {e}', file=sys.stderr)
            except Exception:
                pass


def _validate_bootstrap_ready_ack(
    ack: ControlAck,
    *,
    expected_protocol_version: int,
    expected_registry_hash: str,
) -> None:
    if not ack.get('success'):
        msg = ack.get('error_message') or 'Writer bootstrap ready ACK failed.'
        raise RuntimeError(str(msg))
    result = ack.get('result', {})
    if not isinstance(result, dict):
        raise RuntimeError('bootstrap ready ACK result must be a dict')
    actual_protocol = result.get('protocol_version')
    actual_registry = result.get('registry_hash')
    if actual_protocol != expected_protocol_version:
        raise RuntimeError(
            'bootstrap ready ACK protocol_version mismatch: '
            f'expected {expected_protocol_version!r}, got {actual_protocol!r}'
        )
    if actual_registry != expected_registry_hash:
        raise RuntimeError(
            'bootstrap ready ACK registry hash mismatch: '
            f'expected {expected_registry_hash!r}, got {actual_registry!r}'
        )


# ── Public API ────────────────────────────────────────────────────────────────

def ConfigureLogger(
    default_level: str = 'INFO',
    log_path: str = '.',
    pg_name: str = 'Default',
    env_prefix: str = 'D_LOG',
    config_file: str | None = None,
    config_dict: dict[str, dict[str, str]] | None = None,
    is_async: bool = False,
    backup_count: int = 0,
    archive_mode: bool = False,
    routing_mode: str = 'none',
    interval: str | int = 10,
    max_bytes: int = 0,
    max_lines: int = 0,
    max_count: int | None = None,
    suffix_digits: int = 3,
    console_out: bool = True,
    structured: bool = False,
    fmt: str | logging.Formatter | None = None,
    file_fmt: str | logging.Formatter | None = None,
    console_fmt: str | logging.Formatter | None = None,
    datefmt: str | None = None,
    enable_hash: bool = False,
    manifest_path: str | None = None,
    sens_kws: Sequence[str] | None = None,
    sens_kws_replace: bool = False,
    worker_model: Literal['process', 'pool', 'executor'] = 'process',
    mp_context: Any = None,
    ipc_log_timeout: float = 0.5,
    ipc_log_queue_maxsize: int | None = None,
    ipc_client_queue_maxsize: int | None = None,
    writer_flush_batch: int | None = None,
    runtime_warning_path: str | None = None,
    shutdown_report_path: str | None = None,
) -> BootstrapContext:
    """Initialize D-SafeLogger Writer runtime for multiprocess use.

    Starts a Writer runtime (background threads in the calling process) and
    attaches the calling process to it. Returns a picklable BootstrapContext
    that worker processes pass to AttachCurrentProcess().

    Args:
        runtime_warning_path: Optional JSON Lines file for runtime warnings.
            Worker processes that cannot reach the Writer warning IPC path
            write per-pid fallback files named
            ``<runtime_warning_path>.<pid>.fallback.jsonl``.
        shutdown_report_path: Optional JSON file written atomically by the
            Writer during shutdown. It contains the final delivery accounting
            snapshot and worker-crash/missing-detach fields.

    Returns:
        BootstrapContext — opaque, picklable context for worker distribution.

    Raises:
        RuntimeError: Already configured in this process.
        ValueError: Invalid arguments or ipc_log_timeout <= 0.
        TypeError: Non-allow-list Formatter instance.
    """
    global _mp_writer_runtime, _mp_atexit_registered

    with _mp_configure_lock:
        if _mp_writer_runtime is not None:
            raise RuntimeError(
                'mp.ConfigureLogger() has already been called in this process. '
                'Call AttachCurrentProcess(ctx) in worker processes instead.'
            )

        # ── Layer 3: argument validation ──────────────────────────────────────
        if not env_prefix:
            raise ValueError('env_prefix must not be empty')

        validate_bool_args(
            {
                'is_async': is_async,
                'archive_mode': archive_mode,
                'console_out': console_out,
                'structured': structured,
                'enable_hash': enable_hash,
                'sens_kws_replace': sens_kws_replace,
            },
            scope='mp.ConfigureLogger()',
        )

        if routing_mode not in VALID_ROUTING_MODES:
            raise ValueError(
                f"Invalid routing_mode: {routing_mode!r}. "
                f"Valid values: {sorted(VALID_ROUTING_MODES)}"
            )

        valid_levels = get_valid_level_names()
        if default_level.upper() not in valid_levels:
            raise ValueError(
                f"Invalid default_level: {default_level!r}. "
                f"Valid values: {sorted(valid_levels)}"
            )

        pg_name = _sanitize_pg_name(pg_name)

        if structured and any(
            v is not None and not (isinstance(v, str) and v == '')
            for v in (fmt, file_fmt, console_fmt)
        ):
            raise ValueError(
                'structured=True and fmt/file_fmt/console_fmt cannot be specified simultaneously.'
            )

        if suffix_digits < 1:
            raise ValueError(f'suffix_digits must be >= 1, got {suffix_digits}')

        if max_count is not None and max_count < 1:
            raise ValueError(f'max_count must be >= 1 or None, got {max_count}')

        if max_bytes < 0:
            raise ValueError(f'max_bytes must be >= 0, got {max_bytes}')

        if max_lines < 0:
            raise ValueError(f'max_lines must be >= 0, got {max_lines}')

        resolved_runtime_warning_path: str | None = None
        if runtime_warning_path is not None:
            warning_path = Path(runtime_warning_path).expanduser()
            if not warning_path.is_absolute():
                warning_path = warning_path.resolve()
            if not warning_path.parent.exists():
                raise ValueError(
                    'runtime_warning_path parent directory does not exist: '
                    f'{warning_path.parent}'
                )
            resolved_runtime_warning_path = str(warning_path)
        resolved_shutdown_report_path: str | None = None
        if shutdown_report_path is not None:
            report_path = Path(shutdown_report_path).expanduser()
            if not report_path.is_absolute():
                report_path = report_path.resolve()
            if not report_path.parent.exists():
                raise ValueError(
                    'shutdown_report_path parent directory does not exist: '
                    f'{report_path.parent}'
                )
            resolved_shutdown_report_path = str(report_path)

        _validate_routing_thresholds(
            routing_mode, max_bytes=max_bytes, max_lines=max_lines,
            scope='mp.ConfigureLogger()',
        )

        if worker_model not in ('process', 'pool', 'executor'):
            raise ValueError(
                f"Invalid worker_model: {worker_model!r}. "
                "Valid values: 'process', 'pool', 'executor'"
            )

        # Formatter allow-list validation (fail-fast before any I/O)
        for param_name, fmt_arg in [('fmt', fmt), ('file_fmt', file_fmt), ('console_fmt', console_fmt)]:
            if isinstance(fmt_arg, logging.Formatter) and type(fmt_arg) not in _KIND_MAP:
                raise TypeError(
                    f"{param_name}: Formatter type {type(fmt_arg).__name__!r} is not in the "
                    "allow-list. Use one of: logging.Formatter, DSafeFormatter, "
                    "DiagnosticFormatter, StructuredFormatter, DiagnosticStructuredFormatter."
                )

        # ── ipc_log_timeout resolution ────────────────────────────────────────
        env_ipc_raw = os.environ.get(f'{env_prefix}_IPC_LOG_TIMEOUT')
        if env_ipc_raw is not None:
            try:
                ipc_log_timeout = float(env_ipc_raw)
            except ValueError:
                # v23h: invalid env var is now fail-fast (was warning + ignore).
                raise ValueError(
                    f'invalid {env_prefix}_IPC_LOG_TIMEOUT {env_ipc_raw!r}: '
                    'must be a float'
                ) from None

        if ipc_log_timeout <= 0:
            raise ValueError(f'ipc_log_timeout must be > 0, got {ipc_log_timeout}')

        if ipc_log_timeout > MAX_IPC_LOG_TIMEOUT_SECONDS:
            print(
                f'[D-SafeLogger] Warning: ipc_log_timeout {ipc_log_timeout} exceeds '
                f'maximum {MAX_IPC_LOG_TIMEOUT_SECONDS}s; clipping.',
                file=sys.stderr,
            )
            ipc_log_timeout = MAX_IPC_LOG_TIMEOUT_SECONDS

        # ── ipc_log_queue_maxsize resolution ──────────────────────────────────
        env_lq_raw = os.environ.get(f'{env_prefix}_IPC_LOG_QUEUE_MAXSIZE')
        if env_lq_raw is not None:
            try:
                ipc_log_queue_maxsize = int(env_lq_raw)
            except ValueError:
                # v23h: invalid env var is fail-fast.
                raise ValueError(
                    f'invalid {env_prefix}_IPC_LOG_QUEUE_MAXSIZE {env_lq_raw!r}: '
                    'must be an integer'
                ) from None
        resolved_log_queue_maxsize: int
        if ipc_log_queue_maxsize is None:
            resolved_log_queue_maxsize = _LOG_QUEUE_MAXSIZE
        elif ipc_log_queue_maxsize <= 0:
            raise ValueError(
                f'ipc_log_queue_maxsize must be > 0, got {ipc_log_queue_maxsize}'
            )
        else:
            resolved_log_queue_maxsize = ipc_log_queue_maxsize
            if resolved_log_queue_maxsize > 100_000:
                print(
                    f'[D-SafeLogger] Warning: ipc_log_queue_maxsize '
                    f'{resolved_log_queue_maxsize} is very large (>100000); '
                    'high memory usage possible.',
                    file=sys.stderr,
                )

        # ── ipc_client_queue_maxsize resolution ───────────────────────────────
        env_cq_raw = os.environ.get(f'{env_prefix}_IPC_CLIENT_QUEUE_MAXSIZE')
        if env_cq_raw is not None:
            try:
                ipc_client_queue_maxsize = int(env_cq_raw)
            except ValueError:
                # v23h: invalid env var is fail-fast.
                raise ValueError(
                    f'invalid {env_prefix}_IPC_CLIENT_QUEUE_MAXSIZE {env_cq_raw!r}: '
                    'must be an integer'
                ) from None
        resolved_client_queue_maxsize: int
        if ipc_client_queue_maxsize is None:
            resolved_client_queue_maxsize = resolved_log_queue_maxsize
        elif ipc_client_queue_maxsize <= 0:
            raise ValueError(
                f'ipc_client_queue_maxsize must be > 0, got {ipc_client_queue_maxsize}'
            )
        else:
            resolved_client_queue_maxsize = ipc_client_queue_maxsize
            if resolved_client_queue_maxsize > 100_000:
                print(
                    f'[D-SafeLogger] Warning: ipc_client_queue_maxsize '
                    f'{resolved_client_queue_maxsize} is very large (>100000); '
                    'high memory usage possible.',
                    file=sys.stderr,
                )

        # ── writer_flush_batch resolution ─────────────────────────────────────
        env_wfb_raw = os.environ.get(f'{env_prefix}_WRITER_FLUSH_BATCH')
        if env_wfb_raw is not None:
            try:
                writer_flush_batch = int(env_wfb_raw)
            except ValueError:
                # v23h: invalid env var is fail-fast.
                raise ValueError(
                    f'invalid {env_prefix}_WRITER_FLUSH_BATCH {env_wfb_raw!r}: '
                    'must be an integer'
                ) from None
        resolved_writer_flush_batch: int
        if writer_flush_batch is None:
            resolved_writer_flush_batch = 1
        elif writer_flush_batch <= 0:
            raise ValueError(
                f'writer_flush_batch must be > 0, got {writer_flush_batch}'
            )
        else:
            resolved_writer_flush_batch = writer_flush_batch
            if resolved_writer_flush_batch > 1024:
                print(
                    f'[D-SafeLogger] Warning: writer_flush_batch '
                    f'{resolved_writer_flush_batch} is very large (>1024); '
                    'flush visibility may be reduced.',
                    file=sys.stderr,
                )

        # ── Layer 2: load INI / dict ──────────────────────────────────────────
        env_names = EnvParser.resolve_env_names(env_prefix)
        env_config_path = EnvParser.parse_config_path(
            os.environ.get(env_names['config'])
        )

        resolved_config_file: str | None = None
        resolved_config_dict: dict[str, dict[str, str]] | None = None

        if env_config_path is not None:
            resolved_config_file = env_config_path
        else:
            if config_file is not None and config_dict is not None:
                raise ValueError('config_file and config_dict are mutually exclusive.')
            resolved_config_file = config_file
            resolved_config_dict = config_dict

        ini_global: dict[str, Any] = {}
        ini_modules: dict[str, dict[str, Any]] = {}
        color_overrides: dict[str, str] = {}

        if resolved_config_file is not None:
            ini_global, ini_modules = IniLoader.load(resolved_config_file)
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(resolved_config_file, encoding='utf-8')
            color_overrides = IniLoader._parse_color_palette(
                parser, get_valid_abbreviations()
            )
        elif resolved_config_dict is not None:
            ini_global, ini_modules = DictLoader.load(resolved_config_dict)
            color_overrides = DictLoader._parse_color_palette(
                resolved_config_dict, get_valid_abbreviations()
            )

        if 'env_prefix' in ini_global:
            print(
                '[D-SafeLogger] Warning: env_prefix in config_file/config_dict is ignored. '
                'Pass env_prefix to mp.ConfigureLogger() instead.',
                file=sys.stderr,
            )
            ini_global.pop('env_prefix', None)

        # Build args_config from Layer 3 values
        args_config: dict[str, Any] = {
            'default_level': default_level.upper(),
            'log_path': log_path,
            'pg_name': pg_name,
            'env_prefix': env_prefix,
            'is_async': is_async,
            'backup_count': backup_count,
            'archive_mode': archive_mode,
            'routing_mode': routing_mode,
            'interval': interval,
            'max_bytes': max_bytes,
            'max_lines': max_lines,
            'max_count': max_count,
            'suffix_digits': suffix_digits,
            'console_out': console_out,
            'structured': structured,
            'fmt': fmt,
            'file_fmt': file_fmt,
            'console_fmt': console_fmt,
            'datefmt': datefmt,
            'enable_hash': enable_hash,
            'manifest_path': manifest_path,
            'sens_kws': list(sens_kws) if sens_kws is not None else None,
            'sens_kws_replace': sens_kws_replace,
            'color_overrides': color_overrides,
            'encoding': 'utf-8',
        }

        # Merge Layer 2 over Layer 3
        for key, value in ini_global.items():
            if key in args_config:
                args_config[key] = value

        # ── Layer 1: environment variables ────────────────────────────────────
        env_level_raw = os.environ.get(env_names['level'])
        if env_level_raw is not None:
            env_level = EnvParser.parse_global_level(env_level_raw)
            if env_level is not None:
                if env_level.upper() not in get_valid_level_names():
                    raise ValueError(
                        f"Invalid level from {env_names['level']}: {env_level!r}"
                    )
                args_config['default_level'] = env_level.upper()

        env_modules_raw = os.environ.get(env_names['modules'])
        env_modules: dict[str, dict[str, Any]] = {}
        if env_modules_raw is not None:
            env_modules = EnvParser.parse_modules_env(env_modules_raw)

        from dsafelogger import _constants
        env_diagnose = os.environ.get(env_names['diagnose'])
        _constants._diagnose_enabled = (env_diagnose == '1')

        env_console = EnvParser.parse_bool_env(os.environ.get(env_names['console']))
        if env_console is not None:
            args_config['console_out'] = env_console

        no_color = os.environ.get('NO_COLOR')
        env_color = EnvParser.parse_bool_env(os.environ.get(env_names['color']))
        if no_color is not None:
            color_stream = False
        elif env_color is not None:
            color_stream = env_color
        else:
            try:
                color_stream = sys.stderr.isatty()
            except Exception:
                color_stream = False
        args_config['color_stream'] = color_stream

        env_hash = EnvParser.parse_hash_env(os.environ.get(env_names['hash']))
        if env_hash is not None:
            args_config['enable_hash'] = env_hash

        env_manifest = EnvParser.parse_manifest_env(os.environ.get(env_names['manifest']))
        if env_manifest is not None:
            args_config['manifest_path'] = env_manifest

        # ── Final validation after 3-layer merge ──────────────────────────────
        validate_resolved_file_config(
            args_config,
            scope='global config (mp)',
            valid_levels=get_valid_level_names(),
            level_key='default_level',
        )

        # ── Sensitive keywords ────────────────────────────────────────────────
        merged_sens_kws = args_config.get('sens_kws')
        merged_sens_replace = args_config.get('sens_kws_replace', False)
        if merged_sens_replace:
            if not merged_sens_kws:
                raise ValueError(
                    'sens_kws_replace=True requires sens_kws to contain at least one keyword.'
                )
            resolved_sens_kws: frozenset[str] = frozenset(
                kw.lower() for kw in merged_sens_kws
            )
        else:
            if merged_sens_kws:
                resolved_sens_kws = BUILTIN_SENSITIVE_KEYWORDS | frozenset(
                    kw.lower() for kw in merged_sens_kws
                )
            else:
                resolved_sens_kws = BUILTIN_SENSITIVE_KEYWORDS

        # ── Fail-Fast path permission checks ──────────────────────────────────
        log_path_obj = Path(args_config['log_path'])
        PathValidator.validate_writable(log_path_obj)

        merged_modules = _merge_module_configs(ini_modules, env_modules)
        for mod_name, mod_conf in merged_modules.items():
            if 'level' in mod_conf:
                validate_resolved_file_config(
                    {'routing_mode': 'none', 'level': mod_conf['level']},
                    scope=f"module {mod_name!r} (mp)",
                    valid_levels=get_valid_level_names(),
                    level_key='level',
                    check_formatter_conflict=False,
                )
            mod_path = mod_conf.get('path')
            if mod_path:
                validate_resolved_file_config(
                    {
                        'level': mod_conf.get('level', args_config['default_level']),
                        'routing_mode': mod_conf.get('routing_mode', 'none'),
                        'interval': mod_conf.get('interval', args_config['interval']),
                        'max_bytes': mod_conf.get('max_bytes', args_config['max_bytes']),
                        'max_lines': mod_conf.get('max_lines', args_config['max_lines']),
                        'max_count': mod_conf.get('max_count', args_config['max_count']),
                        'suffix_digits': mod_conf.get('suffix_digits', args_config['suffix_digits']),
                        'backup_count': mod_conf.get('backup_count', args_config['backup_count']),
                        'archive_mode': mod_conf.get('archive_mode', args_config['archive_mode']),
                        'enable_hash': args_config['enable_hash'],
                        'manifest_path': args_config['manifest_path'],
                    },
                    scope=f"module {mod_name!r} (mp)",
                    valid_levels=get_valid_level_names(),
                    level_key='level',
                    check_formatter_conflict=False,
                )
                mod_path_str = str(mod_path)
                mod_dir = (
                    Path(mod_path_str).parent
                    if os.sep in mod_path_str or '/' in mod_path_str
                    else log_path_obj
                )
                PathValidator.validate_writable(mod_dir)

        if args_config['manifest_path']:
            PathValidator.validate_writable(
                Path(str(args_config['manifest_path'])).parent
            )

        # Module routes: modules with dedicated Writer-side file sinks
        module_routes: list[str] = [
            mod_name for mod_name, mod_conf in merged_modules.items()
            if mod_conf.get('path')
        ]
        module_levels: dict[str, str] = {
            mod_name: str(mod_conf.get('level', args_config['default_level'])).upper()
            for mod_name, mod_conf in merged_modules.items()
            if 'level' in mod_conf
        }

        # ── Create IPC queues ─────────────────────────────────────────────────
        # v23h: log_queue is a TrackedQueue so qsize() works on platforms where
        # multiprocessing.Queue.qsize() is unimplemented (e.g. macOS); the
        # implementation auto-detects native support and only pays the
        # Value-counter overhead on unsupported platforms.
        ipc_mp_ctx = _resolve_mp_context(mp_context)
        log_queue = _create_log_queue(resolved_log_queue_maxsize, ipc_mp_ctx)
        control_queue = ipc_mp_ctx.Queue(maxsize=_CONTROL_QUEUE_MAXSIZE)
        runtime_warning_queue = (
            ipc_mp_ctx.Queue(maxsize=_CONTROL_QUEUE_MAXSIZE)
            if resolved_runtime_warning_path is not None
            else None
        )

        # ── Build BootstrapContext ────────────────────────────────────────────
        worker_resolved_config: dict[str, object] = {
            'is_async': bool(args_config['is_async']),
            'log_level': args_config['default_level'],
            'module_routes': module_routes,
            'module_levels': module_levels,
            'mp_start_method': ipc_mp_ctx.get_start_method(),
            'runtime_warning_path': resolved_runtime_warning_path,
            'shutdown_report_path': resolved_shutdown_report_path,
        }
        resolved_config_digest = hashlib.sha256(
            json.dumps(worker_resolved_config, sort_keys=True).encode()
        ).hexdigest()[:16]

        ctx = BootstrapContext(
            protocol_version=1,
            session_id=uuid.uuid4().hex,
            writer_pid=os.getpid(),
            log_queue=log_queue,
            control_queue=control_queue,
            resolved_config=worker_resolved_config,
            resolved_config_digest=resolved_config_digest,
            registry_hash=_compute_registry_hash(),
            log_queue_maxsize=resolved_log_queue_maxsize,
            ipc_client_queue_maxsize=resolved_client_queue_maxsize,
            writer_flush_batch=resolved_writer_flush_batch,
            ipc_log_timeout=ipc_log_timeout,
            overflow_policy='drop',
            runtime_warning_queue=runtime_warning_queue,
        )

        # ── Build Writer-side sink groups ─────────────────────────────────────
        sink_groups = _build_writer_sink_groups(
            args_config, merged_modules, resolved_sens_kws
        )

        # ── Start WriterRuntime ───────────────────────────────────────────────
        runtime = WriterRuntime(ctx, sink_groups)
        runtime.start()
        if runtime._log_thread is None or not runtime._log_thread.is_alive():
            raise RuntimeError('Writer bootstrap failed: log thread did not start')
        if runtime._control_thread is None or not runtime._control_thread.is_alive():
            raise RuntimeError('Writer bootstrap failed: control thread did not start')
        send_conn, recv_conn = _make_pipe_with_context(ipc_mp_ctx)
        ready_req = _make_bootstrap_ready_request('bootstrap', send_conn)
        try:
            _send_control_request(ctx.control_queue, ready_req)
            ready_ack = _wait_control_ack(recv_conn, ready_req['request_id'])
            _validate_bootstrap_ready_ack(
                ready_ack,
                expected_protocol_version=ctx.protocol_version,
                expected_registry_hash=ctx.registry_hash,
            )
        finally:
            try:
                send_conn.close()
            except Exception:
                pass
        _mp_writer_runtime = runtime

        if not _mp_atexit_registered:
            atexit.register(_mp_shutdown)
            _mp_atexit_registered = True

    # Attach calling process to Writer runtime (outside configure lock)
    _mp_attach._do_attach(ctx)

    return ctx


def AttachCurrentProcess(ctx: BootstrapContext) -> None:
    """Attach the current process to an existing Writer runtime.

    Must be called in each worker process before logging. Use
    GetWorkerInitializer(ctx) to obtain a (init_fn, init_args) tuple
    suitable for multiprocessing.Pool or ProcessPoolExecutor.

    Args:
        ctx: BootstrapContext returned by mp.ConfigureLogger().

    Raises:
        RuntimeError: Already attached to a different Writer session.
        TimeoutError: Writer ACK timed out.
        ValueError: Writer rejected the ATTACH (e.g., shutting down).
    """
    _mp_attach._do_attach(ctx)


def DetachCurrentProcess() -> None:
    """Detach the current process from the active Writer runtime.

    If the current process is not attached, this is a no-op.
    """
    _mp_attach._do_detach()


def GetLogger(name: str = '') -> DSafeLogger:
    """Get a DSafeLogger instance.

    Unlike the single-process version, this does NOT auto-fire ConfigureLogger.
    The calling process must have called ConfigureLogger() or
    AttachCurrentProcess() first.

    Args:
        name: Logger name. Empty string returns the root logger.

    Returns:
        DSafeLogger instance (logging.Logger compatible).

    Raises:
        RuntimeError: Current process has not been attached to a Writer runtime.
    """
    if _mp_attach._mp_runtime_state is None:
        raise RuntimeError(
            'mp.GetLogger() requires the current process to be attached to a '
            'Writer runtime. Call mp.ConfigureLogger() or '
            'mp.AttachCurrentProcess(ctx) first.'
        )
    logger = logging.getLogger(name)
    return logger  # type: ignore[return-value]


def GetWorkerInitializer(
    ctx: BootstrapContext,
) -> tuple[Callable[..., None], tuple[BootstrapContext]]:
    """Return (init_fn, init_args) for Pool or Executor worker initialization.

    Usage:
        init_fn, init_args = mp.GetWorkerInitializer(ctx)
        with multiprocessing.Pool(initializer=init_fn, initargs=init_args) as pool:
            ...

    Args:
        ctx: BootstrapContext returned by mp.ConfigureLogger().

    Returns:
        (AttachCurrentProcess, (ctx,)) — passes directly to Pool/Executor.
    """
    return (AttachCurrentProcess, (ctx,))


def GetDeliveryStatus() -> DeliveryStatus:
    """Return a runtime snapshot of Writer-owned delivery counters.

    The snapshot is intended for live status checks. During normal runtime,
    `missing_detach_clients` is always zero because active workers are not
    treated as crashed until shutdown report generation.

    Raises:
        RuntimeError: Multiprocess logging is not configured or Writer stopped.
        TimeoutError: The Writer did not return a STATUS ACK in time.
    """
    runtime = _mp_writer_runtime
    if runtime is None:
        raise RuntimeError('multiprocess runtime is not configured')
    if (
        runtime._control_thread is None
        or not runtime._control_thread.is_alive()
        or runtime._stop_requested
    ):
        raise RuntimeError('writer runtime has stopped')

    state = _mp_attach._mp_runtime_state
    client_id = state.client_id if state is not None else 'status-client'
    mp_start_method: object | None
    if state is not None:
        mp_start_method = state.ctx.resolved_config.get('mp_start_method')
        control_queue = state.ctx.control_queue
    else:
        mp_start_method = runtime._ctx.resolved_config.get('mp_start_method')
        control_queue = runtime._ctx.control_queue

    send_conn, recv_conn = _make_pipe_with_context(mp_start_method)
    req = _make_status_request(client_id=client_id, send_conn=send_conn)
    try:
        _send_control_request(control_queue, req)
        ack = _wait_control_ack(recv_conn, req['request_id'])
        _raise_for_failed_ack(ack)
        return _coerce_delivery_status(ack.get('result', {}))
    finally:
        try:
            send_conn.close()
        except Exception:
            pass


def _coerce_delivery_status(result: dict[str, Any]) -> DeliveryStatus:
    return cast(
        DeliveryStatus,
        {
            'schema_version': int(result.get('schema_version', 1)),
            'session_id': str(result.get('session_id', '')),
            'writer_pid': int(result.get('writer_pid', 0)),
            'active_clients': int(result.get('active_clients', 0)),
            'attempted': int(result.get('attempted', 0)),
            'accepted': int(result.get('accepted', 0)),
            'delivered': int(result.get('delivered', 0)),
            'partial_delivered': int(result.get('partial_delivered', 0)),
            'known_rejected': int(result.get('known_rejected', 0)),
            'known_dropped': int(result.get('known_dropped', 0)),
            'unexplained_lost': int(result.get('unexplained_lost', 0)),
            'writer_reject_breakdown': dict(result.get('writer_reject_breakdown', {})),
            'worker_drop_breakdown': dict(result.get('worker_drop_breakdown', {})),
            'writer_drop_breakdown': dict(result.get('writer_drop_breakdown', {})),
            'snapshot_complete': bool(result.get('snapshot_complete', False)),
            'missing_detach_clients': int(result.get('missing_detach_clients', 0)),
            'stop_requested': bool(result.get('stop_requested', False)),
        },
    )


def ReopenLogFiles() -> None:
    """Re-open all Writer-side file sinks after external log rotation.

    Sends a REOPEN control request to the Writer runtime and waits
    synchronously for ACK. Intended for use with routing_mode='none'
    and external log rotators (e.g. logrotate on Linux).

    Raises:
        RuntimeError: Current process is not attached, or no file sinks found.
        ValueError: Any active file sink uses routing_mode != 'none'.
        TimeoutError: ACK did not arrive within CONTROL_PLANE_ACK_TIMEOUT_SEC.
    """
    state = _mp_attach._mp_runtime_state
    if state is None:
        raise RuntimeError(
            'mp.ReopenLogFiles() requires the current process to be attached to a '
            'Writer runtime. Call mp.ConfigureLogger() or AttachCurrentProcess(ctx) first.'
        )

    send_conn, recv_conn = _make_pipe_with_context(
        state.ctx.resolved_config.get('mp_start_method')
    )
    req = _make_reopen_request(client_id=state.client_id, send_conn=send_conn)
    try:
        _send_control_request(state.ctx.control_queue, req)
        ack = _wait_control_ack(recv_conn, req['request_id'])
        _raise_for_failed_ack(ack)
    finally:
        try:
            send_conn.close()
        except Exception:
            pass
