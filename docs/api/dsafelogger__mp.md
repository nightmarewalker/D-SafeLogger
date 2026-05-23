# Multiprocess API

**Module**: `dsafelogger.mp`

D-SafeLogger multiprocess public API.

Public API:
    ConfigureLogger       - Initialize Writer runtime and attach caller process
    AttachCurrentProcess  - Attach a worker process to an existing Writer runtime
    GetLogger             - Get a DSafeLogger instance (requires prior attach)
    GetWorkerInitializer  - Return (init_fn, init_args) for Pool/Executor initializer
    GetDeliveryStatus     - Return current Writer delivery accounting snapshot
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

### `ConfigureLogger(default_level: 'str' = 'INFO', log_path: 'str' = '.', pg_name: 'str' = 'Default', env_prefix: 'str' = 'D_LOG', config_file: 'str | None' = None, config_dict: 'dict[str, dict[str, str]] | None' = None, is_async: 'bool' = False, backup_count: 'int' = 0, archive_mode: 'bool' = False, routing_mode: 'str' = 'none', interval: 'str | int' = 10, max_bytes: 'int' = 0, max_lines: 'int' = 0, max_count: 'int | None' = None, suffix_digits: 'int' = 3, console_out: 'bool' = True, structured: 'bool' = False, fmt: 'str | logging.Formatter | None' = None, file_fmt: 'str | logging.Formatter | None' = None, console_fmt: 'str | logging.Formatter | None' = None, datefmt: 'str | None' = None, enable_hash: 'bool' = False, manifest_path: 'str | None' = None, sens_kws: 'Sequence[str] | None' = None, sens_kws_replace: 'bool' = False, worker_model: "Literal['process', 'pool', 'executor']" = 'process', mp_context: 'Any' = None, ipc_log_timeout: 'float' = 0.5, ipc_log_queue_maxsize: 'int | None' = None, ipc_client_queue_maxsize: 'int | None' = None, writer_flush_batch: 'int | None' = None, runtime_warning_path: 'str | None' = None, shutdown_report_path: 'str | None' = None) -> 'BootstrapContext'`

Initialize D-SafeLogger Writer runtime for multiprocess use.

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

### `DetachCurrentProcess() -> 'None'`

Detach the current process from the active Writer runtime.

If the current process is not attached, this is a no-op.

### `GetDeliveryStatus() -> 'DeliveryStatus'`

Return a runtime snapshot of Writer-owned delivery counters.

The snapshot is intended for live status checks. During normal runtime,
`missing_detach_clients` is always zero because active workers are not
treated as crashed until shutdown report generation.

Raises:
    RuntimeError: Multiprocess logging is not configured or Writer stopped.
    TimeoutError: The Writer did not return a STATUS ACK in time.

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

## Classes

### `DeliveryStatus(...)`

Runtime snapshot of multiprocess delivery accounting counters.

`partial_delivered` is a terminal state separate from `delivered` and
`known_rejected`. Runtime STATUS snapshots report
`missing_detach_clients=0`; crash classification is finalized in the
shutdown report when `shutdown_report_path` is configured.
