# Multiprocess API

**Module**: `dsafelogger.mp`

D-SafeLogger multiprocess public API.

Public API:
    ConfigureLogger       - Initialize Writer runtime and attach caller process
    AttachCurrentProcess  - Attach a worker process to an existing Writer runtime
    GetLogger             - Get a DSafeLogger instance (requires prior attach)
    GetWorkerInitializer  - Return (init_fn, init_args) for Pool/Executor initializer
    ReopenLogFiles        - Signal Writer to reopen file sinks after external log rotation

## Functions

### `AttachCurrentProcess(ctx: 'BootstrapContext') -> 'None'`

Attach the current process to an existing Writer runtime.

Must be called in each worker process before logging. Use
GetWorkerInitializer(ctx) to obtain a (init_fn, init_args) tuple
suitable for multiprocessing.Pool or ProcessPoolExecutor.

Args:
    ctx: BootstrapContext returned by mp.ConfigureLogger().

Raises:
    RuntimeError: Already attached to a different Writer session.
    TimeoutError: Writer ACK timed out.
    ValueError: Writer rejected the ATTACH (e.g., shutting down).

### `ConfigureLogger(default_level: 'str' = 'INFO', log_path: 'str' = '.', pg_name: 'str' = 'Default', env_prefix: 'str' = 'D_LOG', config_file: 'str | None' = None, config_dict: 'dict[str, dict[str, str]] | None' = None, is_async: 'bool' = False, backup_count: 'int' = 0, archive_mode: 'bool' = False, routing_mode: 'str' = 'none', interval: 'str | int' = 10, max_bytes: 'int' = 0, max_lines: 'int' = 0, max_count: 'int | None' = None, suffix_digits: 'int' = 3, console_out: 'bool' = True, structured: 'bool' = False, fmt: 'str | logging.Formatter | None' = None, file_fmt: 'str | logging.Formatter | None' = None, console_fmt: 'str | logging.Formatter | None' = None, datefmt: 'str | None' = None, enable_hash: 'bool' = False, manifest_path: 'str | None' = None, sens_kws: 'Sequence[str] | None' = None, sens_kws_replace: 'bool' = False, worker_model: "Literal['process', 'pool', 'executor']" = 'process', mp_context: 'Any' = None, ipc_log_timeout: 'float' = 0.5, ipc_log_queue_maxsize: 'int | None' = None, ipc_client_queue_maxsize: 'int | None' = None, writer_flush_batch: 'int | None' = None) -> 'BootstrapContext'`

Initialize D-SafeLogger Writer runtime for multiprocess use.

Starts a Writer runtime (background threads in the calling process) and
attaches the calling process to it. Returns a picklable BootstrapContext
that worker processes pass to AttachCurrentProcess().

Returns:
    BootstrapContext — opaque, picklable context for worker distribution.

Raises:
    RuntimeError: Already configured in this process.
    ValueError: Invalid arguments or ipc_log_timeout <= 0.
    TypeError: Non-allow-list Formatter instance.

### `DetachCurrentProcess() -> 'None'`

Detach the current process from the active Writer runtime.

If the current process is not attached, this is a no-op.

### `GetLogger(name: 'str' = '') -> 'DSafeLogger'`

Get a DSafeLogger instance.

Unlike the single-process version, this does NOT auto-fire ConfigureLogger.
The calling process must have called ConfigureLogger() or
AttachCurrentProcess() first.

Args:
    name: Logger name. Empty string returns the root logger.

Returns:
    DSafeLogger instance (logging.Logger compatible).

Raises:
    RuntimeError: Current process has not been attached to a Writer runtime.

### `GetWorkerInitializer(ctx: 'BootstrapContext') -> 'tuple[Callable[..., None], tuple[BootstrapContext]]'`

Return (init_fn, init_args) for Pool or Executor worker initialization.

Usage:
    init_fn, init_args = mp.GetWorkerInitializer(ctx)
    with multiprocessing.Pool(initializer=init_fn, initargs=init_args) as pool:
        ...

Args:
    ctx: BootstrapContext returned by mp.ConfigureLogger().

Returns:
    (AttachCurrentProcess, (ctx,)) — passes directly to Pool/Executor.

### `ReopenLogFiles() -> 'None'`

Re-open all Writer-side file sinks after external log rotation.

Sends a REOPEN control request to the Writer runtime and waits
synchronously for ACK. Intended for use with routing_mode='none'
and external log rotators (e.g. logrotate on Linux).

Raises:
    RuntimeError: Current process is not attached, or no file sinks found.
    ValueError: Any active file sink uses routing_mode != 'none'.
    TimeoutError: ACK did not arrive within CONTROL_PLANE_ACK_TIMEOUT_SEC.
