"""D-SafeLogger: Zero-dependency, thread-safe, append-only logging library.

Public API:
    ConfigureLogger - Initialize the logging system with 3-layer config pipeline
    GetLogger       - Get a DSafeLogger instance (auto-fires ConfigureLogger if needed)
    register_level  - Register custom log levels before ConfigureLogger
    ReopenLogFiles  - Re-open file sinks after external log rotation
"""

from __future__ import annotations

__version__ = '0.3.0'
__all__ = ['ConfigureLogger', 'GetLogger', 'register_level', 'ReopenLogFiles']

import atexit
import copy
import logging
import logging.handlers
import os
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dsafelogger._async import (
    DSafeQueueHandler,
    DSafeQueueListener,
    QUEUE_DRAIN_TIMEOUT_SEC,
    WORKER_JOIN_TIMEOUT_SEC,
)
from dsafelogger._color import ColorStreamHandler, _enable_windows_vt100
from dsafelogger._constants import (
    BUILTIN_SENSITIVE_KEYWORDS,
    DEFAULT_DATEFMT,
    DEFAULT_FMT,
    VALID_ROUTING_MODES,
)
from dsafelogger._config_validation import (
    validate_bool_args,
    validate_resolved_file_config,
)
from dsafelogger._context import _log_context
from dsafelogger._env_parser import EnvParser
from dsafelogger._formatter import (
    DSafeFormatter,
    DiagnosticFormatter,
    DiagnosticStructuredFormatter,
    StructuredFormatter,
)
from dsafelogger._handler import AppendOnlyFileHandler
from dsafelogger._ini_loader import DictLoader, IniLoader
from dsafelogger._integrity import HashWorker
from dsafelogger._levels import (
    get_all_color_map,
    get_all_level_map,
    get_valid_abbreviations,
    get_valid_level_names,
    install_convenience_methods,
    register_level as _register_level_impl,
)
from dsafelogger._logger import DSafeLogger
from dsafelogger._purge import ArchiveWorker, PurgeWorker
from dsafelogger._routing import create_strategy
from dsafelogger._validator import PathValidator

# ──────────────────────────────────────────────────────────────
# Shared state (v18: protected by explicit locks, no GIL reliance)
# ──────────────────────────────────────────────────────────────
_lifecycle_lock = threading.RLock()
_workers_lock = threading.Lock()
_configure_state = 'unconfigured'  # unconfigured | auto | explicit | configuring | shutting_down
_active_pipeline = None  # v20: Pipeline instances
_active_workers: set[threading.Thread] = set()
_atexit_registered: bool = False
_diagnose_enabled: bool = False
_resolved_sensitive_keywords: frozenset[str] = BUILTIN_SENSITIVE_KEYWORDS

# Shared lock tables
_manifest_locks: dict[Path, threading.Lock] = {}
_family_locks: dict[tuple[Path, str], threading.Lock] = {}

# Forbidden characters in pg_name
_PG_NAME_FORBIDDEN = set('/\\:*?"<>|')


def _sanitize_pg_name(pg_name: str) -> str:
    """Replace OS-forbidden characters with underscores."""
    return ''.join('_' if c in _PG_NAME_FORBIDDEN else c for c in pg_name)


def _validate_routing_thresholds(
    routing_mode: str,
    *,
    max_bytes: int | None,
    max_lines: int | None,
    scope: str,
) -> None:
    """Validate size/count routing thresholds after each config merge stage."""
    if routing_mode == 'size' and (max_bytes is None or max_bytes <= 0):
        raise ValueError(
            f"{scope}: routing_mode='size' requires max_bytes > 0, got {max_bytes!r}"
        )

    if routing_mode == 'count' and (max_lines is None or max_lines <= 0):
        raise ValueError(
            f"{scope}: routing_mode='count' requires max_lines > 0, got {max_lines!r}"
        )


def _get_manifest_lock(path: Path) -> threading.Lock:
    """Return a shared lock for a given manifest path."""
    resolved = path.resolve()
    with _lifecycle_lock:
        lock = _manifest_locks.get(resolved)
        if lock is None:
            lock = threading.Lock()
            _manifest_locks[resolved] = lock
        return lock


def _get_family_lock(directory: Path, pg_name: str) -> threading.Lock:
    """Return a shared lock for a given directory + pg_name family."""
    key = (directory.resolve(), pg_name)
    with _lifecycle_lock:
        lock = _family_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _family_locks[key] = lock
        return lock


def _register_worker(worker: threading.Thread) -> None:
    """Register a worker thread for shutdown tracking."""
    with _workers_lock:
        _active_workers.add(worker)


def _unregister_worker(worker: threading.Thread) -> None:
    """Unregister a worker thread after completion."""
    with _workers_lock:
        _active_workers.discard(worker)


def _reset_for_tests() -> None:
    """Reset process-global logger state for the test suite."""
    import dsafelogger._constants as constants_mod
    import dsafelogger._levels as levels_mod

    global _configure_state, _active_pipeline, _atexit_registered
    global _diagnose_enabled, _resolved_sensitive_keywords

    _configure_state = 'unconfigured'
    _active_pipeline = None
    _atexit_registered = False
    _diagnose_enabled = False
    constants_mod._diagnose_enabled = False
    _resolved_sensitive_keywords = BUILTIN_SENSITIVE_KEYWORDS
    constants_mod._resolved_sensitive_keywords = BUILTIN_SENSITIVE_KEYWORDS
    _manifest_locks.clear()
    _family_locks.clear()

    with _workers_lock:
        _active_workers.clear()

    levels_mod._clear_custom_levels_for_tests()


def register_level(
    name: str,
    value: int,
    abbreviation: str,
    color: str = '',
) -> None:
    """Register a custom log level before ConfigureLogger().

    Must be called before ConfigureLogger(). Calling after initialization
    raises RuntimeError.

    Args:
        name: Level name (e.g. 'TRACE'). Normalized to uppercase.
        value: Numeric value (e.g. 5). Built-in values (10,20,30,40,50) are protected.
        abbreviation: 3-character abbreviation (e.g. 'TRC'). Required.
        color: ANSI escape sequence string. Empty for no color.

    Raises:
        RuntimeError: If ConfigureLogger() has already been called.
        ValueError: If validation fails.
    """
    global _configure_state
    with _lifecycle_lock:
        if _configure_state != 'unconfigured':
            raise RuntimeError(
                'register_level() must be called before ConfigureLogger(). '
                'Custom levels cannot be added after logger initialization.'
            )
        _register_level_impl(name, value, abbreviation, color)


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
) -> None:
    """Initialize D-SafeLogger with 3-layer config pipeline.

    Settings are merged in order (higher overrides lower):
        Layer 1: Environment variables ({env_prefix}_LEVEL, etc.)
        Layer 2: INI file or dict (config_file / config_dict / {env_prefix}_CONFIG)
        Layer 3: Function arguments (defaults)

    This function is idempotent: calling it multiple times after the first
    explicit call is a no-op. Auto-fired initialization (via GetLogger) can
    be overridden by an explicit call.
    """
    global _configure_state, _atexit_registered
    global _diagnose_enabled, _resolved_sensitive_keywords

    _is_auto = False

    with _lifecycle_lock:
        if _configure_state == 'explicit':
            return  # No-Op
        if _configure_state == 'shutting_down':
            return  # No-Op during shutdown
        if _configure_state == 'configuring':
            # Re-entrant call from same thread (RLock allows it): return immediately.
            # Cross-thread calls cannot reach here while we hold the lock.
            return

        if _configure_state == 'auto':
            _is_auto = True  # Will re-initialize

        _configure_state = 'configuring'

        # Run _do_configure() while holding the lock so that no other thread
        # can observe 'configuring' state without waiting for completion.
        # RLock is re-entrant, so internal calls that acquire _lifecycle_lock
        # (e.g., _get_manifest_lock) are safe.
        try:
            _do_configure(
                default_level=default_level,
                log_path=log_path,
                pg_name=pg_name,
                env_prefix=env_prefix,
                config_file=config_file,
                config_dict=config_dict,
                is_async=is_async,
                backup_count=backup_count,
                archive_mode=archive_mode,
                routing_mode=routing_mode,
                interval=interval,
                max_bytes=max_bytes,
                max_lines=max_lines,
                max_count=max_count,
                suffix_digits=suffix_digits,
                console_out=console_out,
                structured=structured,
                fmt=fmt,
                file_fmt=file_fmt,
                console_fmt=console_fmt,
                datefmt=datefmt,
                enable_hash=enable_hash,
                manifest_path=manifest_path,
                sens_kws=sens_kws,
                sens_kws_replace=sens_kws_replace,
                _is_auto_fire=False,
                _cleanup_auto=_is_auto,
            )
            _configure_state = 'explicit'
        except Exception:
            _configure_state = 'auto' if _is_auto else 'unconfigured'
            raise


def _do_configure(
    *,
    default_level: str,
    log_path: str,
    pg_name: str,
    env_prefix: str,
    config_file: str | None,
    config_dict: dict[str, dict[str, str]] | None,
    is_async: bool,
    backup_count: int,
    archive_mode: bool,
    routing_mode: str,
    interval: str | int,
    max_bytes: int,
    max_lines: int,
    max_count: int | None,
    suffix_digits: int,
    console_out: bool,
    structured: bool,
    fmt: str | logging.Formatter | None,
    file_fmt: str | logging.Formatter | None,
    console_fmt: str | logging.Formatter | None,
    datefmt: str | None,
    enable_hash: bool,
    manifest_path: str | None,
    sens_kws: Sequence[str] | None,
    sens_kws_replace: bool,
    _is_auto_fire: bool = False,
    _cleanup_auto: bool = False,
) -> None:
    """Internal implementation of ConfigureLogger."""
    global _resolved_sensitive_keywords
    global _atexit_registered

    # ── Step 2: Argument validation (Layer 3) ──
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
        scope='ConfigureLogger()',
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
            'structured=True and fmt/file_fmt/console_fmt cannot be specified simultaneously. '
            'Choose either structured JSON output or custom format string.'
        )

    if suffix_digits < 1:
        raise ValueError(f'suffix_digits must be >= 1, got {suffix_digits}')

    if max_count is not None and max_count < 1:
        raise ValueError(f'max_count must be >= 1 or None, got {max_count}')

    if max_bytes < 0:
        raise ValueError(f'max_bytes must be >= 0, got {max_bytes}')

    if max_lines < 0:
        raise ValueError(f'max_lines must be >= 0, got {max_lines}')

    _validate_routing_thresholds(
        routing_mode,
        max_bytes=max_bytes,
        max_lines=max_lines,
        scope='ConfigureLogger()',
    )

    if config_file is not None and not isinstance(config_file, str):
        raise TypeError(f'config_file must be str or None, got {type(config_file).__name__}')

    if config_dict is not None and not isinstance(config_dict, dict):
        raise TypeError(f'config_dict must be dict or None, got {type(config_dict).__name__}')

    if sens_kws is not None:
        if isinstance(sens_kws, str):
            raise TypeError('sens_kws must be a Sequence[str] (list/tuple), not a bare str')
        for i, kw in enumerate(sens_kws):
            if not isinstance(kw, str):
                raise TypeError(
                    f'sens_kws[{i}] must be str, got {type(kw).__name__}: {kw!r}'
                )
            if not kw:
                raise ValueError(f'sens_kws[{i}] must not be empty')

    # ── Step 3: Resolve Layer 2 source ──
    env_names = EnvParser.resolve_env_names(env_prefix)
    env_config_path = EnvParser.parse_config_path(os.environ.get(env_names['config']))

    resolved_config_file: str | None = None
    resolved_config_dict: dict[str, dict[str, str]] | None = None

    if env_config_path is not None:
        # {prefix}_CONFIG overrides everything
        resolved_config_file = env_config_path
    else:
        if config_file is not None and config_dict is not None:
            raise ValueError(
                'config_file and config_dict are mutually exclusive. '
                'Specify one or the other, not both.'
            )
        resolved_config_file = config_file
        resolved_config_dict = config_dict

    # ── Step 4: Load and merge Layer 2 ──
    ini_global: dict[str, Any] = {}
    ini_modules: dict[str, dict[str, Any]] = {}
    color_overrides: dict[str, str] = {}

    if resolved_config_file is not None:
        ini_global, ini_modules = IniLoader.load(resolved_config_file)
        import configparser
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

    # Build args config dict
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
    }

    if 'env_prefix' in ini_global:
        print(
            '[D-SafeLogger] Warning: env_prefix in config_file/config_dict is ignored. '
            'Pass env_prefix to ConfigureLogger() instead.',
            file=sys.stderr,
        )
        ini_global.pop('env_prefix', None)

    # Merge Layer 2 into Layer 3
    for key, value in ini_global.items():
        if key in args_config:
            args_config[key] = value

    # ── Step 5: Apply Layer 1 (environment variables) ──
    # Global level
    env_level_raw = os.environ.get(env_names['level'])
    if env_level_raw is not None:
        env_level = EnvParser.parse_global_level(env_level_raw)
        if env_level is not None:
            if env_level.upper() not in get_valid_level_names():
                raise ValueError(
                    f"Invalid level name from {env_names['level']}: {env_level!r}. "
                    f"Valid values: {sorted(get_valid_level_names())}"
                )
            args_config['default_level'] = env_level.upper()

    # Module-level settings
    env_modules_raw = os.environ.get(env_names['modules'])
    env_modules: dict[str, dict[str, Any]] = {}
    if env_modules_raw is not None:
        env_modules = EnvParser.parse_modules_env(env_modules_raw)
        # Validate level names
        for mod_name, mod_config in env_modules.items():
            level = mod_config.get('level', '')
            if level and level.upper() not in get_valid_level_names():
                print(
                    f'[D-SafeLogger] Warning: Invalid level {level!r} for module '
                    f'{mod_name!r} in {env_names["modules"]}. Skipping.',
                    file=sys.stderr,
                )

    # Diagnose (sanctuary)
    env_diagnose = os.environ.get(env_names['diagnose'])
    from dsafelogger import _constants
    _constants._diagnose_enabled = (env_diagnose == '1')
    _diagnose_enabled = _constants._diagnose_enabled

    # Console
    env_console = EnvParser.parse_bool_env(os.environ.get(env_names['console']))
    if env_console is not None:
        args_config['console_out'] = env_console

    # Color
    no_color = os.environ.get('NO_COLOR')
    env_color = EnvParser.parse_bool_env(os.environ.get(env_names['color']))
    if no_color is not None:
        color_enabled = False
    elif env_color is not None:
        color_enabled = env_color
    else:
        try:
            color_enabled = sys.stderr.isatty()
        except Exception:
            color_enabled = False

    # Hash
    env_hash = EnvParser.parse_hash_env(os.environ.get(env_names['hash']))
    if env_hash is not None:
        args_config['enable_hash'] = env_hash

    # Manifest
    env_manifest = EnvParser.parse_manifest_env(os.environ.get(env_names['manifest']))
    if env_manifest is not None:
        args_config['manifest_path'] = env_manifest

    # ── Step 6: Final validation on merged config ──
    validate_resolved_file_config(
        args_config,
        scope='global config',
        valid_levels=get_valid_level_names(),
        level_key='default_level',
    )

    # ── Step 7: Fail-Fast permission validation ──
    log_path_obj = Path(args_config['log_path'])
    PathValidator.validate_writable(log_path_obj)

    # Module paths
    merged_modules = _merge_module_configs(ini_modules, env_modules)
    for mod_name, mod_conf in merged_modules.items():
        if 'level' in mod_conf:
            validate_resolved_file_config(
                {'routing_mode': 'none', 'level': mod_conf['level']},
                scope=f"module {mod_name!r}",
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
                scope=f"module {mod_name!r}",
                valid_levels=get_valid_level_names(),
                level_key='level',
                check_formatter_conflict=False,
            )
            mod_path_str = str(mod_path)
            if os.sep in mod_path_str or '/' in mod_path_str:
                mod_dir = Path(mod_path_str).parent
            else:
                mod_dir = log_path_obj
            PathValidator.validate_writable(mod_dir)

    if args_config['manifest_path']:
        manifest_dir = Path(args_config['manifest_path']).parent
        PathValidator.validate_writable(manifest_dir)

    # ── Step 8: Set logger class ──
    with _lifecycle_lock:
        logging.setLoggerClass(DSafeLogger)
        install_convenience_methods(DSafeLogger)

    # ── Step 9: Resolve sensitive keywords ──
    merged_sens_kws = args_config.get('sens_kws')
    merged_sens_replace = args_config.get('sens_kws_replace', False)

    if merged_sens_replace:
        if not merged_sens_kws:
            raise ValueError(
                'sens_kws_replace=True requires sens_kws to contain at least one keyword.'
            )
        _resolved_sensitive_keywords = frozenset(kw.lower() for kw in merged_sens_kws)
    else:
        if merged_sens_kws:
            _resolved_sensitive_keywords = BUILTIN_SENSITIVE_KEYWORDS | frozenset(
                kw.lower() for kw in merged_sens_kws
            )
        else:
            _resolved_sensitive_keywords = BUILTIN_SENSITIVE_KEYWORDS
    _constants._resolved_sensitive_keywords = _resolved_sensitive_keywords

    # ── Step 10: Configure root logger ──
    root = logging.getLogger()
    root.setLevel(
        logging.getLevelNamesMapping().get(args_config['default_level'], logging.INFO)
    )

    # Cleanup existing handlers if re-initializing from auto state
    if _cleanup_auto:
        for h in root.handlers[:]:
            root.removeHandler(h)
            try:
                h.flush()
                h.close()
            except Exception:
                pass

    from dsafelogger._pipeline import ResolvedConfig, PipelineBuilder
    
    resolved_file_fmt: str | logging.Formatter = 'json' if args_config['structured'] else (
        args_config['file_fmt'] if args_config['file_fmt'] else (
            args_config['fmt'] if args_config['fmt'] else DEFAULT_FMT
        )
    )
    resolved_console_fmt: str | logging.Formatter = 'json' if args_config['structured'] else (
        args_config['console_fmt'] if args_config['console_fmt'] else (
            args_config['fmt'] if args_config['fmt'] else DEFAULT_FMT
        )
    )

    config = ResolvedConfig(
        pg_name=args_config['pg_name'],
        log_dir=log_path_obj,
        file_fmt=resolved_file_fmt,
        console_fmt=resolved_console_fmt,
        routing_mode=args_config['routing_mode'],
        routing_kwargs={
            'interval': args_config['interval'],
            'max_bytes': args_config['max_bytes'],
            'max_lines': args_config['max_lines'],
            'max_count': args_config['max_count'],
            'suffix_digits': args_config['suffix_digits'],
        },
        backup_count=args_config['backup_count'],
        archive_mode=args_config['archive_mode'],
        enable_hash=args_config['enable_hash'],
        manifest_path=Path(args_config['manifest_path']) if args_config['manifest_path'] else None,
        encoding='utf-8',
        diagnose=_constants._diagnose_enabled,
        max_level='',
        console=args_config['console_out'],
        is_async=args_config['is_async'],
        queue_size=-1,
        log_level=args_config['default_level'],
        color_stream=color_enabled,
        module_configs=merged_modules,
        color_overrides=color_overrides,
        sensitive_keywords=_resolved_sensitive_keywords,
    )

    builder = PipelineBuilder()
    pipeline = builder.build(config)
    pipeline.start()
    
    root.addHandler(pipeline.get_root_handler())

    # ── Step 12: Module-level settings ──
    for mod_name, mod_conf in merged_modules.items():
        mod_logger = logging.getLogger(mod_name)
        level_name = mod_conf.get('level', args_config['default_level'])
        mod_logger.setLevel(
            logging.getLevelNamesMapping().get(str(level_name).upper(), logging.DEBUG)
        )

        mod_handler = pipeline.get_module_handler(mod_name)
        if mod_handler is not None:
            mod_logger.propagate = False
            mod_logger.addHandler(mod_handler)
        else:
            mod_logger.propagate = True

    global _active_pipeline
    _active_pipeline = pipeline

    if args_config['is_async'] and not _atexit_registered:
        atexit.register(_shutdown)
        _atexit_registered = True


def _merge_module_configs(
    ini_modules: dict[str, dict[str, Any]],
    env_modules: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge INI (Layer 2) module configs with env (Layer 1) overrides."""
    merged: dict[str, dict[str, Any]] = {}

    for mod, config in ini_modules.items():
        merged[mod] = config.copy()

    for mod, env_config in env_modules.items():
        if mod in merged:
            if 'level' in env_config:
                merged[mod]['level'] = env_config['level']
            if 'path' in env_config and env_config['path'] is not None:
                merged[mod]['path'] = env_config['path']
        else:
            merged[mod] = env_config

    return merged


def GetLogger(name: str = '') -> DSafeLogger:
    """Get a DSafeLogger instance.

    If ConfigureLogger() has not been called yet, it will be auto-fired
    with default arguments (state transitions to 'auto').

    Args:
        name: Logger name. Empty string returns the root logger.

    Returns:
        DSafeLogger instance (logging.Logger compatible).
    """
    global _configure_state

    with _lifecycle_lock:
        state = _configure_state

    if state == 'unconfigured':
        with _lifecycle_lock:
            # Re-check inside the lock: another thread may have already configured.
            if _configure_state not in ('unconfigured',):
                pass  # Someone else got here first; fall through.
            else:
                _configure_state = 'configuring'
                # Run auto-fire while holding the lock (same pattern as ConfigureLogger).
                try:
                    _do_configure(
                        default_level='INFO',
                        log_path='.',
                        pg_name='Default',
                        env_prefix='D_LOG',
                        config_file=None,
                        config_dict=None,
                        is_async=False,
                        backup_count=0,
                        archive_mode=False,
                        routing_mode='none',
                        interval=10,
                        max_bytes=0,
                        max_lines=0,
                        max_count=None,
                        suffix_digits=3,
                        console_out=True,
                        structured=False,
                        fmt=None,
                        file_fmt=None,
                        console_fmt=None,
                        datefmt=None,
                        enable_hash=False,
                        manifest_path=None,
                        sens_kws=None,
                        sens_kws_replace=False,
                        _is_auto_fire=True,
                        _cleanup_auto=False,
                    )
                    _configure_state = 'auto'
                except Exception:
                    _configure_state = 'unconfigured'
                    raise

    elif state == 'configuring':
        # Another thread is holding _lifecycle_lock inside ConfigureLogger or
        # GetLogger auto-fire; acquire and release the lock to wait for completion.
        with _lifecycle_lock:
            pass

    elif state == 'shutting_down':
        # Don't auto-fire during shutdown, return existing logger
        pass

    logger = logging.getLogger(name)
    return logger  # type: ignore[return-value]


def _shutdown() -> None:
    """Safe shutdown handler for atexit."""
    global _configure_state, _active_pipeline

    # Phase A: State transition under lock
    pipeline_ref = None
    with _lifecycle_lock:
        if _configure_state == 'shutting_down':
            return  # Idempotent
        if _configure_state == 'unconfigured':
            return
        _configure_state = 'shutting_down'
        pipeline_ref = _active_pipeline
        _active_pipeline = None

    # Acquire root logger reference up-front so the finally block always has it
    # (pyright narrowing: ensures `root` is not possibly unbound when accessed below).
    root = logging.getLogger()

    # Phase B: Pipeline stop (handles worker joins and listener drains)
    try:
        # Detach pipeline from root logger
        if pipeline_ref is not None:
            handler_to_remove = pipeline_ref.get_root_handler()
            if handler_to_remove in root.handlers:
                root.removeHandler(handler_to_remove)

            # Stop pipeline with timeout
            try:
                pipeline_ref.stop(QUEUE_DRAIN_TIMEOUT_SEC)
            except Exception as e:
                print(f'[D-SafeLogger] Warning: pipeline stop failed: {e}', file=sys.stderr)

        # Join any remaining workers (redundant if pipeline stopped them, but safe)
        with _workers_lock:
            workers_snapshot = _active_workers.copy()

        for worker in workers_snapshot:
            try:
                worker.join(timeout=WORKER_JOIN_TIMEOUT_SEC)
                if worker.is_alive():
                    print(
                        f'[D-SafeLogger] Warning: worker {worker.name} did not finish '
                        f'within {WORKER_JOIN_TIMEOUT_SEC}s.',
                        file=sys.stderr,
                    )
            except Exception:
                pass

    except Exception as e:
        try:
            print(f'[D-SafeLogger] Warning: shutdown error: {e}', file=sys.stderr)
        except Exception:
            pass

    finally:
        # Phase C: Finalize state
        with _lifecycle_lock:
            pass
            # Kept as shutting_down to prevent re-initialization

        # Flush and close handlers
        for h in root.handlers[:]:
            try:
                h.flush()
                h.close()
            except Exception:
                pass
            root.removeHandler(h)


def ReopenLogFiles() -> None:
    """Re-open all writer-side file sinks after external log rotation.

    Intended for use with routing_mode='none' and external log rotators
    (e.g. logrotate on Linux) that use the rename + create cycle.

    This function does NOT install any signal handler.  It is the caller's
    responsibility to invoke ReopenLogFiles() in response to a notification
    (e.g. SIGHUP or logrotate postrotate script).

    Constraints:
        - ConfigureLogger() must have been called first.
        - routing_mode must be 'none' for every active file sink.

    Raises:
        RuntimeError: If the logger has not been configured, or if no file
            sinks are found (console-only configuration).
        ValueError: If any active file sink uses a routing strategy other
            than NoneStrategy (routing_mode != 'none').
    """
    with _lifecycle_lock:
        state = _configure_state
        pipeline = _active_pipeline

    if state not in ('auto', 'explicit'):
        raise RuntimeError(
            "ReopenLogFiles() requires ConfigureLogger() to have been called first. "
            f"Current state: {state!r}"
        )

    if pipeline is None:
        raise RuntimeError(
            "ReopenLogFiles() found no active pipeline."
        )

    # reopen_file_sinks() calls handler.reopen() which raises ValueError
    # for non-NoneStrategy handlers — propagate directly to the caller.
    reopened = pipeline.reopen_file_sinks()
    if reopened == 0:
        raise RuntimeError(
            "ReopenLogFiles() found no file sinks to reopen. "
            "This may indicate a console-only configuration."
        )
