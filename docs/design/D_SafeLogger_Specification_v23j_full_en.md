# D-SafeLogger Basic Design Specification v23j (Capture/Transport/Sink 3-layer Architecture, Formal `dsafelogger.mp` Specification, External Log Rotation Coexistence, Fixed Control Plane/Backpressure Semantics, Vendor-Agnostic Core)

## 1. Purpose and Position of This Document
This module is a lightweight, fast, and feature-rich logging platform shared by all projects in the Python ecosystem provided by `D`, including D-Settings, DPySide, and D-MessageRouter.
Although it is intended to be released as a standalone OSS package, its highest priority is to serve as the common foundation of the "D Ecosystem" rather than to maximize general adoption.
With full compliance with the standard library as a hard requirement, it provides strong diagnostic capability and robustness against fatal Windows file-locking issues while keeping runtime external dependencies at zero.

The product is named **`D-SafeLogger`** to make explicit the concept of "safety and robustness (Safe)," which is the module's central feature and its distinctive value.

The target Python version is **3.11 or later**. The design assumes `X | Y` style type hints throughout, so this requirement keeps future implementation, documentation, and type annotations consistent. In addition to regular CPython builds, the design scope includes **free-threaded builds of Python 3.13 or later**. The implementation must not depend on Python 3.14-specific APIs; it should use approaches that can remain unified across Python 3.11+.

## 2. Architecture and Technical Advantages (Overview)
* **Zero Dependency:**
  The library consists only of Python standard-library components. External dependencies are eliminated completely, reducing supply-chain exposure at runtime to zero.
* **Three-layer configuration management pipeline (environment variables > INI/dictionary > arguments):**
  Configuration is strictly merged across three layers: environment variables for emergency overrides, INI files or dictionaries for operational baselines, and `ConfigureLogger` arguments as defaults. This supports both module-level configuration management in large projects and reliable operational control.
* **Separation of Concerns:**
  Logger initialization (`Configure`) and logger use from each module (`GetLogger`) are clearly separated, improving readability and maintainability.
* **Drop-in Replacement (fully standard-compatible):**
  `logging.setLoggerClass()` returns a custom class derived from the standard `logging.Logger`. It can be injected seamlessly into stdlib-logging-compatible libraries such as SQLAlchemy and Django without hacks, combining strong ecosystem compatibility with D-SafeLogger-specific functionality.
* **Async Mode:**
  Synchronous and asynchronous I/O are controlled uniformly through the `Transport` abstraction (`DirectTransport` / `QueueTransport`), eliminating write latency from the main thread, such as a GUI thread. In v18, the producer thread snapshots context information, and diagnostic information only when needed, so hand-off across thread boundaries preserves semantics. In v20, the internal architecture was reorganized into Capture / Transport / Sink layers. In v22c, the multiprocess design was reworked as `dsafelogger.mp` while preserving that three-layer separation. In single-process mode, `is_async=True` handles thread-boundary hand-off; in multiprocess mode, client-to-Writer process-boundary hand-off is added.
* **Free-threaded Python Ready (GIL-independent shared-state management):**
  Shared state such as `_configure_state`, `_active_pipeline`, `_active_workers`, and `_custom_levels` is protected by explicit locks without assuming the GIL exists. The design does not rely on implementation-dependent atomicity of `list` or `dict` operations.
* **Append-Only Routing (O(1) File Access):**
  The library uses an append-only model that determines output file names dynamically without renaming active files. This physically avoids `PermissionError` caused by Windows-specific file-lock contention and keeps OS-level file-operation overhead at O(1).
* **Fire-and-Forget asynchronous purging and self-healing:**
  Generation management, such as deleting or archiving old files, runs in a disposable background thread only when the output destination changes. If purging fails because of a Windows file lock or a similar condition, the next switch retries automatically, providing self-healing behavior.
* **Fail-Fast Initialization Verification & Pre-Storage Verification:**
  At startup, when `ConfigureLogger` runs, the library immediately tests whether output directories can be created and whether permissions and storage are usable. Permission errors and full disks are detected early. Invalid INI values raise exceptions immediately without silent fallback.
* **Environment-variable-only safety control (`diagnose`):**
  Automatic expansion of `f_locals` on exceptions can be enabled only through an environment variable. This prevents the common accident of enabling diagnostics in code and forgetting to disable them. The setting is treated as a protected area that cannot be enabled from INI files.
* **Transparent support for JSONL (Structured Logs):**
  The library can switch to fully structured JSON Lines output, one JSON object per line, while retaining the strengths of the append-only architecture.
* **Thread/async contextualization:**
  `contextvars` are used to automatically attach identifiers to all log records within a scope, with isolation across both threads and asyncio tasks.
* **Custom level names and color output:**
  In addition to abbreviated level names (`DBG`, `INF`, `WAR`, `ERR`, `CRI`), ANSI color output for the console is supported by default.
* **Console color palette settings:**
  Console colors (ANSI color codes) for the five built-in levels and custom levels can be changed with `color_{abbreviation}` keys in the `[global]` section of the INI/dictionary. This enables color customization for terminal environments and visual requirements without code changes. This setting is intentionally supported only in the second layer (INI/dictionary), not through environment variables or function arguments.
* **Custom Log Levels:**
  `register_level()` allows you to insert a custom log level at any numerical position in addition to the standard 5 levels (DEBUG/INFO/WARNING/ERROR/CRITICAL). Complete bulk registration of 3-letter abbreviations, ANSI colors, and convenient methods with a single call before `ConfigureLogger`. The built-in 5 stages are protected as inviolable and are fully aligned with the 3-tier configuration management pipeline.
* **File Integrity Verification:**
  Automatically generates a SHA-256 hash of the write-completed file when switching files by routing. Achieves tampering detection, transfer verification, and file loss detection using a `sha256sum -c` compatible sidecar file and a manifest with a timestamp. Hash calculations are performed in a separate thread and do not block I/O on the main thread.
* **Safe Shutdown:**
  During normal termination, explicitly manage the order of queue drain, bounded worker join, and handler close. `daemon=True` is used only as a backstop during abnormal termination, and is not used as a safety basis during normal termination.
* **Vendor-Agnostic Principles (v20):**
  Do not include any vendor-specific imports (OpenTelemetry, etc.) or data references in the core module (under `src/dsafelogger/`). Vendor integration such as OTel is provided as custom Formatter insertion using `file_fmt` / `console_fmt`, context injection using `contextualize()`, and sample code under `examples/`.
* **Per-sink Formatter configuration (v20):**
  The `file_fmt` / `console_fmt` parameters allow separate Formatters for file output and console output. The existing `fmt` parameter remains the overall default for backward compatibility while enabling output-specific formatting.
* **No-Copy Snapshot (FrozenContext) (v20):**
  Context management changed from `contextvars.ContextVar[dict]` to `contextvars.ContextVar[MappingProxyType]`. The immutability guarantee of `MappingProxyType` optimizes context snapshot and consumer-side hand-off in async mode to O(1) reference passing. Only **immutable values (str, int, float, tuple, etc.) should be passed to `contextualize()` kwargs**. If a typical mutable object such as a list, dict, or set is passed, `TypeError` or `ValueError` is raised fail-fast. This reliably detects unintended side effects from O(1) reference passing during development. `MappingProxyType` protects only top-level key operations; it cannot prevent mutation of mutable values stored inside it.
* **Internal 3-layer pipeline Capture / Transport / Sink (v20, v22c inherited):**
  The internal architecture is maintained as a three-layer model: Capture (log generation), Transport (transfer), and Sink (output). The single-process version uses `DirectTransport` / `QueueTransport`, and the multiprocess version uses an internal transport connecting the client-side attach runtime and the Writer runtime. In both cases, Capture and Sink responsibility boundaries do not change. In v22c, the separation between "logging compatibility belongs to the Capture layer" and "routing / hash / manifest / reopen / purge belong to the Sink/Writer side" is stated explicitly as the formal multiprocess design.
* **Concurrency Safety Enhancements (v21):**
  Execute the entire initialization process of `ConfigureLogger` (`_do_configure()`) while holding `_lifecycle_lock`. `GetLogger` detects the `'configuring'` state and waits for the lock structure. This safely prevents reading of the state during initialization in parallel. The independent `self._lock` of `AppendOnlyFileHandler` was abolished and the double lock overhead was eliminated by unifying it with the lock API (`self.acquire()/release()`) of the parent class `logging.Handler`.
* **Full Transport integration for module-specific paths (v21):**
  `is_async=True` semantics apply consistently to both root routes and module-specific path routes. `Pipeline` holds `module_transports: dict[str, Transport]` and structurally stops all Transports at `stop()`. Handlers are attached to module loggers through `pipeline.get_module_handler()`.
* **Non-destructive level display resolution (v21):**
  `DSafeFormatter.format()` and `ColorStreamHandler.emit()` do not change `record.levelname`. Level abbreviation conversion and ANSI coloring are resolved by local display mappings or display proxies to avoid breaking changes to shared `LogRecord`. It does not depend on temporary replacement by `copy.copy(record)` or try/finally. Guarantees the same semantics for each `%` / `{}` / `$` style allowed by `logging.Formatter`.
* **Context snapshot fallback accuracy (v21):**
  Changed context return in Formatter from `getattr(record, '_ds_context', None) or get_context()` pattern to `hasattr` base branch. If the `_ds_context` attribute exists, even an empty `MappingProxyType` is treated as an authoritative snapshot, and falls back to `get_context()` only when directly called without going through Transport.

---

## 3. Three-tier configuration management pipeline

### 3.1. Design philosophy

D-SafeLogger separates configuration sources into the following three layers and defines a strict merge order in which upper layers always override lower layers.

```
Layer 1: Environment variables (highest priority / emergency override)
  ↓ override
Layer 2: INI file or dictionary (operational baseline)
  ↓ override
Layer 3: ConfigureLogger arguments (defaults / simple use cases)
```

### 3.2. Role of each layer

**Third layer: `ConfigureLogger` argument (lowest level)**

Initial base configuration for simple requirements, such as a single file or small script. In a minimal configuration that does not use INI files or environment variables, this layer is sufficient.

```python
ConfigureLogger(
    default_level='INFO',
    log_path='./logs',
    routing_mode='daily',
    backup_count=7,
)
```
**Layer 2: INI file or dictionary (middle)**

The main axis for managing and visualizing log levels and output destinations for each module in a detailed and structured manner. In addition to all parameters that can be specified with ConfigureLogger arguments, level, output destination, and routing settings for each module can be described as sections. Overrides the parameter with the same name in the ConfigureLogger argument. As an alternative to the INI file, it is also possible to directly pass a dictionary (`config_dict`) with an equivalent structure (see §5.7).

**Layer 1: Environment variables (top level)**

Final override method to set before startup. You can specify configuration values ​​that will be applied the next time `ConfigureLogger` is executed without changing the source code or configuration file. Overwrite everything, including settings in the INI file.

### 3.3. Specific example of merging

The following shows the merge result when all three layers are present.

```python
# Layer 3: ConfigureLogger arguments
ConfigureLogger(default_level='DEBUG', log_path='./logs', routing_mode='daily')
```

```ini
# Layer 2: INI file
[global]
default_level = INFO
backup_count = 30
```

```bash
# Layer 1: Environment variable
D_LOG_LEVEL=WARNING
```

Merge result:
- `default_level` = `WARNING` (environment variables are final)
- `log_path` = `./logs` (Not listed in INI, arguments are maintained)
- `routing_mode` = `daily` (Not listed in INI, arguments are maintained)
- `backup_count` = `30` (INI overrides argument default value)

### 3.4. Complete flowchart for config merging

```
ConfigureLogger() call
  │
  ├─ Layer 3: Store argument values as the base configuration
  │
  ├─ Resolve config_file / config_dict / {env_prefix}_CONFIG
  │   ├─ {env_prefix}_CONFIG set      → use that path (overrides both config_file and config_dict)
  │   ├─ config_file and config_dict  → ValueError (mutual-exclusion violation)
  │   ├─ config_file argument set     → use the INI file at that path
  │   ├─ config_dict argument set     → use the dictionary as Layer 2
  │   └─ none specified               → skip Layer 2
  │
  ├─ Layer 2: Load and merge INI file or dictionary
  │   ├─ Missing/unreadable file          → Fail-Fast (raise exception)
  │   ├─ [global] section                 → override argument values
  │   ├─ [dsafelogger:mod] section        → register module-specific settings
  │   ├─ Extract color_{abbreviation}     → build color-palette override dictionary (see §5.3)
  │   ├─ Type conversion error            → Fail-Fast (raise exception)
  │   └─ diagnose key exists              → ignore (no warning or error)
  │
  ├─ Layer 1: Apply environment variables
  │   ├─ {env_prefix}_LEVEL    → override global level
  │   ├─ {env_prefix}_MODULES  → override module-specific settings (level/path only)
  │   ├─ {env_prefix}_CONSOLE  → override console_out
  │   ├─ {env_prefix}_COLOR    → override color setting
  │   ├─ {env_prefix}_DIAGNOSE → enable diagnose (only when value is "1")
  │   ├─ {env_prefix}_HASH     → override enable_hash
  │   └─ {env_prefix}_MANIFEST → override manifest_path
  │
  │   > v20 clarification: `sens_kws` / `sens_kws_replace` are intentionally not configurable through environment variables.
  │   > This treats them as a protected area similar to `diagnose`, preventing unintended changes to sensitive-keyword handling.
  │   > `file_fmt` / `console_fmt` are also not configurable through environment variables because Formatter instances cannot be represented by environment variables.
  │
  ├─ Resolve sens_kws / sens_kws_replace
  │   ├─ sens_kws_replace=True  → discard built-in keywords and use only sens_kws
  │   └─ sens_kws_replace=False → merge built-in keywords + sens_kws (default behavior)
  │
  ├─ Fail-Fast validation
  │   ├─ log_path permission / disk-space test
  │   ├─ module-specific path permission test
  │   └─ manifest_path permission test (when specified)
  │
  └─ Initialize handlers and bind them to the root logger
```

---

## 4. Operational specifications: Overwriting startup settings using environment variables

Using environment variables, you can control the overall log level applied when `ConfigureLogger` is executed, the output destination for each module, and the presence or absence of various modes without changing the source code or configuration files. Environment variable values ​​override settings in INI files and code during initialization.

The environment variables in this chapter are not dynamically reflected during process operation. In order for the changes to take effect, the target process must be restarted, or there must be an initialization path where `ConfigureLogger` is re-executed.

All control environment variables follow the naming convention based on `ConfigureLogger`'s `env_prefix` parameter (default: `'D_LOG'`). The following explains using the default prefix `D_LOG` as an example.

### 4.1. Complete list of environment variables

| Environment variable | Purpose | Valid values | Override |
|---|---|---|---|
| `{prefix}_LEVEL` | Global default level | `DEBUG`~`CRITICAL` + Registered custom level name | INI `default_level`, argument `default_level` |
| `{prefix}_MODULES` | Module-specific level/output destination | `MOD:LEVEL[,...]` | INI module-specific section |
| `{prefix}_DIAGNOSE` | Diagnostic mode (f_locals expansion) | Valid only for `"1"` | **Cannot be set from INI/arguments (sanctuary)** |
| `{prefix}_CONSOLE` | Forced control of console output | `"1"/"0"`, `"true"/"false"` | INI `console_out`, argument `console_out` |
| `{prefix}_COLOR` | Forced control of color output | `"1"/"0"`, `"true"/"false"` | Override automatic detection |
| `{prefix}_CONFIG` | Override INI file path | File path | Arguments `config_file` and `config_dict` |
| `{prefix}_HASH` | Enabling hash generation | `"1"/"0"`, `"true"/"false"` | INI `enable_hash`, argument `enable_hash` |
| `{prefix}_MANIFEST` | Override manifest file path | File path | INI `manifest_path`, argument `manifest_path` |
| `{prefix}_IPC_LOG_TIMEOUT` | multiprocess version log plane send wait time | positive floating point seconds | multiprocess argument `ipc_log_timeout` |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` | multiprocess version log plane queue capacity | positive integer | multiprocess argument `ipc_log_queue_maxsize` |
| `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` | multiprocess version process-local async queue capacity | positive integer | multiprocess argument `ipc_client_queue_maxsize` |
| `{prefix}_WRITER_FLUSH_BATCH` | flush batch size for multiprocess Writer | positive integer | multiprocess argument `writer_flush_batch` |
| `NO_COLOR` | Forced disabling of color output | If set (value does not matter) | Priority over `{prefix}_COLOR` |

> `NO_COLOR` is an industry standard (https://no-color.org/) and is the only environment variable that is not affected by `env_prefix`.

### 4.2. `{prefix}_LEVEL` (global default level only)

Specify only the global default level. Module specific syntax is not accepted.

- Valid values: In addition to `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (case does not matter), custom level names registered with `register_level()` can also be used.
- Override the `default_level` and ConfigureLogger `default_level` arguments in the INI file

**Design decision: Reason for limitation to global use**

Separating module-specific settings into dedicated `{prefix}_MODULES` ensures that the value of `{prefix}_LEVEL` is a single level name, eliminating parsing ambiguity.

If comma-separated values are specified, Fail-Fast behavior raises `ValueError`, and the error message prompts migration to `{prefix}_MODULES`.

```
ValueError: D_LOG_LEVEL contains comma-separated module specs.
Use D_LOG_MODULES for per-module settings.
Example: D_LOG_LEVEL=INFO  D_LOG_MODULES=ModuleA:DEBUG,ModuleB:ERROR
```
### 4.3. `{prefix}_MODULES` (For individual settings for each module only)

Specify the level and output destination for each module using environment variables.

Format: `MOD_SPEC1,MOD_SPEC2,...`

```bash
D_LOG_MODULES=myapp.db:DEBUG,myapp.api:ERROR:/var/log/api.log
```
- Override module-specific section settings in INI files
- evaluated independently from the global level of `{prefix}_LEVEL`
- Only specified fields (level, path) override INI values, INI-side routing details (routing_mode, max_bytes, etc.) remain unaffected.
- In addition to the 5 built-in level names, you can also use custom level names registered with `register_level()`
- If an individual `MOD_SPEC` has a format violation (e.g. missing a colon), only that element will be skipped with a warning output to stderr, and other normal elements will continue to be applied.

#### 4.3.1. Specify only level (`MOD:LEVEL`)
Change only the level of the target module (e.g. `myapp.db:DEBUG`). The output path and routing settings set for that module on the INI side are maintained.

#### 4.3.2. Full specification (`MOD:LEVEL:PATH`)
Change the output destination individually along with the level. Routing-related settings configured on the INI side are maintained.
* **PATH is only the file name (no path separator)**: The file name is output directly under the entire `log_path`.
* **PATH contains directory structure**: Ignores the entire `log_path` setting and prints directly to the specified full path (absolute or relative).
* **Windows absolute path support**: Everything after the first two colons in the PATH part is interpreted as PATH, so Windows absolute paths such as `myapp.api:ERROR:C:\logs\api.log` can also be specified.

**Default routing when defining a new module with environment variables only:**
`{prefix}_MODULES` expresses only the level and path, so if you specify `PATH` to output an individual file to a new module that does not exist in the INI, the default routing mode for that individual handler is `none` (no routing).

**Technical rationale for integrating module-specific specifications into a single environment variable:**
The Python module name passed to `GetLogger(__name__)` (e.g. `myapp.db.core`) includes a dot (`.`), but the Linux/Bash environment variable naming convention does not allow dots. Providing individual environment variables for each module will cause name conversion parsing bugs and namespace conflicts, so we adopt a method of combining them into a single variable separated by commas.

### 4.4. `{prefix}_DIAGNOSE` (controlling automatic variable expansion)

Diagnostic mode (automatic expansion of local variable `f_locals` when an exception occurs) is enabled only when the environment variable `{prefix}_DIAGNOSE=1` is set. Values other than `"1"` are ignored, and `"true"`, `"yes"`, `"True"`, etc. are not valid values.

**This feature is not provided as an argument to `ConfigureLogger`. Settings from INI files are not allowed at all (protected area).** This is an intentional design decision to structurally prevent development debug settings from leaking into production.

- Since there is no way to write `diagnose=True` in the source code, the accident pattern of ``writing it in the code and forgetting to put it back'' cannot physically occur.
- INI files are often included in version control (git), and the risk of `diagnose = true` being committed and entering the production environment is the same as for arguments in the code. Therefore, the route from the INI file is also blocked.
- Even if the `diagnose` key is listed in the INI file, it will be ignored (no warning or error will be issued, it will be treated as just an invalid key).
- By limiting it to only `"1"`, it prevents unintended activation due to differences in truth value notation depending on the operating environment.
- If it is necessary to enable it in the production environment, it must be done explicitly as an infrastructure layer operation by setting environment variables.

### 4.5. `{prefix}_CONSOLE` and `{prefix}_COLOR` (forced control of console output)

The environment variable `{prefix}_CONSOLE` (valid values: `"1"` / `"0"` or `"true"` / `"false"`: case does not matter) overrides and controls whether log output is output to the console (standard error output).
D This is a specification to align the direction with other parameters of the ecosystem, and even background services designed as `console_out=False` in the source code can be started by overwriting `True` only during development by setting environment variables before startup.

It also supports a function that interprets the environment variable `{prefix}_COLOR` (valid values: `"1"` / `"0"` or `"true"` / `"false"`: case does not matter) and the industry standard `NO_COLOR` environment variable and forcibly controls the enable/disable of ANSI color output.

The priority order of color control is as follows.

1. If `NO_COLOR` is set, color is always disabled regardless of the value.
2. If `NO_COLOR` is not set and `{prefix}_COLOR` is set, that value will be followed.
3. If both are not set, it will be automatically determined by TTY judgment by `sys.stderr.isatty()`

### 4.6. `{prefix}_CONFIG` (Override INI file path)

By specifying a file path in the environment variable `{prefix}_CONFIG`, it overwrites the INI file path specified in the `config_file` argument of `ConfigureLogger`. This allows the same application binary to be launched in different environments (development/staging/production) with different configuration files.

**Relationship with `config_dict`**: If `{prefix}_CONFIG` is set, not only the `config_file` argument but also the `config_dict` argument will be ignored, and the INI file specified by the environment variable will be used as the second layer (the principle that environment variables take precedence over everything else).

### 4.7. `{prefix}_HASH` (Enabling hash generation)

The environment variable `{prefix}_HASH` (valid values: `"1"` / `"0"` or `"true"` / `"false"`: case does not matter) overrides and controls the enable/disable of SHA-256 hash generation for file integrity verification. Override the `enable_hash` and ConfigureLogger `enable_hash` arguments in the INI file.

Operational example to enable hashing only in production environment:

```bash
D_LOG_HASH=true
```
### 4.8. `{prefix}_MANIFEST` (override manifest file path)

By specifying a file path in the environment variable `{prefix}_MANIFEST`, it overrides the manifest file path specified in the `manifest_path` argument of `ConfigureLogger` and the `manifest_path` key in the INI file.

```bash
D_LOG_MANIFEST=/var/log/audit/checksums.txt
```
### 4.9. `{prefix}_IPC_LOG_TIMEOUT` (override multiprocess log plane timeout)

The waiting time for sending normal logs to the log plane queue** in the multiprocess version `dsafelogger.mp.ConfigureLogger()` can be overwritten by the environment variable `{prefix}_IPC_LOG_TIMEOUT`.

**Applicable to:**
- multiprocess version only
- `LOG` hand-off only
- Does not apply to control plane commands such as `ATTACH` / `DETACH` / `STOP` / `REOPEN` / `STATUS`

**Contract:**
- Valid values are **positive floating point seconds**
- Values below `0` or equivalent to `None` are **`ValueError`**
- If the effective value exceeds the internal limit **`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0`**, issue a stderr warning and **clip to 3.0 seconds**
- Environment variables take precedence over API argument `ipc_log_timeout`

```bash
D_LOG_IPC_LOG_TIMEOUT=1.5
```
### 4.10. `{prefix}_IPC_LOG_QUEUE_MAXSIZE` / `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE`

Starting from v23c, the multiprocess version's queue capacity can be overwritten as a startup setting. These are **bootstrap-time only** settings, and changes after starting Writer runtime or after child attach are not reflected. The queue size must not be overwritten by environment variable changes on the child process side, and all children follow the queue size contract contained in `BootstrapContext`.

**Contract:**
- Valid values are **positive integers**
- `0` Below is **`ValueError`**
- For values exceeding `100000`, initialization continues after issuing a stderr warning.
- `{prefix}_IPC_LOG_QUEUE_MAXSIZE` takes precedence over `ipc_log_queue_maxsize` arguments
- `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` takes precedence over `ipc_client_queue_maxsize` arguments
- If `ipc_client_queue_maxsize` is not specified, it will be the same as the effective `ipc_log_queue_maxsize`.

```bash
D_LOG_IPC_LOG_QUEUE_MAXSIZE=20000
D_LOG_IPC_CLIENT_QUEUE_MAXSIZE=5000
```

### 4.11. `{prefix}_WRITER_FLUSH_BATCH`

Since v23g, the multiprocess Writer's flush strategy can be set at startup with `writer_flush_batch`. The default value `1` is per-message flush, which maintains the v23 baseline durability contract. Batch flush is used only when explicitly opting in with a value of `2` or greater.

**Contract:**
- Valid values are **positive integers**
- `0` or less is **`ValueError`**
- For values exceeding `1024`, initialization continues after issuing a stderr warning.
- Environment variables take precedence over API argument `writer_flush_batch`

```bash
D_LOG_WRITER_FLUSH_BATCH=16
```

---

## 5. INI file setting specifications (including dictionary settings)

### 5.1. How to specify the INI file path

The INI file path can be specified in the following two ways, and the environment variable overrides the argument. It is also possible to use dictionaries (`config_dict`) as an alternative to INI files (see §5.7).

```python
# Layer 3: specified by argument
ConfigureLogger(config_file='./config/logging.ini')

# Layer 1: overridden by environment variable
# D_LOG_CONFIG=/etc/myapp/logging.ini
```
- `config_file` defaults to `None` (works without INI file)
- If `config_file` is specified but the file does not exist/reading fails, **Fail-Fast** (immediately throws an exception and stops startup)
- If `config_file` is `None` (default) and `{prefix}_CONFIG` is also unset, it will skip the INI layer and operate only on the third layer (arguments).

### 5.2. INI file format

Adopt an INI format that can be interpreted by the standard library `configparser`. Initialize with `ConfigParser(interpolation=None)` and eliminate the need to escape `%`.

```ini
; D-SafeLogger configuration file
; Global section: [global]
; Module-specific section: [dsafelogger:<module_name>]

[global]
; --- Global settings (correspond to ConfigureLogger arguments) ---
default_level = INFO
log_path = ./logs
pg_name = MyApp
is_async = false
backup_count = 30
archive_mode = true
routing_mode = daily
interval = 10
max_bytes = 10485760
max_lines = 10000
; max_count is None when omitted (overflow-error mode)
suffix_digits = 3
console_out = true
structured = false
fmt = %(asctime)s.%(msecs)03d [%(levelname)-3s] %(message)s
datefmt = %Y-%m-%d %H:%M:%S
enable_hash = true
manifest_path = /var/log/myapp/audit/checksums.txt
sens_kws = my_secret, api_token

; --- Console color palette ---
; ANSI color codes for each level abbreviation (SGR parameter numbers).
; Only specified keys override defaults; omitted levels keep their colors.
; color_dbg = 36
; color_inf = 32
; color_war = 33
; color_err = 31
; color_cri = 1;31

; --- Module-specific settings ---
; Split sections using the [dsafelogger:<module_name>] format

[dsafelogger:myapp.db]
level = DEBUG
; If path is omitted, inherit the global log_path; routing is none

[dsafelogger:myapp.api]
level = ERROR
path = /var/log/myapp/api.log
; When path is specified, independent routing can be configured
routing_mode = size
max_bytes = 10485760
max_count = 5
suffix_digits = 2

[dsafelogger:myapp.auth]
level = WARNING
path = auth_events.log
; If only a filename is specified, output under the global log_path
```
> **`interpolation=None` design rationale**: `configparser` interprets `%` as an interpolation character by default, so the `%%` escape is required when writing log format strings (`%(asctime)s`, etc.). This significantly impairs usability, so `interpolation=None` is adopted to eliminate the need for escaping. There is no downside to this design decision, as D-SafeLogger's INI file does not require variable interpolation.

### 5.3. Key list of global section `[global]`

One-to-one correspondence with ConfigureLogger arguments. `config_file` itself is not subject to configuration (because it is a self-reference).

| INI key | Corresponding argument | Type | Notes |
|---|---|---|---|
| `default_level` | `default_level` | str | Custom level names can also be used |
| `log_path` | `log_path` | str | |
| `pg_name` | `pg_name` | str | |
| `env_prefix` | `env_prefix` | str | v20: Changes in INI/config_dict are prohibited. When written, a stderr warning is issued and ignored. Normally no changes are required |
| `is_async` | `is_async` | bool | In addition to `true`/`false`, `1`/`0`/`yes`/`no`/`on`/`off` are also allowed (case does not matter) |
| `backup_count` | `backup_count` | int | |
| `archive_mode` | `archive_mode` | bool | In addition to `true`/`false`, `1`/`0`/`yes`/`no`/`on`/`off` are also allowed |
| `routing_mode` | `routing_mode` | str | |
| `interval` | `interval` | str or int | `10` or `12h` or `1d` |
| `max_bytes` | `max_bytes` | int | |
| `max_lines` | `max_lines` | int | |
| `max_count` | `max_count` | int or omitted | If omitted/empty value is None (upper limit reached error mode) |
| `suffix_digits` | `suffix_digits` | int | |
| `console_out` | `console_out` | bool | In addition to `true`/`false`, `1`/`0`/`yes`/`no`/`on`/`off` are also allowed |
| `structured` | `structured` | bool | In addition to `true`/`false`, `1`/`0`/`yes`/`no`/`on`/`off` are also allowed |
| `fmt` | `fmt` | str | No escaping required because `interpolation=None` |
| `file_fmt` | `file_fmt` | str | v20 added. Custom format exclusively for file output. Takes precedence over `fmt`. If omitted, falls back to `fmt` |
| `console_fmt` | `console_fmt` | str | v20 added. Custom format for console output only. Takes precedence over `fmt`. If omitted, falls back to `fmt` |
| `datefmt` | `datefmt` | str | Same as above |
| `enable_hash` | `enable_hash` | bool | In addition to `true`/`false`, `1`/`0`/`yes`/`no`/`on`/`off` are also allowed |
| `manifest_path` | `manifest_path` | str | Default/empty value is None (sidecar only) |
| `sens_kws` | `sens_kws` | str (CSV) | Specify sensitive keywords separated by commas (e.g. `my_secret, api_token`). Added to built-in keywords |
| `sens_kws_replace` | `sens_kws_replace` | bool | `true`, completely replace the built-in keyword with `sens_kws`. In addition to `true`/`false`, `1`/`0`/`yes`/`no`/`on`/`off` are also allowed |
| `color_{abbreviation}` | — | str | The numeric part of the ANSI SGR parameter (for example, `36`, `1;31`, `38;5;208`). `color_dbg`, `color_inf`, `color_war`, `color_err`, `color_cri` are built in. Custom level abbreviations registered with `register_level()` can also be used. This cannot be configured from ConfigureLogger arguments or environment variables (Layer 2 only). An empty string disables coloring for the corresponding level |
| `diagnose` | — | **Invalid** | Ignored even if specified (protected area) |

**Type conversion and validation**: For type conversion of string values read from INI files (converting `is_async` to bool, `max_bytes` to int, etc.) or formatting violations, immediately throw an exception and stop startup (Fail-Fast) instead of falling back to the default value. Silent fallback to default values creates the most dangerous failure pattern: settings appear to be working even though they are not reflected.

**Null value processing for optional keys**: If the value is an empty string like `max_count =` (null value), it is treated as the same as "key absent" (`None`). Null values ​​for optional format keys such as `fmt =` / `file_fmt =` / `console_fmt =` / `datefmt =` are similarly treated as "unspecified" and subject to normal fallback rules.

**Handling of unknown keys**: If an unknown key is listed in the `[global]` section, that key will be ignored after outputting a warning to stderr. Unlike type conversion errors for existing valid keys, unknown keys are subject to notification of misconfiguration, but are not immediately disabled. However, keys with the `color_` prefix are recognized on a pattern basis, so they are not included in the fixed key list. The `color_` prefix key dynamically verifies whether the abbreviation part matches the built-in 5-level or custom-level abbreviation registered with `register_level()`, and if it is an unknown abbreviation, a warning is output to stderr and skipped (not Fail-Fast).

**`color_{abbreviation}` key validation**: The following validations apply to keys with the `color_` prefix:
* **Unknown abbreviation**: If the part after `color_` does not match a valid abbreviation (built-in + custom level), output a warning to stderr and ignore the key.
* **Illegal characters**: If the value contains characters other than `0-9` and `;`, output a warning to stderr and ignore the key.
* **Empty string**: Enabled. Disable colorization for the corresponding level (output without color)
* In any of the above cases, processing continues with warning + skip instead of Fail-Fast (throwing an exception). Application of other valid color settings is not prevented.

**Custom level name validation**: The `default_level` and `level` keys in the module-specific section accept custom level names registered with `register_level()` in addition to the built-in 5 levels. If an unregistered level name is specified, `ValueError` is sent (Fail-Fast).

**v23j: unified post-merge validation**: After Python API arguments, INI/config_dict, and environment variables are merged, the final file-sink configuration is validated again with the same rules. `structured=True` combined with `fmt` / `file_fmt` / `console_fmt`, unregistered `default_level`, `backup_count < 0`, `max_count < 1`, `suffix_digits < 1`, and `startup_interval` with `interval < 1` are `ValueError` regardless of where they were specified. Python API bool arguments (`is_async`, `archive_mode`, `console_out`, `structured`, `enable_hash`, `sens_kws_replace`) accept only actual `bool` values; string truthiness/falsiness is not interpreted at the API layer.

**v23j: fail-fast invalid feature combinations**: The following combinations are `ValueError` rather than warning-based correction, because the requested feature cannot take effect or would break semantics.

```text
routing_mode='none' + enable_hash=True
routing_mode='none' + backup_count > 0
routing_mode='none' + archive_mode=True
cyclic routing + enable_hash=True
cyclic routing + backup_count > 0
cyclic routing + archive_mode=True
size/count + max_count=None + backup_count > 0
size/count + max_count=None + archive_mode=True
archive_mode=True + backup_count=0
manifest_path specified + enable_hash=False
```

Cyclic routing means `cyclic_weekday` / `cyclic_month` / `size|count with max_count specified`. `size/count + max_count=None` is overflow-error mode; it is designed for full retention until an explicit capacity-design failure, so it is not combined with generation management (`backup_count` / `archive_mode`).

### 5.4. Module-specific section `[dsafelogger:<module_name>]`

The section name after `:` corresponds to the module name (the name passed to `GetLogger(__name__)`).

A section with an empty module name like `[dsafelogger:]` is invalid and will send `ValueError` (Fail-Fast).

| INI key | Required | Type | Description |
|---|---|---|---|
| `level` | Required | str | Log level for this module (custom level name can also be used) |
| `path` | Optional | str | Output path. If omitted, global `log_path` / `pg_name` is inherited |
| `routing_mode` | Optional | str | `path` Valid only when specified. If omitted `none` |
| `max_bytes` | Optional | int | `routing_mode=size` Required |
| `max_lines` | Optional | int | Required when `routing_mode=count` |
| `max_count` | Optional | int or omitted | Cyclic upper limit |
| `suffix_digits` | Optional | int | Inherits global value if omitted |
| `backup_count` | Optional | int | Inherits global value if omitted |
| `archive_mode` | Optional | bool | Inherits global value if omitted |

**Routing when `path` is omitted**:
Module-specific sections omitting `path` are intended for level changes only. The output destination is the same file as the global settings, so independent routing has no meaning. If a routing-related key such as `routing_mode` is specified when `path` is omitted, **output a warning to stderr and ignore that key**.

**Default routing when `path` is specified**:
The default routing for a module that specifies `path` and outputs to its own file is `none` (no routing). This assumes a simple use case where "rotation is not required just by separating the output destinations". If rotation is required, explicitly specify `routing_mode`.

**Module-specific control of hash generation**: Hash generation is a global setting only. Individual specification of `enable_hash` / `manifest_path` in module-specific sections is not supported even in v15a. It is simpler to apply uniformly to all files to be routed, and there is no omission in auditing.

**v23j: module-specific validation parity**: A module-specific file sink with `path` receives the same validation as the global file sink for routing, generation management, hash, and numeric ranges. `level` is validated with `get_valid_level_names()` regardless of whether `path` is present, and unregistered names are `ValueError`. In the multiprocess API, module-specific `level` is also applied to the worker-side logger during attach.

### 5.5. Merge priority of INI files and environment variables `{prefix}_MODULES`

Settings for each module can be specified using both INI and the environment variable `{prefix}_MODULES`, and the environment variable takes precedence.

```ini
; INI: myapp.db is DEBUG and uses daily routing to its own file
[dsafelogger:myapp.db]
level = DEBUG
path = /var/log/db.log
routing_mode = daily
```

```bash
# Environment variable: emergency change myapp.db level to ERROR
D_LOG_MODULES=myapp.db:ERROR
```
In this case, the level of `myapp.db` is overwritten by `ERROR`. Since only `MOD:LEVEL` is specified in the environment variable (no path), all settings such as `path`, `routing_mode`, `max_bytes`, etc. set on the INI side are maintained**. The environment variable `{prefix}_MODULES` only overrides the level and output path; the INI side routing details are not affected.

### 5.6. INI parser implementation policy that maintains Zero Dependency

Instead of using external libraries (D-Settings, etc.), D-SafeLogger includes a dedicated minimal INI loader using the standard library `configparser.ConfigParser(interpolation=None)`.

**Design Rationale**: A clear trade-off in favor of "full portability (zero external dependencies)" as the underlying library over the DRY principle (code deduplication). The logger is the foundation at the bottom of any project, and other D ecosystem libraries (such as D-Settings) may depend on D-SafeLogger. To avoid circular dependencies, the logger itself must not depend on anything external.

**Handling of unknown sections**: Sections other than `[global]` and `[dsafelogger:...]` are ignored after outputting a warning to stderr. This allows for coexistence with other tools and the mixing of alternative comment sections, while ensuring that configuration errors are not overlooked.

### 5.7. Dictionary-based configuration (`config_dict`)

As an alternative to the INI file, passing a dictionary directly to the `config_dict` argument of `ConfigureLogger` enables second-layer configuration that can be completed within the code. It is especially useful in test environments and use cases where you generate configurations programmatically.

#### 5.7.1. Dictionary structure

`config_dict` is of type `dict[str, dict[str, str]]` and has the same section/key structure as the INI file.

```python
ConfigureLogger(
    config_dict={
        'global': {
            'default_level': 'INFO',
            'log_path': './logs',
            'backup_count': '30',
            'sens_kws': 'my_secret, api_token',
        },
        'dsafelogger:myapp.db': {
            'level': 'DEBUG',
        },
        'dsafelogger:myapp.api': {
            'level': 'ERROR',
            'path': '/var/log/myapp/api.log',
            'routing_mode': 'size',
            'max_bytes': '10485760',
        },
    }
)
```
**All values ​​are string types**: All values ​​in the dictionary are specified as strings so that they go through the exact same type conversion and validation pipeline as when reading from an INI file. Passing `int` or `bool` directly results in `TypeError` (Fail-Fast). This ensures that type conversion and validation code paths are completely unified whether using INI files or dictionaries.

#### 5.7.2. Section name and key rules

* **Global section**: The key name is `'global'`. The same keys as the key list in §5.3 can be used.
* **Module-specific section**: The key name is `'dsafelogger:<module_name>'`. Same as the key list in §5.4
* **`diagnose` key**: ignored like INI file (sanctuary)
* **Unknown key/unknown section**: Treated the same as INI files (unknown keys are stderr warnings + ignored, unknown sections are also stderr warnings + ignored)
* **Empty module name**: `'dsafelogger:'` (empty module name) is `ValueError` (same as INI)

#### 5.7.3. Exclusive constraint with `config_file`

`config_file` and `config_dict` are **exclusive**, and if both are specified at the same time, `ValueError` will be raised.

```python
# OK: config_file only
ConfigureLogger(config_file='./config/logging.ini')

# OK: config_dict only
ConfigureLogger(config_dict={'global': {'default_level': 'DEBUG'}})

# NG: both specified -> ValueError
ConfigureLogger(config_file='./logging.ini', config_dict={'global': {'default_level': 'DEBUG'}})
```
**Relationship with the `{prefix}_CONFIG` environment variable**: If `{prefix}_CONFIG` is set, both `config_file` and `config_dict` are overwritten, and the INI file specified by the environment variable is used as the second layer. In this case, the exclusion check for `config_file` and `config_dict` is not performed (because the environment variable takes precedence over everything else, exclusion violations in arguments become irrelevant).

#### 5.7.4. Validation

The following validations apply to `config_dict` (all Fail-Fast):

| Condition | Exception |
|------|------|
| `config_dict` is not of type `dict` | `TypeError` |
| Section value is not of type `dict` | `TypeError` |
| Value is not of type `str` | `TypeError` |
| Specified at the same time as `config_file` | `ValueError` |
| Empty module name section `'dsafelogger:'` | `ValueError` |
| Value type conversion error (bool, int, etc.) | `ValueError` (same as INI) |

---

## 6. Log format and structured log specifications

### 6.1. Default format string
The following unified format is output by default for both files and console (when enabled).
`%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s`
* **Date and time format**: ISO8601-like `%Y-%m-%d %H:%M:%S`
* **Level name abbreviation**: In addition to the built-in `DBG`, `INF`, `WAR`, `ERR`, `CRI`, the 3-character abbreviation of the custom level registered with `register_level()` is also output in the same format.
* **Contextualize information**: Added to the end of the message in the format `[task_id:42 worker:db_sync]` (described later in the specification).

### 6.2. Custom log format override settings (fmt / datefmt)
You can arbitrarily override the default format by passing strings to the `fmt` and `datefmt` arguments of `ConfigureLogger`.

* **fmt (str | None)**: Corresponds to the first argument of `logging.Formatter`. Log message format including `%(message)s` etc.
* **datefmt (str | None)**: Corresponds to the second argument of `logging.Formatter`. Date and time format applied to `%(asctime)s`.

In the detailed design and implementation, advanced customization (such as style selection) is also allowed by passing an **instance** of `logging.Formatter` or a subclass directly to the `fmt` argument.

### 6.3. Formatter individual specification (v20 new feature)

Separate Formatters can be specified for file output and console output. It supports use cases such as outputting OTel's trace_id only to a file as JSON and keeping concise text in the console.

```python
ConfigureLogger(
    file_fmt=StructuredFormatter(),     # JSON for files
    console_fmt='%(levelname)s %(message)s',  # concise text for console
)
```

**Resolution priority**:

```
file_fmt specified -> use for file Sink
file_fmt is None or empty string -> fall back to fmt
fmt is also None -> default format

console_fmt specified -> use for console Sink
console_fmt is None or empty string -> fall back to fmt
fmt is also None -> default format
```
* `fmt` is the existing overall default Formatter (maintaining backward compatibility)
* `file_fmt` / `console_fmt` accept `str` or `logging.Formatter` instances
* Can also be set as `file_fmt`, `console_fmt` keys in INI / config_dict (see §5.3)
* If `fmt` / `file_fmt` / `console_fmt` / `datefmt` is an empty string from INI / config_dict, treat it as "unspecified" and apply a fallback.
* `StructuredFormatter` outputs vendor-neutral extra attributes of `LogRecord` to the JSON top level in addition to `contextualize()` information (excluding standard `LogRecord` keys and internal `_ds_*` attributes)
* If `file_fmt` / `console_fmt` is not specified, the behavior is completely the same as v18 (non-destructive change)

### 6.4. Structured log (JSON Lines output)
By specifying `structured: bool = False` for `ConfigureLogger`, it is possible to output in JSON Lines format (1 JSON per line).
Structured logging and Append-Only architecture are **completely orthogonal**, so the underlying file management layer (I/O layer), such as routing and generation management, operates as is without any changes (the output is just replaced with JSON).
`structured=True`, the context information given with `contextualize()` is output as a top-level field of the JSON object, not as a suffix at the end of the message.
Simultaneous specification of this function (`structured=True`) and custom format (character string specification for `fmt` / `file_fmt` / `console_fmt` parameters, and all cases of Formatter instance specification) will cause `ValueError` to be sent as an exclusive specification violation.

---

## 7. Determination of log file name and routing/generation management specifications

### 7.1. Rules for determining base file name (pg_name)
If there is no full specification for each module, the log file name is determined based on the combination of `log_path` (output destination directory) and `pg_name` (program name).
* **Basic configuration**: `{log_path}/{pg_name}` (Automatically generated and sanitized with `os.makedirs` when the directory does not exist)
* The actual output filename is this base filename with a specific suffix added.

**`pg_name` sanitization rules**:
If `pg_name` contains characters prohibited in OS file names (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`), they are replaced with `_`. This is not rejected with Fail-Fast; it is a logging-foundation requirement to generate safe file names without blocking startup.

### 7.2. Technical Background of Append-Only Architecture
Clarify the decision as to why the industry standard "rename method" will not be adopted when releasing OSS.
* **Historical background**: The renaming method became popular due to its simplicity, ``the current log is always `app.log`'', but it locks the file. **In a Windows environment, renaming will result in a Permission Error even if another monitoring tool etc. has the file open, a fatal flaw that will bring down the entire backend service**.
* **Technical advantage**: D-SafeLogger uses **Append-Only (does not perform any renaming, just switches the stream to a file with a date or sequential number from the beginning)** as the premise of its architecture, and completely eliminates this locking problem in O(1). Similar ideas can be found in specific options such as Logback and Log4j2, but no design with this as the default core exists in the Python ecosystem.

### 7.3. Routing mode (routing_mode) detailed explanation

#### 7.3.1. No routing (`none`)
* **Behavior**: Default. Continue appending to a single file. No suffix (`{pg_name}.log`).
* **v22a: External log rotation coexistence**: When coexisting with external rotators such as `logrotate` on Linux/Unix systems, only this mode is officially supported. After the external side executes rename + create, the application side explicitly calls `ReopenLogFiles()` to reopen the new inode.
* **Restrictions**: `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / Routing, in which D-SafeLogger itself handles file switching, such as cyclic, and external rotation operation should not be mixed. `ReopenLogFiles()` sends `ValueError` if any file sink on writer-side is `routing_mode != 'none'`.

#### 7.3.2. Absolute date and time base (`daily`, `hourly`, `min_interval`)
Routing (switching) according to the absolute time on the clock. Subject to generation management.
* **daily**: Toggled when changing date. Suffix `YYYYMMDD`
* **hourly**: Switch every hour on the hour (0 minutes). Suffix `YYYYMMDD_HH`
* **min_interval**: Toggle at specified minutes interval. Suffix `YYYYMMDD_HHMM`
  * **[Restrictions]**: In this mode, the argument `interval` must be a **numeric value only (unit: minutes)**, and only numbers that are evenly divisible by 60 can be specified to align on the hour. Valid values ​​are `{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}`.

#### 7.3.3. Startup time (relative) base (`startup_interval`)
Routes at specified intervals starting from the time the application starts. Subject to generation management.
* **Units/Parameters**: The minimum switching unit is "minutes". In addition to integers, the `interval` argument accepts flexible settings such as string specifications such as `'12h'` and `'1d'`.
* **Suffix**: Adopt the absolute date and time (`YYYYMMDD_HHMMSS`) of the moment the switch was executed.

#### 7.3.4. Resource base (`size`, `count`)
Switch files using file size (`max_bytes`) or number of log lines (`max_lines`) as a threshold. The suffix in this mode is a sequential number, **the number of digits is controlled by the argument `suffix_digits` (default: 3), and zero padding is applied in all operations. ** `max_bytes > 0` is required for `routing_mode='size'`, `max_lines > 0` is required for `routing_mode='count'`, and anything below 0 is Fail-Fast (`ValueError`).
The essential purpose of operation differs depending on the presence or absence of the parameter `max_count`.

* **Cyclic mode (`max_count` specified)**
  * Usage: Rotate logs within a limited space without filling up the disk.
  * The suffix is ​​cyclically added in the range `.000` to `.{max_count-1}`. (*If `suffix_digits=2`, it will be formatted as `.00` ~ `.{max_count-1}`)
  * After reaching the upper limit, it returns to `0`, **overwrites** the existing file, and continues writing. **Not applicable** to the generation management function.

* **Upper limit reached error mode (`max_count` Not specified/None)**
  * Usage: Insurance for strict systems that want to absolutely prevent log loss or unintentional overwriting.
  * **Design intent**: The purpose of this mode is to "maintain all logs without loss," and the design intent is contradictory to generation management, which deletes old files, so it is also **excluded** from generation management. The number of digits specified by `suffix_digits` is for the designer to specify the upper limit of the number of files that the system expects.
  * **Behavior**: The serial number increases monotonically until the maximum value of `suffix_digits` (for 3 digits, `.999`). When the limit is reached, it is considered a "capacity design error" and `OverflowError` is sent when switching files to stop the application execution.
  * **Relationship with `backup_count` / `archive_mode`**: This mode is designed to preserve all logs, so generation management that processes old files contradicts its design intent. Therefore, specifying `backup_count > 0` or `archive_mode=True` is not corrected; `ConfigureLogger()` fails fast with `ValueError`.

#### 7.3.5. Day of week/month cyclic base (`cyclic_weekday`, `cyclic_month`)
A mode that rotates logs in periodic periods. It is always overwritten after one cycle and is **not subject to generation management**.
* **cyclic_weekday**: Day of the week. The suffixes are `sun`, `mon`, `tue`, etc.
* **cyclic_month**: Month. The suffix is ​​a number from `01` to `12`.

### 7.4. Typical use cases (TIPS) for routing configuration
* **Web service/resident daemon**:
  * `routing_mode='daily'`, `backup_count=30`, `archive_mode=True`
  * (Intent: Change files once a day, and leave files for the past 30 days in a ZIP archive without deleting them. The strongest configuration to prevent disk pressure)
* **Small CLI tools / ephemeral batch processing**:
  * `routing_mode='none'` (default)
  * (Intent: readability of one file rather than log persistence. If it ends up in a few kilobytes, the routing operation itself is useless)
* **Ultra-high Message IO debugging**:
  * `routing_mode='size'`, `max_bytes=10485760` (10MB), `max_count=10`
  * (Intent: Use cyclic mode to prevent disk puncture. Write only the most recent logs in a circular manner forever within a total area of about 100MB)
* **Large-scale microservices (INI usage example)**:
  * Centrally manage output destinations and levels for each module using the INI file, and when responding to a failure, overwrite the level of a specific module using environment variables and restart
  * (Intent: achieve both visibility of settings and quick response during operation)
* **Audit/Compliance**:
  * `routing_mode='daily'`, `backup_count=365`, `archive_mode=True`, `enable_hash=True`, `manifest_path='./audit/checksums.txt'`
  * (Intent: Keep all logs for one year and detect tampering with hash. Check the existence of all files and list hash history in manifest)

### 7.5. Switching flow during routing and generation management (purge/archive) specifications
In routing modes where generation management (`backup_count > 0`) is set, such as date/time-based modes, file switching (Routing) and processing (Purge/Archive) follow this flow.

1. **Switching trigger**: Immediately before log `emit`, the Handler asks each Strategy whether switching is necessary.
2. **Append-Only file change**: If a switch is required, `close` the previous stream and `open` the file with the new name with the updated suffix.
3. **Hash generation (`enable_hash=True`) and starting a separate thread in the background**:
   Start a background worker immediately after switching to avoid blocking I/O on the main thread. If `enable_hash=True` and **non-cyclic** and `backup_count > 0`, hash generation is performed in advance in the purge/archive worker. If `enable_hash=True` and **non-cyclic** and `backup_count=0`, start an independent `HashWorker`. The combination of cyclic routing (`cyclic_weekday` / `cyclic_month` / `size|count + max_count specified`) and `enable_hash=True` breaks hash semantics when the same file name is reused, so `ConfigureLogger()` fails fast with `ValueError`. These workers are managed as join targets during safe shutdown. See §7.6 for details on hash generation.
4. **Identification of "target file" in generation management**:
   Sort log files in the same family within the directory by modification time, and identify the old log files that exceed the retention count defined by `backup_count` and therefore should be purged (deleted). **When identifying target files, use strict filtering that only targets filename prefixes exactly matching `pg_name`, to prevent false matches caused by prefix matching (for example, `pg_name='App'` also matching `AppServer_*.log`).** Specifically, target files must exactly match either `{pg_name}.log` (NoneStrategy) or `{pg_name}_{suffix}.log` (other strategies).
5. **Final processing of old files (delete or archive)**:
   * **Normal mode (`archive_mode=False`)**: `unlink` (delete) identified old files as is, completely discarding them from disk. **When `enable_hash=True`, the corresponding `.sha256` sidecar file is also deleted.**
   * **Archive mode (`archive_mode=True`)**: Instead of deleting identified old files, compress and save them in ZIP format or similar. **When `enable_hash=True`, include the corresponding `.sha256` sidecar file in the ZIP and delete the original sidecar file.**
     * **[Preventing storage exhaustion]**: Archiving consumes work space. Therefore, before starting the compression process, check the storage free space (`shutil.disk_usage`, etc.) and stop the process if it seems to be insufficient. Prioritizing safety, a warning is sent to the console, etc. (the process itself is interrupted at that point).
6. **Self-repairability**: If deletion or archiving fails due to a lock from another process on Windows, etc., only a warning will be output to the console and the process will be retried (self-repair) at the next switching timing.
7. **Maintenance serialization of the same family**: Purge/archive belonging to the same `directory + pg_name` will not be executed in parallel. To avoid duplicate deletion, duplicate zipping, and frequent conflict warnings, maintenance of the same family is serialized in key units.

### 7.6. File Integrity Verification Specification

The `enable_hash` parameter of `ConfigureLogger` provides a function to automatically generate the SHA-256 hash of the write-completed file when switching files during routing. This feature is opt-in (disabled by default), and if you do not use it, no additional processing will occur.

#### 7.6.1. Design philosophy
This function generates a SHA-256 hash for a file that has been written, not every time it is written, but when the file is switched due to routing.

* **Minimized impact on log body**: Hash computation is enabled only in non-cyclic mode and is performed in a separate thread, similar to purge/archive. Don't block any I/O on the main thread (Fire-and-Forget). However, it is subject to bounded wait during safe shutdown.
* **File Integrity Guarantee**: The meaning of the hash is clear because it only targets “confirmed files” that have been written.
* **No hash exists for active file**: Do not generate a hash for the file currently being written. This is because the intermediate state hash has no meaning.

#### 7.6.2. Sidecar file (`.sha256`)

When switching files, a `{original_filename}.sha256` sidecar file is automatically generated for the completed source file.

**Format**: `sha256sum -c` compatible format (one line)

```
a1b2c3d4e5f6789... (64-character hexadecimal SHA-256 hash)  MyApp_20260328.log
```
* The hash and file name are separated by **two half-width spaces** (`sha256sum` compatible)
* For the file name, write the **relative path (file name only)**. Design the verification so that it does not break even if the log set is moved (archived) to another location.

Verification method:

```bash
cd logs/
sha256sum -c MyApp_20260328.log.sha256
# MyApp_20260328.log: OK
```

#### 7.6.3. Manifest file

Hash history file of all routed files, generated when `manifest_path` is specified.

**Format**:

```
[2026-03-28T23:59:59.123] a1b2c3d4e5f6789...  MyApp_20260328.log
[2026-03-29T23:59:59.456] b2c3d4e5f6789a1...  MyApp_20260329.log
```
Each line consists of:

| Field | Content | Format |
|------------|------|------|
| Timestamp | Hash confirmation date and time | `[ISO8601]` (with milliseconds) |
| Hash value | SHA-256 (64 characters) | Hexadecimal string |
| File name | Target log file | Relative path (file name only) |

**Operating specifications**:
* **Append format**: Append one line each time routing occurs. No overwriting
* **Assigning a timestamp**: Records the date and time when the hash is finalized, and serves as a trail of "when writing was completed."
* **Directory automatic generation**: If the `manifest_path` directory does not exist, it will be automatically created with `os.makedirs(exist_ok=True)`.
* **File name is relative path**: The file name in the manifest should only be the file name (does not include the directory part)
* **Serialization**: Additions to the same `manifest_path` are always done one thread at a time. This is to prevent manifest line corruption and line-by-line conflicts.

**Manifest operational value**:
* **File loss detection**: Files that are listed in the manifest but do not exist on the disk can be determined to have been "deleted." Sidecar files alone cannot detect when files and sidecars are deleted together
* **Improved tampering resistance**: By storing the manifest in a separate directory and with different permissions from the log itself, even if the log file is manipulated by an attacker, it can be detected by the inconsistency with the manifest.
* **Overview of history**: You can instantly check whether all logs for the past N days are complete by checking the number of lines in one manifest file.

#### 7.6.4. Execution order and threading model

Hash generation must be completed before purge/archive (because purge calculates the hash before deleting the file). Guarantee ordering using the following method:

| Condition | Execution method |
|------|---------|
| `enable_hash=True` and non-cyclic and `backup_count > 0` | Pre-execute hash generation in `PurgeWorker` / `ArchiveWorker` |
| `enable_hash=True` and non-cyclic `backup_count=0` | Start independent `HashWorker` with Fire-and-Forget |
| Cyclic routing and `enable_hash=True` | `ConfigureLogger()` fails fast with `ValueError` |
| `enable_hash=False` | No hash-related processing |

If hash generation fails (such as `OSError`), processing continues with only a warning output to stderr, similar to the self-healing nature of purge.

**Atomic sidecar writes**: To avoid exposing a partially written `.sha256` sidecar externally, write to a temporary file first and then atomically replace the target file with `os.replace()`.

#### 7.6.5. Considerations in cyclic mode

In the `max_count` specification mode (`is_cyclic()=True`) of `cyclic_weekday` / `cyclic_month` and `size`/`count`, file names are reused. Cyclic mode does not preserve history, so hash verification semantics cannot be preserved. In v23j, combining cyclic routing with `enable_hash=True` is not corrected; `ConfigureLogger()` fails fast with `ValueError`. This is a design decision to avoid obscuring the semantics of the manifest/sidecar file.

#### 7.6.6. Validation

| Condition | Behavior |
|------|------|
| `enable_hash=False` and `manifest_path` specified | Fail-fast (`ValueError`). A manifest without hash generation has no supported semantics |
| `routing_mode='none'` and `enable_hash=True` | Fail-fast (`ValueError`). No routing occurs, so there is no hash generation point |
| Cyclic routing and `enable_hash=True` | Fail-fast (`ValueError`). File name reuse prevents meaningful hash verification semantics |
| `routing_mode='size'` and `max_bytes <= 0` | `ConfigureLogger` Fail-Fast (`ValueError`) |
| `routing_mode='count'` and `max_lines <= 0` | `ConfigureLogger` Fail-Fast (`ValueError`) |
| `manifest_path` directory is not writable | Fail-Fast (`PermissionError`) when `ConfigureLogger` |

#### 7.6.7. Out of scope

* **HMAC signature**: HMAC signing with a private key introduces fundamentally different key-management responsibilities (storage location, environment-variable passing, rotation), which exceed D-SafeLogger's role as a lightweight, zero-dependency foundation library. Enterprise use cases that require signatures should use external tooling, such as another D-ecosystem library, with D-SafeLogger-generated hashes as input.
* **CLI verification command**: v15a does not add a hash verification subcommand to the `dsafelogger` CLI. Because the sidecar format is compatible with `sha256sum -c`, verification can be performed immediately with standard OS commands.

---

## 8. Basic design and implementation policy of CLI tool (`dsafelogger`)
Append-Only routing has the advantage of avoiding fatal file locks, but has the disadvantage that ``because the name of the file to write to changes dynamically, it is not always possible to `tail -f` with the same `app.log`.'' To overcome this, a **dedicated CLI utility set** is included in the package.

### 8.1. Provided commands (subcommands)
Prioritizing the ease of entering commands on the CLI (omitting hyphens when typing), the command name is `dsafelogger`, which is the PyPI package name `d-safelogger` without the hyphen.
* **`dsafelogger init`**: Output the INI configuration file template to **standard output**. The design does not take a file path as an argument, and the user can freely control the save destination using shell redirection. This avoids the complexity of checking to overwrite existing files, and makes it easy to combine with pipes and redirects.
* **`dsafelogger ls [log_dir]`**: Parse the D-SafeLogger files in the specified directory and list which log of which program is the latest active file.
* **`dsafelogger tail -f <log_dir> <pg_name> [options]`**: Automatically determines and follows the latest log file of the specified program.
  * **Transparent file following:** Even if the source application changes files due to log "day crossing" etc. during output, the CLI dynamically detects this and transparently replaces `tail` with the new file and continues output.

#### 8.1.1. Example of using `dsafelogger init`

```bash
# Generate a template and save it to a file
dsafelogger init > ./config/logging.ini

# Review the contents before saving
dsafelogger init | less
```

#### 8.1.2. `dsafelogger init` output sample

All configuration keys are commented out in the template, and inline comments explain each key's role and option choices. Users can create configuration files by simply uncommenting the necessary lines and editing the values.

```ini
; =============================================================================
; D-SafeLogger configuration template
; Generated by: dsafelogger init
;
; Lines starting with ';' are comments.
; Uncomment and modify values as needed.
; =============================================================================

[global]

; --- Basic ---
; default_level = INFO
; log_path = .
; pg_name = Default
; env_prefix = D_LOG
; console_out = true
; is_async = false

; --- Log format (choose ONE) ---
;
;   Option A: Human-readable (default)
;     Customizable with fmt/datefmt.
;
; fmt = %(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s
; datefmt = %Y-%m-%d %H:%M:%S
;
;   Option B: Structured JSON Lines
;     Cannot be combined with fmt/datefmt.
;
; structured = false

; --- Routing mode (choose ONE) ---
;
;   'none'       : Single file, no switching (default)
;   'daily'      : Switch at midnight
;   'hourly'     : Switch every hour
;   'min_interval'      : Switch at fixed-minute boundaries
;   'startup_interval'  : Switch after elapsed time from startup
;   'size'       : Switch when file exceeds max_bytes
;   'count'      : Switch when file exceeds max_lines
;   'cyclic_weekday'    : Overwrite by day-of-week (7 files)
;   'cyclic_month'      : Overwrite by month (12 files)
;
; routing_mode = none

;   Parameters for 'min_interval':
;     interval must be a divisor of 60 (5, 10, 15, 20, 30, etc.)
; interval = 10

;   Parameters for 'startup_interval':
;     integer (minutes) or duration string ('12h', '1d')
; interval = 10

;   Parameters for 'size':
; max_bytes = 10485760

;   Parameters for 'count':
; max_lines = 10000

;   Parameters for 'size' / 'count' (cyclic mode):
;     Omit or leave empty for overflow-error mode (keep all files).
; max_count =
; suffix_digits = 3

; --- Retention (requires routing_mode != 'none') ---
;
;   backup_count: Number of old files to keep. 0 = no deletion.
;   archive_mode: If true, old files are ZIP-archived instead of deleted.
;                 Only meaningful when backup_count > 0.
;
; backup_count = 0
; archive_mode = false

; --- Integrity verification (requires routing_mode != 'none') ---
;
;   enable_hash:   Generate .sha256 sidecar on file switch.
;   manifest_path: Append hash history to this file.
;                  Only meaningful when enable_hash = true.
;
; enable_hash = false
; manifest_path =

; --- Console color palette ---
;
;   Customize ANSI color codes for each log level.
;   Values are SGR parameter numbers (without \033[ prefix and m suffix).
;   Only specified keys override defaults; omitted levels keep their colors.
;
;   Common codes:
;     30=black, 31=red, 32=green, 33=yellow, 34=blue, 35=magenta, 36=cyan, 37=white
;     90-97=bright variants (90=dark gray, 91=bright red, ...)
;     1=bold, 4=underline, 1;31=bold red
;     38;5;N=8-bit color, 38;2;R;G;B=24-bit true color
;     Empty value disables color for that level.
;
; color_dbg = 36
; color_inf = 32
; color_war = 33
; color_err = 31
; color_cri = 1;31

; --- Sensitive keyword customisation ---
;
;   sens_kws:         Comma-separated extra keywords added to
;                     the built-in 12 masking words.
;   sens_kws_replace: If true, built-in keywords are replaced
;                     entirely by sens_kws (default: false).
;
; sens_kws =
; sens_kws_replace = false

; =============================================================================
; Per-module settings
;
; Section name format: [dsafelogger:<module_name>]
;   <module_name> corresponds to GetLogger(__name__)
;
; 'level' is required. Other keys are optional.
; 'path' enables independent file output for this module.
;   - Filename only  : output under global log_path
;   - Full/abs path  : output to specified path directly
; Routing keys (routing_mode, max_bytes, etc.) are only valid
;   when 'path' is specified. Ignored otherwise.
; =============================================================================

; [dsafelogger:myapp.db]
; level = DEBUG

; [dsafelogger:myapp.api]
; level = ERROR
; path = /var/log/myapp/api.log
; routing_mode = size
; max_bytes = 10485760
; max_count = 5
; suffix_digits = 2
; backup_count = 10
```

### 8.2. Implementation Architecture Tips
* **Zero external dependencies**: Build only with standard modules including `argparse`.
* **Implementation policy for transparent file tracking**: File change detection takes the approach of periodically polling the target directory using the name `os.stat` and comparing whether the "file corresponding to the latest suffix" has been updated. This enables secure file switching without an external monitoring library.

---

## 9. Basic design and implementation tips for various infrastructure functions

*This chapter not only describes the requirements, but also describes specific implementation policies for detailed designers and implementers when coding.

### 9.1. Fail-Fast: Output destination permission check during initialization
`ConfigureLogger` When executed, it immediately verifies permissions and free disk space by "creating a test file" etc. This prevents the situation where logs cannot be generated several hours after execution, and ensures the robustness of issuing a fatal error (Fail-Fast) early in the startup phase.
If the `log_path` directory does not exist, create it automatically with `os.makedirs(exist_ok=True)` and then verify it.
Similar permission verification is performed for `path` for each module specified in the INI file.
If `manifest_path` is specified, the writability of that directory is also verified at the same time.

### 9.2. Idempotency of initialization, logger acquisition, and stdlib compatibility

* `ConfigureLogger` works safely even if it is called multiple times. **Initialization state is managed in 5 states:**
  * **`unconfigured` (not set)**: Initial state. `ConfigureLogger` performs full initialization.
  * **`auto` (auto-fired)**: State where `GetLogger` was automatically initialized with default arguments when called before `ConfigureLogger`. An explicit call to `ConfigureLogger` from this state **allows reconfiguration** (stopping and cleaning up an existing `Pipeline` with `stop(timeout)` and reinitializing it with explicitly specified arguments).
  * **`explicit` (explicitly set)**: `ConfigureLogger` has been explicitly called from the application code. The second and subsequent `ConfigureLogger` calls from this state will result in **No-Op**.
  * **`configuring` (initializing)**: `ConfigureLogger` is in the middle of execution. Single owner state that holds `_lifecycle_lock` and internal state to prevent double initialization and TOCTOU.
  * **`shutting_down` (terminating)**: `_shutdown()` is in progress. Internal state to prevent termination conflicts. After shutdown is complete, transition to `unconfigured` and reinitialization is allowed.

> **v20 added: Complete state transition table**
>
> | Current | Event | Transition destination |
> |------|---------|---------|
> | `unconfigured` | `ConfigureLogger()` | `configuring` |
> | `unconfigured` | `GetLogger()` Preceding | `configuring` (Automatic firing) |
> | `configuring` | Successful completion | `explicit` or `auto` |
> | `configuring` | Exception occurred | `unconfigured` (rollback) |
> | `configuring` | Same thread reentrant | No-Op return |
> | `auto` | `ConfigureLogger()` | `configuring` (Stop old Pipeline → reinitialize) |
> | `auto` | `_shutdown()` | `shutting_down` |
> | `explicit` | `ConfigureLogger()` | No-Op return |
> | `explicit` | `_shutdown()` | `shutting_down` |
> | `shutting_down` | Done | `unconfigured` |
> | `shutting_down` | `ConfigureLogger()` | No-Op |
>
> Exception handling in `configuring`: `try/finally` prevents `_configure_state` from remaining as `configuring`.
> `_lifecycle_lock` should be `RLock`, re-entrance of the same thread is No-Op return, and another thread re-evaluates the state after waiting for lock acquire.

* `GetLogger` wraps the standard `logging.getLogger` and returns a cached logger (`name=''` is the root logger). If `GetLogger` is executed before `ConfigureLogger` is called, `ConfigureLogger` is automatically fired internally using the default argument (the state transitions to `auto`) to prevent malfunction due to missing initialization.
* **Conflict behavior during 5 states**:
  * Added `ConfigureLogger` in `configuring` **wait until `_lifecycle_lock` is released in another thread, and then re-evaluate the state**. Allows short-circuit returns that are safe only for re-entrancy of the same thread.
  * `GetLogger` in `configuring` also **wait until initialization is completed in another thread**, and only re-entering the same thread is short-circuited by returning the existing logger.
  * `ConfigureLogger` in `shutting_down` does not perform new initialization and prevents state corruption with either No-Op or explicit rejection.
  * `GetLogger` in `shutting_down` may return an existing logger, but must not implicitly fire a new initialization.
  * `register_level()` in `shutting_down` becomes `RuntimeError`.
* **Standard compatibility and testing**: `DSafeLogger` is fully compatible with standard `logging.Logger`, so `pytest`'s `caplog` fixtures and built-in `SMTPHandler` etc. work as is.
* **Free-threaded support principle**: Protect shared states such as `_configure_state`, `_active_pipeline`, `_active_workers`, `_custom_levels` with explicit locks. Do not rely on the existence of the GIL or the internal locks of `list` / `dict` as safety grounds.

### 9.3. Async Mode and Safe Termination
* `is_async=True`, bind D-SafeLogger's dedicated queue hand-off implementation to the root logger instead of the stdlib default `QueueHandler`. This is to safely propagate the producer thread's context information and diagnose information across the queue.
* **Context hand-off**: In async mode, the producer thread side takes a snapshot of `contextualize()` information to the private attribute of `LogRecord`, and the consumer thread side uses that snapshot preferentially. This maintains contextualize semantics consistent with sync mode even in async mode.
* **diagnose lazy path**: Heavy `repr()` expansion for diagnose is executed on the producer thread side only when `diagnose=True` and `exc_info` are present. In normal logs, a lightweight hand-off of copy + context snapshot is performed.
* **`QueueHandler.prepare()` complete override**: D-SafeLogger's queue hand-off is a complete override that does not use stdlib `QueueHandler.prepare()` and does not call `super().prepare()`. This separates the stdlib differences between Python 3.11 / 3.13 / 3.14 from the semantics.
* **Safe termination assurance level**:
  * **Log body flush** has the highest priority. During normal termination, as long as queue drain is successful, the aim is to complete the output of accepted queued log records before starting shutdown.
  * **housekeeping (`hash` / `purge` / `archive`)** is best-effort. A bounded wait is performed, but when timeout occurs, a warning is issued and termination is prioritized.
* **Recommended termination order**: During normal termination, process in the order of (1) state transition and reference saving → (2) queue drain → (3) worker join → (4) handler flush/close. In particular, stop the listener before worker join. This is because the listener may cause a rollover and start a new worker while processing the last queued record.
* **`daemon=True` position**: Since the daemon thread can stop abruptly during shutdown, it should not be used as a basis for safety during normal termination. `daemon=True` is used as a backstop at the time of abnormal termination.
* **timeout and finalization**: Separate queue drain timeout and worker join timeout in shutdown. If `join()` cannot be continued due to late finalization, it will be degraded to warning and termination will take priority.

### 9.4. Variable Dumping and Diagnose implementation policy
* If the environment variable `{prefix}_DIAGNOSE=1` is enabled, a dedicated formatter is applied to the exception log and `f_locals` is expanded and recorded.
* In the case of `structured=True` and `{prefix}_DIAGNOSE=1`, the `f_locals` information is included and output as the `locals` field of the JSON object, not as an expanded string.
* **Protection of sensitive information**: `f_locals` When expanding, the policy is to replace values ​​with sensitive words in variable names with `*** MASKED ***` instead of outputting them as is.
  * **Built-in keywords (12 words)**: `password`, `passwd`, `pass`, `secret`, `token`, `key`, `api_key`, `apikey`, `auth`, `credential`, `private`, `cert`
  * **Customization with `sens_kws`**: You can add your own sensitive keywords using the `sens_kws` parameter of `ConfigureLogger` (or the `sens_kws` key in the INI/dictionary). By default, the specified keyword is **added** to the built-in keywords.
  * **Complete replacement by `sens_kws_replace`**: If `sens_kws_replace=True` is explicitly specified, the built-in keyword will be discarded and only the keyword** specified by `sens_kws` will be masked. This gives the user complete control over problems such as "built-in `key` is too wide and is masked too much".
  * **Matching**: Determine by partial match (case does not matter) for the variable name. For example, `password` matches `user_password`, `PASSWORD_HASH`, `my_password_field`.
* **Suppressing large reprs**: Truncate `repr()` of individual local variables to a fixed length to prevent large objects or excessively redundant data from polluting the log. Even if `repr()` fails, the entire diagnostic log is not destroyed, but the failure is output as a placeholder.
* **Cross-thread safety**: In a free-threaded build, live `f_locals` references to frames in other running threads are unsafe. Therefore, when a hand-off across queues occurs, the traceback and `f_locals` are converted to safe masked repr snapshots on the producer thread side, and live references are not performed on the consumer thread side.
* **Fallback rules**: The formatter (1) uses a queue hand-off diagnostic snapshot if available, (2) allows live references only if `exc_info` is held in the same thread, and (3) otherwise outputs only a standard traceback.
* **[Implementation policy]**: The enable/disable of diagnose is resolved from `{prefix}_DIAGNOSE` during `ConfigureLogger` execution, and consistently propagated to formatter / queue hand-off / diagnostic snapshot. Heavy path is passed only when `exc_info` exists.

### 9.5. Thread/asynchronous context (Contextualize) implementation policy
* **[Implementation policy]**: Use `contextvars.ContextVar[MappingProxyType]` (**FrozenContext**) (changed in v20). Change `ContextVar[dict]` up to v18 to `MappingProxyType` to ensure immutability. Completely independent contexts are guaranteed not only in multithreading but also among `asyncio` tasks. Implement state retention and rewinding using `Token` inside the context manager.
* **No-Copy Performance (new in v20)**: `MappingProxyType` is immutable, so the context snapshot in async mode can be done by **O(1) reference passing** without copying (* `contextualize()` The generation of a new MappingProxyType at the entrance itself is O(n), and the cost is about the same as v18. **Snapshot retrieval and consuming references** only in async mode). Until v18, O(n) copying using `dict.copy()` was required for each queue hand-off, but FrozenContext can reduce hand-off costs. Note that when updating with `contextualize()`, a new `dict` + `MappingProxyType` is generated, so the write path itself remains O(n).
* **Design decision: In sync mode, prefer direct acquisition with Formatter, in async mode, give priority to producer snapshot**: In sync mode, formatter acquires directly from `contextvars` to maintain transparency to third-party standard Logger. On the other hand, in async mode, `contextvars` on the consumer thread side is not trusted, and the `FrozenContext` reference given to `LogRecord` on the producer thread side is given priority. The hand-off cost is O(1) because it is passed by reference rather than a copy.
* **Thread boundary semantics**: Initial context inheritance to new threads created by the user follows the Python specification. The internal thread created by D-SafeLogger itself always starts with an empty `Context`. This prevents context from leaking to internal threads.

### 9.6. Designing console color output and explicit output to stderr
* Specify the default destination of console output as **`sys.stderr`**.
* **[Implementation policy]**: ANSI color codes are assigned to abbreviated display level values. Coloring is resolved using the same local mapping/display proxy route as `DSafeFormatter` and does not directly change `record.levelname`. For Windows, include hacks such as enabling VT100 with `os.system("")` during initialization. The color code specified when registering the custom level is also automatically reflected (see §9.9).
* **Color palette settings**: The built-in 5-level color palette can be changed using `color_{lowercase_abbreviation}` keys in the `[global]` section of the INI file or config_dict (see §5.3). The value specifies the numerical part of the ANSI SGR parameter (e.g. `36`, `1;31`, `38;5;208`). Custom level colors can also be overwritten using the same naming convention. This setting is supported only in the second layer (INI/dictionary), and settings from environment variables and arguments are intentionally not supported. The color palette merge order is: (1) built-in default → (2) color specified by `register_level()` → (3) `color_{abbreviation}` key in INI/dictionary (final override).

### 9.7. Non-destructive handling of LogRecord (Formatter / Handler implementation guidelines)

`logging.LogRecord` **The same instance is shared among all handlers**. If Formatter or Handler directly rewrites attributes such as `record.levelname`, `record.msg`, destructive side effects will be propagated to subsequent handlers.

**[Required implementation pattern]**: Display formatting on the sink side (level abbreviation conversion, ANSI coloring, etc.) should be resolved with local mapping or a display proxy that does not change the shared `LogRecord` and overwrites some fields only at render time. The important thing is not whether it is `copy.copy(record)`, but **not to destroy the shared `LogRecord`**. Note that the process of generating hand-off records at Transport boundaries (e.g. `DSafeQueueHandler.prepare()`) is a separate issue and is outside the scope of this section.

```python
class DisplayRecordProxy:
    def __init__(self, original: logging.LogRecord, overrides: dict[str, object]):
        self.__dict__ = original.__dict__.copy()
        self.__dict__.update(overrides)


class DSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        display_level = self.LEVEL_MAP.get(record.levelname, record.levelname)
        display_record = DisplayRecordProxy(record, {'levelname': display_level})
        # ... add context information, etc. ...
        return super().format(display_record)
```
Similarly, for `ColorStreamHandler.emit()`, create a local proxy with `levelname` for colored display and `emit()` to ensure that embedding the ANSI color code does not affect other handlers such as file handlers.

### 9.8. Level name abbreviation mapping implementation policy

Conversion of D-SafeLogger level name abbreviations (`DEBUG` → `DBG`, `INFO` → `INF`, etc.) is **performed only when the display is resolved**. Both text formatter and console color use the same local mapping/display proxy route. **Do not use** global level name overrides with `logging.addLevelName()`.

**Design Rationale**: `addLevelName()` changes the process-global state of the `logging` module, thus affecting all loggers (including third-party libraries) within the same process. D-SafeLogger's abbreviation conversion should be completed within the scope of its own Formatter, and by avoiding global side effects, test independence and coexistence with third-party libraries are maintained.

**[Implementation policy]**: `LEVEL_MAP` is not a class variable but an **instance variable**, and an integration map of the 5 built-in levels and the custom level is constructed when Formatter is initialized (using `get_all_level_map()` in §9.9). Similarly, `COLOR_MAP` of `ColorStreamHandler` also holds the integrated map as an instance variable. Ensures the same display semantics for each `%` / `{}` / `$` style allowed by `logging.Formatter`.

> * However, `register_level()` calls `logging.addLevelName(value, name)` and registers the custom level numeric → name mapping in the standard `logging` module. This is a registration required for the normal operation of standard APIs such as `logger.log(value, msg)` and `isEnabledFor(value)`, and is different from abbreviation conversion (`INFO` → `INF`).

### 9.9. Custom Log Levels Specification

The `register_level()` function allows you to insert a custom log level at any numerical position in addition to the standard 5 levels (DEBUG/INFO/WARNING/ERROR/CRITICAL). This feature is opt-in (no effect unless `register_level` is called), and if it is not used, it will maintain exactly the same behavior as v14.5.

#### 9.9.1. Design principles
* Maintain consistency in D-SafeLogger three-letter abbreviation format (`DBG`, `INF`, etc.)
* Built-in 5 stages are inviolable and cannot cause breaking changes
* Maintain Zero Dependency (achieved only by standard `logging` mechanism)
* Fully consistent with the 3-tier configuration management pipeline (Environment Variables > INI > Arguments)
* Level **definition** is done only in Python code, and level **application** (filtering settings) can be controlled by a three-layer pipeline.

> **Design decision: Why limit level definitions to code**
>
> If levels are "defined" using INI files or environment variables, all abbreviations, numbers, and colors must be expressed using external settings, which increases the complexity of parsing and validation. Additionally, dynamic generation of convenience methods (`logger.trace()`) can only be performed using the Python runtime.
> The separation of "level definition is code, level application is configuration" is the same design decision as mature frameworks such as SLF4J/Logback.

#### 9.9.2. Enforced call order

```
register_level()    <- any number of times (including zero)
     ↓
ConfigureLogger()   <- exactly once
     ↓
GetLogger()         <- any number of times
```
`register_level()` after `ConfigureLogger()` sends `RuntimeError`. This constraint structurally prevents Formatter/Handler/Validation from causing inconsistency after initialization.

The `shutting_down` condition is also included in this prohibition. Additional registrations during termination processing will be explicitly rejected as they will destabilize the shared state.

#### 9.9.3. Built-in level of protection

All of the following operations are rejected as `ValueError`:
* Override built-in values (10, 20, 30, 40, 50)
* Override built-in names (DEBUG, INFO, WARNING, ERROR, CRITICAL)
* Override built-in abbreviations (DBG, INF, WAR, ERR, CRI)

#### 9.9.4. Alignment with 3-tier configuration management pipeline

Custom level names registered with `register_level()` will be available to all layers of the 3-tier pipeline:

* **Third layer (arguments)**: `ConfigureLogger(default_level='TRACE', ...)` — Custom level names can be used
* **Second layer (INI)**: `level = TRACE` of `default_level = TRACE` or `[dsafelogger:mod]` — valid if registered
* **First layer (environment variables)**: `D_LOG_LEVEL=TRACE` or `D_LOG_MODULES=mymod:TRACE` — valid if registered

If `TRACE` is specified in the INI file or environment variable without calling `register_level('TRACE', ...)` in the code, `ValueError` will be sent by the existing Fail-Fast validation because it is not included in the set of valid level names.

#### 9.9.5. Dynamic generation of convenience methods

When `register_level('TRACE', value=5, ...)` is called, the `logger.trace(msg, *args, **kwargs)` method is dynamically added to the `DSafeLogger` class during the initialization process of `ConfigureLogger`.

* Convenient method names are lowercase level names (`TRACE` → `trace`, `NOTICE` → `notice`)
* If the name is the same as a method that already exists in the `DSafeLogger` class (and parent class `logging.Logger`), addition of the convenience method will be skipped (existing `logger.info()` etc. will not be overwritten). The custom level itself is registered and available in `logger.log(value, msg)`
* Dynamically generated methods cause type errors with `mypy` / `pyright`. As a countermeasure, use `logger.log(VALUE, msg)` (type safety) or add `# type: ignore[attr-defined]` in the document.

#### 9.9.6. Reflection to components

Registered custom levels are automatically reflected in all components:

| Component | Reflected content |
|--------------|---------|
| `DSafeFormatter` / `StructuredFormatter` | Add custom level name → abbreviation mapping to `LEVEL_MAP` (instance variable) |
| `DiagnosticFormatter` / `DiagnosticStructuredFormatter` | Follow `LEVEL_MAP` of parent class |
| `ColorStreamHandler` | Add custom level abbreviation → ANSI color mapping to `COLOR_MAP` (instance variable) |
| `EnvParser` | `{prefix}_LEVEL` / `{prefix}_MODULES` level validation dynamically accepts custom level names |
| `IniLoader` | Validation of `default_level` and `level` same as above |
| `ConfigureLogger` | `default_level` Same as above for argument validation. Dynamic installation of convenience methods |

**[Implementation Policy]**: Custom-level registration information is centrally managed using an internal module (`_levels.py`). Provide an integrated map to each component through query functions such as `get_all_level_map()`, `get_all_color_map()`, `get_valid_level_names()`.

---

## 10. Public API structure

This chapter defines the public API of the single-process version (`dsafelogger`) and multiprocess version (`dsafelogger.mp`).  
In v22c, the multiprocess version is separated into a dedicated namespace while preserving the single-process API contract. This yields the following structure:

- The single-process version can be completed with "one Configure and normal GetLogger" as before.
- The multiprocess version specifies attach contracts via `ctx` and `AttachCurrentProcess()`
- Both share Drop-in Replacement by `logging.setLoggerClass()`

This is the resulting organization.

### 10.1. `dsafelogger.ConfigureLogger` argument definition (single-process version)

```python
def ConfigureLogger(
    default_level: str = 'INFO',
    log_path: str = '.',            # output directory
    pg_name: str = 'Default',       # filename prefix
    env_prefix: str = 'D_LOG',      # prefix for control environment variables
    config_file: str | None = None, # INI configuration file path
    config_dict: dict[str, dict[str, str]] | None = None,  # dictionary config (INI alternative; exclusive with config_file)
    is_async: bool = False,         # async I/O mode
    backup_count: int = 0,          # generation-retention count
    archive_mode: bool = False,     # whether to ZIP-archive instead of delete
    routing_mode: str = 'none',     # routing mode (daily, size, etc.)
    interval: str | int = 10,       # for min_interval / startup_interval
    max_bytes: int = 0,             # threshold for size mode
    max_lines: int = 0,             # threshold for count mode
    max_count: int | None = None,   # cyclic upper limit (None means overflow-error mode)
    suffix_digits: int = 3,         # number of sequence digits
    console_out: bool = True,       # output to stderr
    structured: bool = False,       # emit structured logs (mutually exclusive with fmt, etc.)
    fmt: str | logging.Formatter | None = None, # format string or Formatter instance
    file_fmt: str | logging.Formatter | None = None,    # Formatter for file output only
    console_fmt: str | logging.Formatter | None = None, # Formatter for console output only
    datefmt: str | None = None,     # date/time format
    enable_hash: bool = False,      # generate SHA-256 hash on routing switch
    manifest_path: str | None = None, # output path for manifest file
    sens_kws: Sequence[str] | None = None,  # additional sensitive keywords
    sens_kws_replace: bool = False, # when True, replace built-ins entirely with sens_kws
) -> None:
    """
    Run once at application startup to initialize the D-SafeLogger single-process runtime.

    This function's contract, behavior, and validation are the same as v22a and are not changed
    by the introduction of the multiprocess version. Use `dsafelogger.mp.ConfigureLogger()`
    when multiprocess support is required.
    """
```
**Design judgment**:
- Do not bring the concepts of `worker_model` and `ctx` into the single-process version of `ConfigureLogger()`.
- Prioritize not breaking calls for existing users
- The multiprocess version is separated into a separate namespace and only shares the function name `ConfigureLogger()`.

**`env_prefix` parameter design rationale**: All control environment variables (`_LEVEL`, `_MODULES`, `_CONFIG`, `_CONSOLE`, `_COLOR`, `_DIAGNOSE`, `_HASH`, `_MANIFEST`) are named based on this prefix. Default is `'D_LOG'` (e.g. `D_LOG_LEVEL`, `D_LOG_MODULES`, etc.). By specifying different prefixes, you can separate the environment variable namespaces for multiple D-SafeLogger instances on the same machine. `NO_COLOR` is an industry standard and is not affected by prefixes.

### 10.2. `dsafelogger.GetLogger`

```python
def GetLogger(name: str = '') -> logging.Logger:
    """Return the internal DSafeLogger (Logger-compatible) class. With no argument, get the root logger."""
    pass
```
The single-process version maintains the auto-fire contract up to v22a. In other words, if `GetLogger()` is called in an uninitialized state, implicit initialization with default arguments is allowed.

### 10.3. `dsafelogger.register_level`

**Re-import rules for spawned workers**:
- `spawn` worker bootstrap may re-execute module top-level `register_level()`
- Re-registration of **same definition** (`name` / `value` / `abbreviation` / `color` is an exact match) is allowed as **idempotent no-op**
- **Unmatched re-registration** is considered as registry divergence and is treated as **`RuntimeError`**
- This allows the usual style of placing `register_level()` at module top level to be maintained in the `spawn` environment.

```python
def register_level(
    name: str,
    value: int,
    abbreviation: str,
    color: str = '',
) -> None:
    """
    Register a custom log level with D-SafeLogger.
    Must be called before ConfigureLogger().
    """
```
The contract for this function will not change from v22a. The multiprocess version assumes the same registry, and `ctx` includes the frozen registry and its hash.

### 10.4. `dsafelogger.ReopenLogFiles`

```python
def ReopenLogFiles() -> None:
    """
    Reopen writer-side file sinks after external log rotation.
    In the single-process version, reopen file handles synchronously.
    In the multiprocess version, send a control message to Writer and wait for ACK.
    """
```
**single-process contract**:
- `ValueError` if file sink other than `routing_mode='none'` is active
- `RuntimeError` if writer-side file sink does not exist
- Fix the signature with `ReopenLogFiles() -> None`

### 10.5. `dsafelogger.mp.ConfigureLogger` (multiprocess version)

```python
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
    mp_context: multiprocessing.context.BaseContext | str | None = None,
    ipc_log_timeout: float = 0.5,
    ipc_log_queue_maxsize: int | None = None,
    ipc_client_queue_maxsize: int | None = None,
    writer_flush_batch: int | None = None,
) -> object:
    """
    Entry point for the multiprocess version.
    Start Writer runtime in the calling process and return an opaque, picklable bootstrap object `ctx`.
    `ctx` is used only to attach worker processes to the same Writer.
    """
```
**Design judgment**:
- The multiprocess version exposes `worker_model`, `mp_context`, `ipc_log_timeout`, `ipc_log_queue_maxsize`, `ipc_client_queue_maxsize`, `writer_flush_batch` as developer-selected APIs exclusive to multiprocess.
- `ipc_log_timeout` only applies to **normal log log plane queue**
- `ipc_log_queue_maxsize` / `ipc_client_queue_maxsize` are bootstrap-time only queue capacity contracts and cannot be changed with child side environment variables.
- `writer_flush_batch=1` is the default per-message flush, `2` and above is an explicit opt-in batch flush.
- The internal transport backend is fixed to `multiprocessing.Queue` and is not exposed to the public API.
- `mp_context=None` leaves to Python default context resolution
- If `mp_context` is specified as `str` or `BaseContext`, apply the normalization result consistently to all IPC primitive generation for log/control queue and Pipe reply path.
- The second `dsafelogger.mp.ConfigureLogger()` in the same process is `RuntimeError`
- The generated `ctx` will be verified with pickle round-trip on the spot, and if it fails, it will be Fail-Fast.
- Writer bootstrap ready ACK checks at least `protocol_version` and `registry_hash` with the caller side, and any mismatch is Fail-Fast by `RuntimeError`.
- The multiprocess version of `fmt` / `file_fmt` / `console_fmt` allows the same type faces as the single-process version, but only allows instances of **`logging.Formatter` body and D-SafeLogger built-in Formatter body** to freeze / rebuild at process boundaries.
- Custom formatter instances (including custom subclasses) other than the above allow-list are `TypeError`, and only the picklable spec consisting of `kind + constructor args` is passed on the Writer side.

### 10.6. `dsafelogger.mp.AttachCurrentProcess`

```python
def AttachCurrentProcess(ctx: object) -> None:
    """
    Attach the current process to the Writer runtime referenced by `ctx`.
    After attach succeeds, `logging.getLogger()` / `GetLogger()` in this process are aggregated to Writer.
    """
```
**Contract**:
- Reattach to same `ctx` is a no-op (however, if you need to regenerate process-local thread / transport, do that)
- Reattach to another `ctx` `RuntimeError`
- A child must not reuse its parent's client identity, even if the attach state is inherited by fork. After confirming that it is the same Writer session, establish a child-specific process-local client identity, register it in the Writer active client registry, and then resume logging.
- Apply `logging.setLoggerClass()` to process-local when attach is successful
- Detect `protocol_version` / `registry_hash` mismatch with Fail-Fast when attach is successful

### 10.7. `dsafelogger.mp.GetLogger`

```python
def GetLogger(name: str = '') -> logging.Logger:
    """
    Return DSafeLogger (Logger-compatible) for an attached process.
    """
```
**Contract**:
- Does not auto-fire in multiprocess version
- `RuntimeError` if called in unattached state
- The exception message should be one that makes it easy to detect forgetting to attach (e.g. `Process not attached to Writer`)

### 10.8. `dsafelogger.mp.GetWorkerInitializer`

```python
def GetWorkerInitializer(ctx: object) -> tuple[Callable[..., None], tuple]:
    """
    Return `(init_fn, init_args)` that can be passed directly to
    `initializer` / `initargs` for `multiprocessing.Pool` / `concurrent.futures.ProcessPoolExecutor`.
    """
```
**Return Agreement**:
- `init_fn` is a callbale that performs an attach equivalent to `AttachCurrentProcess(ctx)` when starting the process.
- `init_args` includes `ctx`
- If `ctx` cannot be pickled, fail-fast at `mp.ConfigureLogger()` instead of here.

### 10.8a. `dsafelogger.mp.DetachCurrentProcess`

```python
def DetachCurrentProcess() -> None:
    """
    Detach the current process from Writer runtime and release process-local transport / handler / state.
    """
```
**Contract**:
- When called from an attached process, send `DETACH` control request to Writer and destroy process-local state after successful ACK.
- The main process that called `ConfigureLogger()` also treats its own process client as a detach target when starting shutdown.
- If it is already detached or not attached, it can be treated as a no-op.
- After detaching, `mp.GetLogger()` in that process becomes `RuntimeError` again

## 11. Multi-process compatible (v22i formal design)

### 11.1. Purpose and design attitude

The purpose of the multiprocess formal design in v22i is to safely aggregate logs generated from multiple processes into one Writer runtime, and reuse the file pipeline (routing / hash / manifest / archive / purge / reopen) that the single-process version already has with its semantics intact.

This chapter is not an explanation of how to use it, but rather a definition of the structure and behavior expected of the library. Therefore, in addition to enumerating external APIs, define the following as the body.

- Where does the responsibility belong: Capture / Transport / Sink?
- Role boundaries between client process and Writer runtime
- Why do we need the `ctx` / attach model?
- How to separate the normal log plane and control plane
- Shutdown / reopen / crash semantics
- Conditions for each OS / start method
- Where the single-process and multiprocess versions are continuous and where they diverge

### 11.2. In scope / out of scope

**In scope**:
- multiprocess logging within the same host
- Configuring one Writer runtime and multiple client processes
- Explicit entry point separation with `dsafelogger.mp` namespace
- attach contract according to `worker_model`
- `multiprocessing.Queue` as internal transport
- Separation of log plane for normal logs and control plane for control commands
- Inheritance of the single-process version of routing / hash / manifest / archive / purge / reopen
- Inheritance of Drop-in Replacement to multiprocess version by `logging.setLoggerClass()`

**Out of scope**:
- remote aggregation / network protocol
- Distributed configuration of multiple Writers
- A mode in which the child process directly owns its own file sink
- Public switching of transport backend
- security/auth/encrypted control plane
- IPC with other hosts

### 11.3. Architectural Principles

Even in the multiprocess version, the three-layer separation of **Capture / Transport / Sink** established in v20 is maintained. However, the boundaries of the Transport layer are different between the single-process version and the multiprocess version.

#### 11.3.1. Single-process version
- Capture: `DSafeLogger`, `logging.setLoggerClass()`, `contextualize()`, `diagnose` snapshot
- Transport: `DirectTransport` / `QueueTransport`
- Sink: `FileSink` / `ConsoleSink`, routing, hash, manifest, reopen

#### 11.3.2. Multiprocess version
- **client side Capture**: `DSafeLogger`, `logging.setLoggerClass()`, `contextualize()`, `diagnose` snapshot, route resolved
- **client side Transport**: process-local async queue (if necessary) + hand-off to log plane `multiprocessing.Queue`
- **Writer side Sink / Runtime**: routing, file open/close, hash, manifest, archive, purge, reopen, shutdown, control plane

> **Design principle**: Even in the multiprocess version, **`logging` compatibility is the responsibility of the Capture layer**, and the Capture semantics of `LogRecord` (logger layer evaluation, `propagate` judgment, level judgment, `f_locals` collection) must not be re-executed on the Writer side. The Writer side simply receives `LogEvent` and dispatches it to the sinks according to the route.

### 11.4. Why separate into `dsafelogger.mp`?

The value of the single-process version is its simplicity as it can be completed with a single Configure and a regular GetLogger. The multiprocess version has the responsibility of connecting to the application's process startup model, which includes starting the Writer runtime, attaching it, inter-process protocol, and shutting down synchronization, so the semantics become muddy if they are mixed in the same namespace.

So in v22i,

- `dsafelogger` = single-process version
- `dsafelogger.mp` = multiprocess version

Separate the inlet. This results in

- Single-process version can maintain auto-fire
- In the multiprocess version, forgetting to attach can be made Fail-Fast.
- `worker_model` / `ctx` / `AttachCurrentProcess()` / `DetachCurrentProcess()` can be treated as a multiprocess-only contract

This is an advantage.

### 11.5. client / Writer model

In the multiprocess design of v22h, emphasis is placed on **logical roles** rather than OS-like parent-child relationships, and terms are organized as follows.

| Term | Meaning |
|------|------|
| **client process** | The process that makes the log call. Includes main process and worker process |
| **Writer runtime** | Internal process that owns file sinks and ultimately writes logs from the client |
| **ctx** | An opaque and picklable bootstrap object for client processes to participate in the Writer runtime |
| **log plane** | One-way path that normally carries log `LogEvent` from client → Writer |
| **control plane** | Route for exchanging control messages such as reopen / detach / stop / status |

**Important**: Writer runtime is an implementation element inside the logger, and is not something that developers can explicitly start directly using `multiprocessing.Process` / `subprocess.Popen` etc. The contracts that developers should know about are limited to `ctx`, `AttachCurrentProcess()`, and `DetachCurrentProcess()`.

### 11.6. Multiprocess overview

```text
main process
  ├─ dsafelogger.mp.ConfigureLogger(...)
  │    ├─ resolve three-layer config
  │    ├─ start Writer runtime
  │    ├─ prepare log plane queue
  │    ├─ prepare control plane request queue
  │    ├─ prepare reply endpoint for caller process
  │    └─ generate ctx + validate pickle round-trip
  │
  ├─ mark the current process itself as attached
  └─ pass ctx to worker process

worker process
  ├─ AttachCurrentProcess(ctx)
  │    ├─ validate ctx
  │    ├─ prepare process-local reply endpoint
  │    ├─ send ATTACH control request
  │    ├─ register child-specific client identity in active registry
  │    ├─ update process-local attach state
  │    ├─ apply logging.setLoggerClass()
  │    └─ enable Capture -> Writer hand-off
  └─ normal use through GetLogger(__name__)

Writer runtime
  ├─ maintain active client registry
  ├─ receive LogEvent from log plane
  ├─ select sink group according to route
  ├─ receive ATTACH / DETACH / REOPEN / STOP from control plane
  ├─ file switch / routing / hash / manifest / purge / archive
  ├─ serialize reopen / shutdown
  └─ safely terminate based on active client count and stop requests
```

### 11.7. `ctx` is a bootstrap object, not just a Queue

`ctx` is an opaque object on the public API, and the actual queue or pipe is not visible to the developer. The reason is as follows.

1. To leave room for replacing the internal transport backend in the future
2. What is essential for developers is not the type of queue, but ``how to attach process now''.
3. If you design a queue to be passed to `GetLogger()`, you will not be able to import third-party logs that use `logging.getLogger()`.

The information expected from `ctx` requires the following categories at the basic design level.

- protocol version
-Writer session identity
- see log plane endpoint
- see control plane request endpoint
- `protocol_version` collation information at bootstrap ready / attach
- default queue policy (maxsize/put timeout/overflow policy digest)
-resolved config digest
-custom level registry hash
- runtime metadata required for attach

However, specific field names, internal representation, and pickle implementation details are defined in the detailed design document. What is determined in the basic design is

- `ctx` is **opaque**
- `ctx` is **picklable**
- `ctx` is **bound by the lifetime of Writer runtime**
- `ctx` is **pickle round-trip validated** when `ConfigureLogger()` is generated.
- `ctx` must not contain **non-picklable synchronization primitives** (`Event`, `Lock`, `Condition`, etc.)

These are the five fixed points.

#### Registry hash verification timing
- When Writer bootstrap ready ACK: Check the registry hash sent by the client and the initial registry on the Writer side.
- `AttachCurrentProcess(ctx)` Runtime: Check the registry of the current process and the hash in `ctx`
- Any mismatch is **Fail-Fast with `RuntimeError`**
- Hash algorithm is **SHA-256**

#### bootstrap payload construction principles
- Configuration information included in `ctx` should be **only raw dict/primitive values**
- **Do not include raw instances of `Strategy` / `Formatter`**
- Formatter normalizes to picklable spec consisting of `kind + constructor args`
- Rebuild `Strategy` / `Formatter` from the raw config dict / formatter spec received on the Writer side
- This structurally avoids pickleability issues caused by Formatter custom subclasses and closures.
- Define `ResolvedConfig` as a **pickleable intermediate representation** and redefine it to a form that does not hold `Strategy` instances.

### 11.8. Basic schema for inter-process payload

In v22h, the payload category that crosses the process boundary is fixed at the basic design level as a prerequisite for proceeding to detailed design.

**Common constraints**:
- All payloads that cross process boundaries must be picklable.
- `ctx` / `LogEvent` / `ControlRequest` / `ControlAck` must not contain **non-picklable synchronization primitives**
- ACK is returned via the **control plane return path** instead of the log plane.

#### 11.8.1. `ctx` bootstrap object
As mentioned in the previous section, although it is opaque, it has the following information categories.
- session identifier
- picklable endpoint/routing information
- protocol version
-resolved config digest
-registry hash
- runtime metadata

#### 11.8.2. `LogEvent`
Hand-off payload normally sent to client → Writer in the log plane. Have at least the following information categories:
- route identity (`_ds_route`)
- level / logger name / message
- source location of file / line / function etc.
- process / thread metadata
- `_ds_context`
- `_ds_extra`
- `_ds_diag_frames`
- exception payload

**Convention**: `_ds_context` and `_ds_extra` always exist as keys, and empty values are represented by `{}`.

> **Supplementary note**: This standing convention is necessary to maintain the hasattr-based context snapshot fallback established in v21 at IPC boundaries. Since the distinction based on hasattr does not hold on the Writer side that receives `LogEvent` via pickle, the presence of the key clearly indicates that "the snapshot has been acquired on the Capture side" to ensure that no live context reference occurs on the Writer side.

#### 11.8.3. `ControlRequest`
Request payload sent to client → Writer on control plane. Have at least the following information categories:
- request id
- client id
- command type (attach / detach / reopen / stop / status)
- command-specific payload
- picklable reply endpoint

**v22i fixed**:
- Reply endpoint is reply path by `multiprocessing.Pipe(duplex=False)` of per-request
- The Queue-in-Queue method of sending a Queue as the payload of another Queue is not adopted because it does not hold due to Python's `multiprocessing` constraints.
- Pipe reply endpoint is assumed to be closed by both client and Writer after request/ack is completed

#### 11.8.4. `ControlAck`
In the control plane, Writer → ACK payload returned to the calling client. Have at least the following information categories:
- request id
- success flag
- error category
- error message
- command-specific result payload
- result metadata interpretable on reply path

### 11.9. Separation of log plane and control plane

In v22i, there is usually a clear separation between the log plane and the control plane.

#### 11.9.1. log plane
- One-way client → Writer
- payload is `LogEvent`
- internal transport is **bounded `multiprocessing.Queue`**
- Main path of file writing path

#### 11.9.2. control plane
- handle reopen / attach / detach / stop / status
- has request/ACK
- `ReopenLogFiles()` is a **synchronous API that uses the control plane**
- The control plane usually consists of a log plane and an independent queue/endpoint group.
- ACK is returned through **control plane Pipe reply path**
- The control plane has different QoS for each command type.

> See **§11.16.3** for QoS definitions for each command type.

**Design principles**:
- Do not mix control commands in normal log queues
- Do not mix ACK in log plane
- Do not include non-picklable synchronization objects in the control payload
- Do not send Queue as payload of another Queue
- Pipe send/recv failure is not leaked as raw `BrokenPipeError` / `EOFError`, but is normalized to `RuntimeError` system as control plane failure.

The reason is that ACK timeout, request serialization, QoS, and error transmission have different semantics than normal logs.

### 11.10. Why the attach model is required

In the single-process version, logger acquisition is completed with just `GetLogger()`. However, in the multiprocess version, logs cannot be aggregated unless the worker process knows about the existence of Writer runtime. In particular, `spawn` does not automatically inherit the memory state of the parent process.

Therefore, in v22h,

- Start Writer runtime = `dsafelogger.mp.ConfigureLogger()`
- Current process join = `AttachCurrentProcess(ctx)`
- Logger acquisition = `GetLogger()`

It is clearly separated into three stages.

This separation results in

- `GetLogger()` can maintain Drop-in Replacement semantics
- Can detect forgetting to attach in a fail-fast manner
- Differences between worker models can be localized in the way `ctx` is passed.

### 11.11. Why does `worker_model` appear in the public API?

The internal transport backend can be hidden as a degree of freedom inside the logger. On the other hand, `worker_model` cannot be hidden because it appears directly when the developer uses which API to create a worker process.

Therefore, v22h allows developers to choose

- `worker_model`
- `mp_context`

limited to two.

#### 11.11.1. `worker_model='process'`
- Pass `ctx` as an argument to worker target
- Call `AttachCurrentProcess(ctx)` at the beginning of worker
- Set as default value

#### 11.11.2. `worker_model='pool'`
- Pass the return value of `GetWorkerInitializer(ctx)` to `initializer / initargs`
- The worker body only needs `GetLogger()`

#### 11.11.3. `worker_model='executor'`
- executor here refers to **`concurrent.futures.ProcessPoolExecutor` only**
- Pass `GetWorkerInitializer(ctx)` to `ProcessPoolExecutor(initializer=..., initargs=...)`
- `Future` For base operation
- `ThreadPoolExecutor` is **not applicable** (thread parallelism is the responsibility of the single-process version)

#### 11.11.4. Reason for setting default to `process`
- Can explain the attach contract with minimal assumptions
- Easy to create reference cases for test design
- The order of passing and attaching `ctx` is the most explicit.

### 11.12. `mp_context` and start method

`mp_context` represents the **`multiprocessing` context** that should be shared by Writer runtime and worker processes. As a type,

- `None`
- `'spawn'`, `'fork'`, `'forkserver'`
- `multiprocessing.context.BaseContext`

accept.

**Default resolution**:
- For `mp_context=None`, **Leave to Python default context**
- The library does not perform its own fallback based on OS determination

**Reason**:
- Does not conflict with application-wide multiprocessing policy
- The library does not automatically force `spawn` / `fork`
- Maintain Zero Dependency and API simplicity

> **Note**: Python default multiprocessing context is OS and Python version dependent. If `mp_context=None` is ported as is, the attach behavior and initialization requirements may change depending on the start method. If portability is an issue, explicitly specify `mp_context`. Examples are provided for each OS.

### 11.13. Semantics of `AttachCurrentProcess()`

`AttachCurrentProcess(ctx)` is a process-local operation that currently causes process to join an existing Writer runtime.

#### 11.13.1. Specific responsibilities
- Validation of `ctx`
- Generate process-local reply endpoint
- Sending an ATTACH request
- update process-local attach state
- process-local application of `logging.setLoggerClass()`
- Enable Capture → Writer hand-off
- Attach the required process-local handler / transport

#### 11.13.2. Idempotence
- Reattach to same `ctx` is no-op (if necessary, only regenerate process-local thread / transport)
- In attach inheritance (fork) to the same Writer session, do not reuse the parent's client identity. After confirming the same session, child registers child-specific `client_id` to Writer active registry, and also regenerates the necessary process-local thread / transport.
- Reattach to another `ctx` `RuntimeError`

#### 11.13.3. `fork` Relationship with inheritance
In POSIX `fork`, the attach state of the parent process can be inherited. v22i treats this as a **normal case**. However, since `fork` only copies the main thread, the process-local pump thread etc. used in `is_async=True` need to be regenerated on the child process side. Therefore, if you call `AttachCurrentProcess(ctx)` after forking, check that the same Writer session exists, then re-register with child-only `client_id` and regenerate the necessary process-local thread / transport to make it successful.

However, do not fork while `ConfigureLogger()` / `AttachCurrentProcess()` is running.
**Requirement**: When using `fork`, fork the child after logger initialization and attach are completed on the parent side.

**Boundary condition**: The above fork inheritance child re-registration only holds true while the original Writer session continues. If the parent/Writer side has `STOP` accepted, draining, or terminated, the child process must not automatically revive the same session. In this case, the subsequent `emit()` will be handled through the normal Writer unavailable route (drop + stderr warning), and continued operation is not guaranteed.

### 11.14. Conditions for Drop-in Replacement in the multiprocess version

The core value of D-SafeLogger is stdlib `logging` compatibility through `logging.setLoggerClass()`. The multiprocess version retains this value, but **`logging.setLoggerClass()` must be enabled in each process.**

Therefore,

- `dsafelogger.mp.ConfigureLogger()` applies `logging.setLoggerClass()` to the calling process
- `AttachCurrentProcess(ctx)` is also reapplied to process-local for the attached process

Take this design.

As a result, in the worker process after attach is completed,

- `GetLogger()`
- `logging.getLogger()`
- Third-party library calls internally `logging.getLogger()`

Both are aggregated into Writer.

> **Guarantee**: After a successful `AttachCurrentProcess(ctx)` in a worker process, standard `logging`-based logs generated by that process are aggregated into the Writer via the same Capture semantics as the single-process version.

> **Supplement**: "Apply process-local" here refers to updating the global state (`_loggerClass`) of the `logging` module within each process. Each process has an independent `logging` module state, so `setLoggerClass()` in one process does not directly affect the other. In `fork`, the `logging` state of the parent is inherited by the child, but the process-local thread is not inherited, so `AttachCurrentProcess(ctx)` after forking can succeed by only regenerating the necessary process-local thread / transport without re-ATTACHing the control plane. On the other hand, in `spawn`, the child is newly imported, so the `logging` state returns to its initial value, and reapplication at `AttachCurrentProcess(ctx)` execution becomes a condition for Drop-in Replacement to occur.

### 11.15. Reason for fixing internal transport to `multiprocessing.Queue`

In v22i, the internal transport backend is not exposed to the public API and is fixed to **bounded `multiprocessing.Queue`**.

#### Reason
1. Multiple client processes → 1 Suitable for fan-in of Writer runtime
2. `maxsize` allows you to define backpressure policy
3. You can have a unified hand-off contract independent of differences in `worker_model`
4. Developers can focus on the contracts they need to know about `ctx` / attach

### 11.16. Queue capacity, `ipc_log_timeout`, and backpressure policy

As a reliable operational need, the behavior when the queue is full will be specified in v22h.

#### 11.16.1. log plane queue
- internal log queue is **bounded**
- The default `maxsize` is **10000** (consistent with the implementation in v23g. The implementation value in v22i to v23b was 1000, but it was adjusted to the specification value 10000 in v23g)
- v23h: The implementation of log plane queue uses **`TrackedQueue`** which is derived from `multiprocessing.queues.Queue`. Automatic fallback to `multiprocessing.Value` counter only when `super().qsize()` is **exception probed** and `NotImplementedError` is caught in the constructor. Since the determination does not depend on the OS name (such as macOS), it will work correctly even on future or minor unsupported platforms without additional support.
- `put()` **does not block infinitely**
- multiprocess version `ConfigureLogger()` receives **`ipc_log_queue_maxsize`** as a public argument (added in v23c)
- Default `ipc_log_queue_maxsize` is **10000** (same value as default maxsize above)
- If the environment variable `{prefix}_IPC_LOG_QUEUE_MAXSIZE` is specified, it takes precedence over the `ipc_log_queue_maxsize` argument.
- `ipc_log_queue_maxsize <= 0` specification is **`ValueError`**, `> 100000` **stderr warning**
- v23h: If the value of the environment variable `{prefix}_IPC_LOG_QUEUE_MAXSIZE` cannot be interpreted as an int, **`ValueError`** (fail-fast from warning + ignore)
- multiprocess version `ConfigureLogger()` receives **`ipc_client_queue_maxsize`** as a public argument (added in v23c)
- `ipc_client_queue_maxsize` is the upper limit of process-local async queue (intermediate buffer at `is_async=True`)
- Default `ipc_client_queue_maxsize` is the same as **`ipc_log_queue_maxsize`** (if not specified)
- If the environment variable `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` is specified, it takes precedence over the `ipc_client_queue_maxsize` argument.
- `ipc_client_queue_maxsize <= 0` specification is **`ValueError`**
- v23h: If the value of the environment variable `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` cannot be interpreted as an int, use **`ValueError`**
- multiprocess version `ConfigureLogger()` receives **`ipc_log_timeout`** as a public argument
- `ipc_log_timeout` only applies to the log plane queue for normal logs (`LOG`)
- Default `ipc_log_timeout` is **0.5 seconds**
- If the environment variable `{prefix}_IPC_LOG_TIMEOUT` is specified, it takes precedence over the `ipc_log_timeout` argument.
- `ipc_log_timeout <= 0` or `None` equivalent specification is **`ValueError`**
- v23h: If the value of the environment variable `{prefix}_IPC_LOG_TIMEOUT` cannot be interpreted as float, use **`ValueError`**
- Have **`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0`** as the framework's absolute line of defense
- If the effective value exceeds `MAX_IPC_LOG_TIMEOUT_SECONDS`, issue a stderr warning, **clip to 3.0 seconds** and continue initialization.

> Design decision: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` is an absolute upper limit to prevent the normal log producer path from being blocked for too long. We use 3.0 seconds as an upper bound that is long enough to wait for the queue to recover naturally from temporary saturation, but not so long that it irreversibly freezes the GUI thread or request handler thread.

#### 11.16.2. Overflow policy
- **Drop record** when `ipc_log_timeout` exceeds or `queue.Full`
- When dropping, increment the **client side drop counter**
- Issue **stderr warning** on first drop and subsequent summary timings
- No silent drop
- `ipc_log_timeout` does not apply to control plane commands

#### 11.16.3. control plane queue
- control queue is also bounded
- Reopen / stop / attach / detach / status requests have higher priority than normal logs and are processed independently on the control plane.
- `ipc_log_timeout` does not apply to control plane queue transmission/ACK waiting
- command Fix QoS for each type as follows
  - `ATTACH` / `DETACH` / `STOP`: **drop not possible**
  - `REOPEN` / `STATUS`: **ACK required**
  - `LOG`'s overflow policy does not apply to control plane commands
- `ATTACH` / `DETACH` / `STOP` must not be silently dropped due to queue saturation.
- Failure to send a request is treated as a control plane failure instead of **RuntimeError**, and the calling API converts it into a corresponding exception (`RuntimeError` / `TimeoutError`, etc.)

### 11.17. Confounding specification with `is_async=True`

`is_async=True` is valid even in the multiprocess version. However, the meaning is different from the single-process version.

- `is_async=False`:
  - After capture, hand-off directly from process to log plane queue
- `is_async=True`:
  - After capturing, it is first loaded on the process-local async queue, and then the dedicated worker hand-offs it to the log plane queue.

Therefore, if you use `is_async=True` in the multiprocess version,

- process-local async queue
- multiprocess log queue
- Writer dispatch

This results in **double queuing**.

**Design Implications**:
- The multiprocess version already has process boundary hand-off, so `is_async=False` is usually sufficient.
- Use `is_async=True` only when you want to separate `put()` to the log plane queue from the main thread.

### 11.18. `GetLogger()` and auto-fire

The multiprocess version does not inherit auto-fire from the single-process version.

- Does not auto-fire in multiprocess version
- If `GetLogger()` is called when process is not currently attached to Writer, **`RuntimeError`**
- The exception message should be such that forgetting to attach can be detected early.

**Exception**: If the attach state is inherited by fork inheritance, it will work normally.

### 11.19. Positioning of `GetWorkerInitializer(ctx)`

`GetWorkerInitializer(ctx)` is an auxiliary API that makes it difficult to make mistakes in the attach procedure in `Pool` / `ProcessPoolExecutor`.

```python
ctx = dsafelogger.mp.ConfigureLogger(...)
init_fn, init_args = dsafelogger.mp.GetWorkerInitializer(ctx)
```
- The return value type is **`tuple[Callable[..., None], tuple]`**
- `init_fn` is a callable that performs an attach equivalent to `AttachCurrentProcess(ctx)` when starting the process
- `init_args` includes `ctx`
- If `ctx` cannot be pickled, fail-fast at `ConfigureLogger()` instead of `GetWorkerInitializer()`

This function does not provide an "alternative attach method" but is an aid to putting `AttachCurrentProcess(ctx)` naturally onto each executor API.

### 11.20. `ReopenLogFiles()` is the control plane

`ReopenLogFiles()` in the multiprocess version is not an operation that directly touches the file handle of process unlike the single-process version. The attached client process that called `ReopenLogFiles()` sends a **control request** to the Writer runtime and waits for the corresponding **ACK**.

#### 11.20.1. Basic Agreement
- **Can be called from any attached client process**
- Serialization responsibility for reopen is on the **Writer side**
- Signature is **`ReopenLogFiles() -> None`**

#### 11.20.2. Exception Contract
- Common to single / multiprocess, if any of the writer-side file sinks is `routing_mode != 'none'`, **`ValueError`**
- In multiprocess version, when Writer runtime is absent/attach is invalid **`RuntimeError`**
- ACK timeout in multiprocess version is **`TimeoutError`**

#### 11.20.3. ACK timeout
- Multiprocess version of ACK wait uses internal constant **`CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0`**
- Do not add timeout arguments to public API signatures

> Design judgment: The basis for 5.0 seconds is a value that takes into account the typical postrotate script execution time in logrotate/cron operations (within a few seconds) and the margin for the reopen processing time on the Writer side (usually several tens of ms).
> Leave room for reconsideration when revising the detailed design document or based on actual operational measurements.

#### 11.20.4. Meaning of ACK
- ACK indicates acceptance and processing result of reopen request
- ACK is returned via **control plane Pipe reply path** and does not normally go through the log queue.
- If reopen fails, the Writer returns an ACK with error information, and the client converts it to a corresponding exception.
- ACK payload includes at least request id / success flag / error category / error message
- Pipe endpoint close after request/ack is completed is the responsibility of control plane implementation, and BrokenPipe/EOF is normalized to `RuntimeError` system.

### 11.21. Shutdown synchronization and active client management

Writer maintains an **active client registry** to ensure safe termination from multiple workers.

#### 11.21.1. attach / detach
- `AttachCurrentProcess(ctx)` On success, Writer registers client in active registry
- Even if `AttachCurrentProcess(ctx)` is called by a fork inherited child, register `client_id` exclusively for the child in the active registry.
- Send detach / close control request when client exits
- Writer subtracts the number of active clients after accepting detach
- `ConfigureLogger()` Caller process also counts as 1 client on active registry

#### 11.21.2. Stop judgment
Writer proceeds to shutdown when both of the following conditions are met:
1. Received a stop request from main side
2. The number of active clients must be 0.

The main process's shutdown helper must complete the detachment of its own process client before waiting for the Writer thread to join. Waiting for a join while the main process itself remains in the active client registry is a design violation.

#### Registry consistency during worker crash
- If the worker process terminates without sending `DETACH`, there may be some residue in the Writer's active client registry.
- Set **internal timeout** to wait for number of active clients to be 0 during shutdown
- When timeout is reached, issue **stderr warning** and transition to forced stop
- **Do not cause silent hang**
- Active survivability detection using periodic liveness probes is a future enhancement and is not a mandatory requirement in the basic design.

**Important**: Shutdown judgment is based on **active client registry**, not the number of sentinels. `STOP` is a shutdown trigger and should not be dropped.

#### 11.21.3. shutdown ordering
1. Drain client side async queue
2. Completed sending from client to Writer
3. client sends detach / close
4. Writer side drains log plane queue
5. Writer side closes sink handlers / hash / manifest finalize
6. Writer runtime ends

### 11.22. Writer crash, drop counters, and exit code

#### 11.22.1. client side drop counter
The client side counter is incremented in the following events.
- log queue `put()` timeout / `queue.Full`
- Send failure without attach
- command failure due to control plane transmission failure

#### 11.22.2. Writer side drop / reject counter
The Writer side counter is incremented in the following events.
- protocol failure
- route failure (unknown route increments reject counter + stderr warning; implicit fallback to root is prohibited)
- discard due to sink failure

#### 11.22.3. Output destination and timing
- Visible by at least **stderr warning**
- Output summary during shutdown
- public getter API is not a mandatory requirement for v22h basic design

#### 11.22.4. Writer exit code
- Normal termination is **exit code 0**
- Abnormal termination is **non-0**
- Parent/caller process issues stderr warning if Writer exit code is non-zero

#### 11.22.5. Writer death detection
- The client side detects Writer death by **log plane transmission failure**, **control plane ACK timeout**, or **observation of Writer termination status**
- Specific examples of transmission failure include `BrokenPipeError` / `EOFError` / queue unavailable status
- No recursive logging after death is detected, and subsequent sends will be **drop + stderr warning**
- Increment client side drop counter
- Periodic liveness probe (healthcheck ping) is not a mandatory requirement in the basic design.
- Specific detection implementation will be determined in the detailed design document

### 11.23. `ctx` lifetime and reuse constraints

- `ctx` is **bound by the lifetime of Writer runtime**
- `ctx` is invalid after Writer exits and attach fails
- `ReopenLogFiles()` will not invalidate `ctx`
- The second `dsafelogger.mp.ConfigureLogger()` in the same process is **`RuntimeError`**

### 11.24. Continuity with single-process version

Even though the multiprocess version has a separate entrance, it must not destroy the core value of the single-process version.

What should be inherited:
- 3-tier configuration management pipeline
- `register_level()`
- append-only routing
- structured JSONL
- diagnose/contextualize
- hash / manifest / archive / purge
- `ReopenLogFiles()` single-process contract
- Drop-in Replacement

The only additions in the multiprocess version are **attach / Writer runtime / control plane** for safely establishing these in multiple processes.

### 11.25. Expected module structure

```text
dsafelogger/
  __init__.py                # single-process public API
  mp/__init__.py             # multiprocess public API
  _async.py                 # QueueHandler/QueueListener based async transport pieces
  _transport.py             # single-process transport
  _handler.py               # AppendOnlyFileHandler / required file sink
  _routing.py
  _formatter.py             # client-side console / shared pieces
  _writer_formatter.py      # Writer-side file formatting
  _integrity.py             # hash worker / manifest integrity support
  _purge.py                 # purge / archive workers
  _pipeline.py              # single-process pipeline
  _mp_queue.py              # TrackedQueue for qsize-visible log plane
  _mp_runtime.py            # Writer runtime / active client registry / shutdown
  _mp_attach.py             # AttachCurrentProcess / GetWorkerInitializer
  _mp_protocol.py           # ctx / LogEvent / ControlRequest / ControlAck contract
  _mp_control.py            # control plane helpers / request serialization
```
In v23j, the above is the correct physical file structure. `_capture.py`, `_hash.py`, `_manifest.py` that appear in past design memos are concept division names, and in the current implementation they are integrated into `_integrity.py` / `_handler.py` / `_transport.py` / `_pipeline.py`.

### 11.26. Design essentials

The main points of the v22h multiprocess formal design are as follows.

- Separate entrance to `dsafelogger.mp`
- internal transport is fixed to bounded `multiprocessing.Queue`
- Normally separate log plane and control plane
- Let developers choose only `worker_model` and `mp_context`
- `ctx` is an opaque and picklable bootstrap object
- `AttachCurrentProcess(ctx)` is the key to establishing multiprocess
- Drop-in Replacement is maintained by process-local `logging.setLoggerClass()` reapply
- `ReopenLogFiles()` is a synchronous API that uses the control plane
- Establish safe termination with active client registry and detach / stop synchronization
- overflow / drop / crash does not result in silent failure

### 11.27. Writer flush strategy (v23g)

The per-message flush of the multiprocess version of Writer will be maintained as the default behavior (§12.2 “Weakening the flush contract”). For high-throughput applications, you can opt-in to batch flush with `ConfigureLogger(writer_flush_batch=N)`.

| `writer_flush_batch` | Operation | Intended use |
|---|---|---|
| `1` (default) | per-message flush. No loss when Writer process crashes (does not remain in Python buffer) | High durability requirements |
| `2 – 64` | Flush every N items + idle flush when queue empty. Possibility of loss of up to N-1 items during process crash | Throughput priority |
| `> 64` | Same as above, but with high risk of reduced visibility | Special use |

Can be overridden with environment variable `{prefix}_WRITER_FLUSH_BATCH`. `<= 0` raises `ValueError`; `> 1024` emits a warning. v23h: `ValueError` is also raised if the environment variable value cannot be interpreted as int (changed from warning + ignore to fail-fast). `WriterRuntime.__init__` also rejects `ctx.writer_flush_batch < 1` with `ValueError`, as a safety net for direct `BootstrapContext` construction paths.

#### §12.3 Correspondence with terms

- For `writer_flush_batch=1`: dispatch completed = matches `delivered_per_sink`
- For `writer_flush_batch>1`: Set the batch flush completion point to the arrival point of `delivered_per_sink`. Per-message visibility is not guaranteed once the user opts in

#### Responsibility for Sink flush control by Writer

In the multiprocess route, the Configure layer (`_build_writer_sink_groups` of `mp/__init__.py`) sets `stream_flush_on_emit` of the Sink (`AppendOnlyFileHandler`) to `False`, and the Writer (`_mp_runtime.py`) centrally controls batch / per-message.

This is specified as an exception to §12.1 “Maintaining three-layer separation.” Reason:
- Multiprocess Writer is designed to serialize dispatch to all sinks using a single thread, so centralized control of Writer is more advantageous in guaranteeing ordering than autonomous flush timing for each sink.
- In the single-process version (`is_async=False/True` alone), maintain `stream_flush_on_emit=True` (default) and perform Sink autonomous flush (3-layer separation principle)


## 12. v23 system design policy

### 12.1 Writer invariants

In improving the v23 series, the following assumptions will not be violated.

| Item | Invariant |
|---|---|
| Writer ownership | File sink, routing, hash, manifest, archive, purge, and reopen are centrally owned by Writer |
| Writer drain | Writer log plane is based on single serial drain |
| Writer write | write to file maintains O_APPEND or equivalent append-only operation |
| Writer parallelization | Not included in v23 series improvements |
| file write | Parallel writes to the same log family / route / file are not performed |
| append-only routing | Maintain an append-only routing policy that does not rely on rename/truncate |
| Capture / Transport / Sink | Maintain three-layer separation and avoid mixing responsibilities |
| logging compatible | Maintain Drop-in Replacement with `logging.setLoggerClass()` |
| Zero dependency | Add no external dependencies, use only the Python standard library, and limit APIs available in supported Python versions |
| fail-safe | Avoid silent loss, silent hang, and silent fallback |

See the beginning of §1 for the range of supported Python versions. This range will not be expanded or reduced in the v23 series. If changes are necessary, we will ask the user to decide.

Writer parallelization tends to conflict with the security of owning a single Writer. Even if the necessity resurfaces, it will not be included in the regular improvements for the v23 series, and the user will be asked to make a separate decision.

Note: This invariant condition means that the v23 system does not fundamentally solve the increase in the number of children in p50 and the saturation of parents in throughput observed in the bench results. These are the consequences of the Writer single serial drain design choice. The v23 series focuses on safety, sequence integrity, shutdown/drain contracts, and visualization of caller-side fixed costs and reduction within a safe range. Fundamental improvements to fan-in scalability are related to the Writer ownership model and are therefore a decision outside of v23.

---

### 12.2 Things not to do in v23 series

| Item | Reason |
|---|---|
| Writer Parallelization | Writer ownership, ordering, and manifest have a large impact on consistency |
| Weakening the flush contract | Durability / safety contract changes (Note: Batch flush via opt-in setting `writer_flush_batch>1` is allowed in §11.27. Default behavior remains per-message flush) |
| Changed semantics of append-only routing | Because it relates to product core value |
| Unsafe optimization for bench results only | Because it conflicts with the SafeLogger brand |
| Making destructive changes to the public JSON schema without permission | Because it may affect external collaboration |
| silent drop / silent fallback | against fail-safe policy |

---

### 12.3 Definition of Terms for Shipping Contracts

Terms are divided into the following hierarchies.

| Hierarchy | Terminology |
|---|---|
| Lifecycle states | attempted / accepted / enqueued / delivered_per_sink / delivered |
| Terminal states | rejected / dropped / writer_reject / partial_delivered / unexpected_loss |
| Policy qualifier | overload_shed |

| Term | Definition |
|---|---|
| attempted | Log call passed by user code to logger. Items that are not converted to LogRecord by logger level filter, etc. are not subject to delivery responsibility.
| accepted | Logs that have passed the level determination and client-side logger filter, and for which D-SafeLogger transport has assumed delivery responsibility. Normally, when shutdown is treated as lossless, the accepted log must be delivered.
| enqueued | accepted log is submitted to client-local queue or multiprocess log queue |
| rejected | Logs where delivery responsibility was not accepted due to timeout, closed, invalid state, Writer unavailable, etc. |
| dropped | Logs dropped after accepted or during the local queue stage. dropped should not be silent and should be reflected in counter / warning / summary |
| delivered_per_sink | The state in which the flush contract completion point has been passed for each target sink (Note: If `writer_flush_batch>1` is opt-in in the multiprocess route, the batch flush completion point is considered delivered_per_sink. See §11.27) |
| delivered | State where delivered_per_sink is satisfied for all required sink sets of target log event |
| partial_delivered | Part of the required sink set has been reached, but not all of the required sinks have been reached. It should not be silent, it should be reflected in counter / warning / summary |
| writer_reject | Logs that are determined to be undeliverable by route / sink / writer-side policy after reaching the writer. Record it as a different terminal state from accepted and do not set it to unexpected_loss |
| overload_shed | Policy qualifier to be given to logs explicitly discarded as rejected or dropped according to the bounded queue / timeout policy to avoid OOM, permanent block, and body-involved outage |
| unexpected_loss | Logs that are accepted but are not recorded as dropped / rejected / writer_reject / partial_delivered and are not delivered even after a normal shutdown. Treat this as a design or implementation bug |

The required sink set is defined mainly around file sinks. The console sink is a best-effort / diagnostic sink, and when it fails, it is subject to a warning / counter, but it is separated from the unexpected_loss of file delivery. A module-specific file sink is included in the delivered judgment only if it is included in the required sinks in the route settings.

**Implementation of sink classification (v23h)**

Each handler distinguishes between required and best-effort with the `_ds_required: bool` class attribute.

| handler | `_ds_required` | Meaning |
|---|---|---|
| `AppendOnlyFileHandler` | `True` (default) | required sink. delivered Judgment target |
| `ColorStreamHandler` | `False` | best-effort sink. delivered Failures and failures will be recorded separately |
| `logging.Handler` derived independently by the user | No attribute → treated as `True` | Custom handler is default required. If `_ds_required = False` is specified, it will be treated as best-effort |

`Writer` per-record accounting rules:

- All required handlers succeeded → `delivered` (counter not incremented)
- All required handlers fail → increment `_reject_counter += 1`, `writer_sink_reject` or `writer_policy_reject` (increment both for records where both causes are mixed)
- Only some required handlers succeed → `_writer_partial_delivered += 1` (terminal state is `partial_delivered`, `writer_sink_reject` / `writer_policy_reject` is not incremented)
- best-effort handler failure → `_writer_best_effort_failures += 1` only (no aggregation to `reject_counter`)

**partial_delivered and single handler route**

`partial_delivered` is a terminal state that indicates a "mixed success and failure" state within the required sink set. When there is one required sink set (typical `root` route or module route single file configuration), the concept of partial does not hold, so counter always remains 0. Partial is observed only in configurations where the user has registered multiple required handlers for the same route.

The caller-side omission from `attempted` before entering `accepted` includes at least the following:

| Opportunity for dropout | Treatment |
|---|---|
| Level determination of `logging.Logger.isEnabledFor()` | Not accepted |
| Case where client-side logger filter returns `False` | Not accepted |
| Case where caller side detects route unresolvability | Will not be accepted. Unknown route after reaching Writer is treated separately as writer_reject |
| Case where transport closed / writer unavailable is determined by the caller | Recorded as rejected instead of accepted |

Rejection due to handler-level filter, writer-side filter, route / sink / writer-side policy is treated as `writer_reject` after reaching Writer.

`writer_reject` has at least the following breakdown. Even if it is not possible to completely separate all classifications in the initial implementation, it will be reflected in the counter / warning / STATUS at the granularity possible and will not result in a silent failure.

| Classification | Definition | v23g Implementation Handling |
|---|---|---|
| `writer_route_reject` | route unresolvable or route target sink absent | dedicated counter and stderr warning (rate-limited) |
| `writer_reconstruct_reject` | LogEvent corruption/reconstruct failure (log plane event path) | Dedicated counter and stderr warning (rate-limited, separated from `writer_event_reject` in v23h) |
| `writer_close_marker_reject` | Incorrect CloseMarker (missing client_id / session mismatch / unknown client) | Dedicated counter and stderr warning (rate-limited, separated from `writer_event_reject` in v23h) |
| `writer_sink_reject` | Required sink exists, but emit / write / flush etc. fails (accounted for per record) | Dedicated counter and stderr warning (rate-limited) |
| `writer_policy_reject` | Delivery refused due to required handler filter or Writer side policy (accounted for per record) | Dedicated counter and stderr warning (rate-limited) |
| `writer_format_reject` | Output format generation failed due to inability to formatter / JSON encode | In v23h, it is folded into `writer_sink_reject` as a handler exception. Separate in subsequent editions if necessary |
| `writer_best_effort_failures` | Best-effort sink (console, etc.) emit failure. Do not include it in the terminal state of `writer_reject`. Counter only for visualization | stderr warning (rate-limited) and STATUS publication only. Do not aggregate to `reject_counter` |

Within the handler group of the same route, if some handlers succeed and some fail or result in policy reject, the Writer increments the `partial_delivered` counter. A console sink is a best-effort / diagnostic sink, but failures are subject to visualization and are treated separately from unexpected_loss of a file sink.

---

### 12.4 Overload Policy and Survival-first Policy

In the v23 series, log loss is not treated uniformly as the same problem.

| Classification | Treatment |
|---|---|
| unexpected loss | bug. The accepted log has disappeared for no reason, which should be detected by sequence integrity verification |
| policy-driven rejected | A state where the request is rejected due to timeout / closed / writer unavailable etc. before assuming delivery responsibility. Explicit recording required |
| Policy-driven dropped | State explicitly dropped to protect the main unit due to bounded queue overflow, etc. counter / warning / summary required |

Default policy:

```text
bounded wait -> visible reject/drop -> process survives
```
This is a policy that prioritizes the survival of the main process rather than retaining logs indefinitely and performing OOM, or permanently blocking the main processing and causing a service outage.

In the v23 series, the following are prohibited by default.

| Prohibitions | Reasons |
|---|---|
| unbounded log queue | OOM risk increases indefinitely when Writer stops or output is clogged |
| indefinite producer block | To involve GUI / Web handler / worker loop with log output |
| silent drop | Because the operator cannot detect log loss |
| Confusing overflow with unexpected loss | Due to design bugs and misjudgment of overload policy |

If you want to add strict lossless mode, unbounded queue, or a mode that allows OOM risk, please be sure to ask the user's judgment as it will affect D-SafeLogger's safety policy.

#### 12.4.1 Bounded shutdown contract (v23h)

A silent hang should not occur even if the normal termination path is shutdown. `mp.ConfigureLogger()` calls `_mp_shutdown` → `WriterRuntime.stop()` on `atexit`, but `stop()` follows the bounded contract:

- `stop(timeout)` waits for `log_thread` / `control_thread` to join for up to `timeout` seconds (default `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`)
- If the thread is alive after timeout, **output a visible warning to stderr** (include the stuck thread name and do not make it a silent failure)
- Writer's `log_thread` / `control_thread` starts with **`daemon=True`**, so Python interpreter can exit even if stop() fails to complete drain (process survives principle)
- This causes the shutdown route to satisfy the following invariants:

```text
bounded wait (≤ timeout) -> visible warning (drain incomplete is visible) -> process exits
```
This design prevents the host process from permanently blocking even if an unknown hang occurs in the drain path. Drain integrity is ensured by `stop()`'s serial drain logic, and the daemon flag is only used for fail-safe escapes.

---

## 13. Change history
* **v6**: Abolition of `overflow_mode` and introduction of `max_count` to ensure consistency of behavior rules.
* **v7**: Clarification of file name determination rules by `pg_name`. Added override rules for `diagnose` using environment variables.
* **v8 (v8a/v8b)**:
  * Add suffix definition and `startup_interval`.
  * Reincorporate important design ideas and strengths into the specifications, such as "separation of concerns," "advantages of drop-in replacement," and "self-healing properties of purging."
  * Added intuitive sample examples for environment variables.
* **v9**:
  * The overall chapter structure and list notation have been radically structured into easy-to-read hierarchies (headings) (Chapters 3 and 5).
  * Corrected the misleading `day` expression to `weekday` (`cyclic_weekday`).
  * Restore and clarify override specifications for custom format (`fmt`).
  *Renamed to Basic Design Specification to clarify layer separation.
* **v10**:
  * Unified the misused term "rotation" to "routing".
  * In resource-based mode (`size`, `count`), the behavior when `max_count` is not specified is redefined to "upper limit reached error mode", and the design is refined to control the number of digits with `suffix_digits` as not subject to generation management.
  *Specific technical specifications for the functions mentioned in the architecture overview in Chapter 2 (Async, Diagnostic, Contextualize, etc.) have been added to Chapter 6, improving the comprehensiveness of the basic design.
  * Complete restoration of changelog.
* **v11**:
  * Reflection of review points by Sonnet.
  * Define type/unit consistency (strict distinction) between `min_interval` and `startup_interval` in `interval` parameters.
  * Clarified the design intent of why the "Upper Limit Reached Error Mode" is ignored as it conflicts with generation management.
  * The design basis for the default value (True) of `console_out` is defined in Section 6.5.
  * Specification of standard logging compatible (root logger return) behavior for `GetLogger(name='')`.
* **v12**:
  * Specified the interlocking digit number specifications of `suffix_digits` in resource-based cyclic mode.
  * Added a function to forcibly overwrite environment variables for console output using `D_LOG_CONSOLE`.
  * Added Fail-Fast storage-status pre-validation specifications to `ConfigureLogger`.
  * Significantly expanded typical routing-configuration use cases (TIPS), switching behavior, and asynchronous thread execution sequence documentation.
  * Addition of `archive_mode` accompanying generation management. And, it is clearly stated that it is a "function that saves old log files that are originally destined to be deleted after exceeding backup_count by converting them into a ZIP archive instead of deleting them."
  * Added safety measures for ZIP archive protection (runtime error failsafe) when storage is exhausted.
* **v13 (Safety and robustness integrated version)**:
  * Product name changed, `diagnose` environment variable only (safety design).
  * Structured log support (`structured`), `contextvars` renewal, color output and `sys.stderr` clarification.
  * Optimize the argument structure of `fmt` / `datefmt` and allow direct passing of `logging.Formatter` instances.
  * Added Append-Only background and added design of dedicated CLI utilities (`dsafelogger`).
  * Full complement of implementation policies and architecture tips (Formatter implementation methods, etc.) for implementation engineers.
* **v14 (3-tier configuration management pipeline)**:
  * Introducing a 3-tier configuration management pipeline (Environment Variables > INI > Arguments). Support for loading INI configuration files via `config_file` arguments and `{env_prefix}_CONFIG` environment variables.
  * Change `env_name` parameter to `env_prefix`. Unify all environment variable names based on prefix to ensure namespace consistency.
  * Role separation of environment variables: `{prefix}_LEVEL` is limited to global level only, and module-specific specifications are moved to the newly created `{prefix}_MODULES`.
  * Individual settings for level, output destination, and unique routing are now possible in each module section (`[dsafelogger:mod]`) using the INI file.
  * INI parser is implemented with `configparser(interpolation=None)` (Zero Dependency maintained, `%` escaping unnecessary). If the value is invalid, an exception is thrown in Fail-Fast without silent fallback.
  * Sanctuary protection for `{prefix}_DIAGNOSE`: does not allow any settings from the INI file, and maintains a safe design that only uses environment variables.
  * Valid values ​​of `{prefix}_COLOR` are unified with `{prefix}_CONSOLE` (`"true"/"false"` is also allowed).
* **v14.5 (v14 design review reflected)**:
  * §7.3.2: Extended valid values of `min_interval` from `{5, 10, 15, 20, 30}` to all divisors of 60 `{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}`.
  * §7.5: Added strict file name filtering requirements to prevent false matches due to prefix matches of `pg_name` when identifying files for generation management.
  * §9.2: Introduced direction to extend `ConfigureLogger`'s idempotency management from `bool` to multi-state management. In v18, it has been fixed as 5 states (`unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`).
  * §9.7 (new): Added non-destructive handling of `LogRecord` (local mapping/display proxy) as a mandatory implementation guideline for Formatter/Handler.
  * §9.8 (New): Clarified the policy to perform level name abbreviation mapping only in `LEVEL_MAP.get()` in `format()` to avoid global side effects caused by `addLevelName()`.
* **v15 (Custom Log Level & File Integrity Verification)**:
  * Added `register_level()` functions (§9.9, §10.3). A custom log level can be inserted at any numerical position. Bulk registration of 3-letter abbreviations, ANSI colors, and convenient methods can be completed with a single call before `ConfigureLogger`. Built-in 5 levels (DEBUG/INFO/WARNING/ERROR/CRITICAL) are protected as inviolable. Fully integrated with the 3-tier configuration management pipeline: Registered custom levels can be used in all environment variables, INI, and arguments.
  * Addition of file integrity verification function (§7.6). Automatically generate SHA-256 sidecar file (`.sha256`) when routing with `enable_hash=True`. By specifying `manifest_path`, the hash history of all files is added to the manifest file with timestamps. Sidecar is `sha256sum -c` compatible format. Linked with purge/archive (when deleting, sidecar is also deleted, ZIP is included).
  * Add `{prefix}_HASH` / `{prefix}_MANIFEST` environment variables (§4.7, §4.8). Addition of `enable_hash` / `manifest_path` keys in the INI file (§5.3).
  * Add `enable_hash` / `manifest_path` arguments to `ConfigureLogger` (§10.1).
  * Change `LEVEL_MAP` / `COLOR_MAP` from class variables to instance variables and dynamically build custom-level integration maps (§9.8).
  * Non-destructive change: Both features are opt-in and if not used behave exactly the same as v14.5.
* **v15a (basic design clarification supplement)**:* Specified target Python version as 3.11 or higher.
  * Clarified the rules for sanitizing prohibited characters for `pg_name`, support for Windows absolute paths for `{prefix}_MODULES`, handling of invalid module specs, strict valid values ​​for `{prefix}_DIAGNOSE`, and priorities for automatic color determination as specifications.
  * Added valid INI bool values, handling of unknown keys/unknown sections, and error handling of empty module name sections as specifications.
  * Clarified the relationship between the upper limit error mode of `size` / `count` and `backup_count`, Fail-Fast verification after automatic generation of `log_path`, and worker wait policy at asynchronous termination.
  * Promote `contextualize`'s Formatter side direct acquisition policy, `diagnose`'s sensitive information masking and huge `repr` suppression policy to basic design.
* **v15b (clarification of environment variable expression)**:
  * Settings using environment variables are now expressed as "startup setting override" instead of "dynamic control."
  * Removed references to auto-reflection during operation and clarified that a restart or reinitialization is required for changes to be reflected.
  * The use case description and the explanation of `console_out` have also been revised to avoid misunderstandings as pre-boot settings.
* **v16 (Sensitive keyword customization & dictionary-based configuration)**:
  * Add `sens_kws` / `sens_kws_replace` parameters (§9.4, §10.1). `f_locals` Users can now customize sensitive keywords for masking. By default, it is added to the built-in keywords (12 words) and completely replaced with `sens_kws_replace=True`. In INI/Dictionary, specify `sens_kws` as a comma-separated string.
  * Unified built-in sensitive keywords to 12 words: `password`, `passwd`, `pass`, `secret`, `token`, `key`, `api_key`, `apikey`, `auth`, `credential`, `private`, `cert`
  * Addition of dictionary-based settings (`config_dict`) (§5.7, §10.1). Ability to directly pass `dict[str, dict[str, str]]` to `ConfigureLogger` as an alternative to the INI file. Shares the same section/key structure, validation, and type conversion pipeline as INI files.
  * Exclusive constraints for `config_file` and `config_dict`: `ValueError` if both are specified at the same time. If the `{prefix}_CONFIG` environment variable is set, override both.
  * Expanded the second layer of the 3-layer pipeline to "INI file or dictionary" (§3.1, §3.2, §3.4).
  * Added `dsafelogger init` subcommand (§8.1). CLI command that prints an INI configuration template to standard output. All setting keys are commented out and instructions on how to use them are provided with inline comments. Supports all v16 keys including `sens_kws` / `sens_kws_replace`.
  * Removed §11 (Backward Compatibility Impact).
* **v17 (Console color palette settings)**:
  * Added `color_{abbreviation}` keys to the `[global]` section of the INI file and config_dict (§5.2, §5.3). The console color of the built-in 5 levels (DBG/INF/WAR/ERR/CRI) can be changed according to the terminal environment and visual characteristics. Custom level colors registered with `register_level()` can also be overwritten using the same naming convention.
  * Supported only in the second layer (INI/dictionary) of the 3-layer pipeline. Environment variables (1st layer) and arguments (3rd layer) are intentionally not supported, and `ConfigureLogger` signature is not changed (§9.6).
  * `color_` prefix keys are recognized on a pattern basis and are not included in the fixed key list (`VALID_GLOBAL_KEYS`). Unknown abbreviations and invalid values ​​are output as a warning to stderr and skipped (not Fail-Fast).
  * Color palette merging order: built-in default → color specified by `register_level()` → `color_{abbreviation}` key in INI/dictionary.
  * `dsafelogger init` Added color palette section to template (§8.1.2).
  * Non-destructive change: `color_` Exactly the same behavior as v16 unless the key is specified.
* **v18 (free-threaded Python support)**:
  * Added free-threaded build of Python 3.13+ to the design target in addition to normal build.
  * Expand `_configure_state` to 5 states (`unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`) and specify a policy that does not depend on GIL for the safety of shared state.
  * Change `_active_workers` from `list` to `set`, and add prevention of duplicate registration and exception avoidance in case of termination conflict using `discard()`.
  * Reviewed the queue hand-off in async mode and updated the design to create a snapshot of `contextualize` information on the producer thread side. `QueueHandler.prepare()` is assumed to be completely overridden by D-SafeLogger.
  * Added cross-thread safety for diagnose. When crossing queues, convert traceback / `f_locals` into a safe snapshot on the producer thread side, and do not refer to live `f_locals` on the consumer thread side.
  * Added policy that internal thread always starts with empty `Context`. Initial context inheritance to user thread follows the Python specification.
  * Separate the safe shutdown guarantee level into "log flush" and "housekeeping best-effort" and specify the order of queue drain → worker join → handler close.
  * Enhanced the integrity area, added serialization of same family maintenance, serialization of manifest addition, and atomic write policy of `.sha256` sidecar.
* **v20 (Capture/Transport/Sink 3-layer/Vendor-Agnostic/FrozenContext)**:
  * Restructured the internal architecture into a three-layer model of Capture / Transport / Sink (§11.2). No changes to public API (`ConfigureLogger` / `GetLogger` / `register_level`).
  * `Transport` Introduction of abstractions (`DirectTransport` / `QueueTransport`). Structurally prepared for future addition of `IPCTransport` (multi-process support) (§11.3, §11.4).
  * Clarification of Vendor-Agnostic principles (§2, §11.5). Institutionalize the exclusion of vendor-specific logic (OpenTelemetry, etc.) from core modules as a design guard. CI assumes AST/import-based static inspection.
  * Add `file_fmt` / `console_fmt` parameters (§6.3, §10.1). You can now specify separate Formatters for files and consoles. Added corresponding keys to `[global]` section of INI / config_dict (§5.3).
  * Changed context management from `contextvars.ContextVar[dict]` to `contextvars.ContextVar[MappingProxyType]` (FrozenContext) (§9.5). Optimized queue hand-off in async mode to O(1) reference passing, eliminating the need for `dict.copy()` on the producer side.
  * Extend exclusive constraints for `structured=True` and `file_fmt` / `console_fmt`. `structured=True` Both file and console output in JSON Lines format. Note that if a `logging.Formatter` instance is passed to `file_fmt` / `console_fmt`, the `datefmt` argument is ignored (the datefmt of the instance takes precedence) (§6.4).
  * Fixed the async mode + `contextualize()` hand-off bug by integrating it into the FrozenContext contract.
  * Non-destructive change: Completely the same behavior as v18 unless `file_fmt` / `console_fmt` is specified. FrozenContext also has no effect on external APIs.
  * Completely resolved the async mode + contextualize context loss bug in v17.x (structure resolution in v18, snapshot cost improvement in v19).
* **v20 (Reflects review points and strengthens robustness)**:
  * Fully defined state machine error recovery. Rollback to `unconfigured` due to exception in `configuring`, and transition to `unconfigured` after completion of `shutting_down`. Added complete state transition table.
  * Eliminate deadlock risk by adding `_registry_lock`. `_get_manifest_lock()` / `_get_family_lock()` use dedicated `_registry_lock` instead of `_lifecycle_lock`.
  * Protect `register_level()` with `_lifecycle_lock` to prevent `_custom_levels` corruption due to parallel calls in free-threaded Python.
  * Separate `LogEvent` / `_event.py` from the main body of v20 and change to install it at the same time as IPCTransport (Step 10 / v19.1). v20 maintains `LogRecord` + `_ds_*` attribute contract.
  * Added detailed design of PipelineBuilder / Pipeline / ResolvedConfig (detailed design document §3.4).
  * Add vendor-neutral extra field extraction (`_merge_extra_fields`) to `StructuredFormatter`. Added `taskName` for Python 3.12+ to `_STD_RECORD_KEYS`.
  * `RoutingStrategy` Add `advance()` to ABC with default no-op (LSP compliant).
  * Fixed CQS violation in `CountStrategy.should_switch()`. Move count update to `advance()`.
  * `_switch_file()` rollback improvements. Preliminarily tries opening the new file, and rolls back to the old file if it fails.
  * Support for `DirectTransport.stop()` partial failure. Try processing all handlers with individual try/except.
  * Eliminate SHA-256 double counting. Add `hash_value` argument to `write_sidecar()` / `append_manifest()`.
  * Fixed double call of `datetime.now()` of `append_manifest()` (only called once).
  * Limited O(1) representation of FrozenContext. "No-Copy Context" → "No-Copy Snapshot". `contextualize()` Specify O(n) cost of ingress.
  * Specify shallow immutability constraints for `MappingProxyType` (pass only immutable values ​​to kwargs).
  * `configuring` Confirm state behavior: `RLock` Reentrant is No-Op return, another thread waits for lock.
  * Clarified that environment variables are not supported for `sens_kws` / `sens_kws_replace` / `file_fmt` / `console_fmt`.
  * Prevent INI/config_dict modification of `env_prefix`.
  * cyclic mode + Force overwriting `enable_hash=True` to `enable_hash=False`.
  * Clarified that the console output when using `structured=True` is also JSON.
  * Clarified `datefmt` priority rules when passing Formatter instances.
  * Limit Vendor-Agnostic CI grep to import statements.
* **v21 (concurrency safety/non-destructive level display/module transport integration)**:
  * Execute the entire `_do_configure()` of `ConfigureLogger` under `_lifecycle_lock` to safely prevent reading of intermediate state during initialization in parallel. `GetLogger` waits for lock structure when `'configuring'` state is detected.
  * `AppendOnlyFileHandler`'s independent `self._lock` has been abolished and the lock API has been unified to the parent class `logging.Handler`.
  * Introduced a non-destructive method that does not directly change `record.levelname` in `DSafeFormatter.format()` and `ColorStreamHandler.emit()`. The TLS proxy reuse pattern (`threading.local()` + `_DisplayRecordProxy`) eliminates GC pressure while ensuring the same semantics for all `%` / `{}` / `$` styles.
  * `is_async=True` semantics consistently applied to module-specific paths. `Pipeline` holds `module_transports: dict[str, Transport]`, and all Transports are structurally stopped at `stop()`.
  * Change snapshot context fallback to `hasattr` base branch. If the `_ds_context` attribute exists, even an empty `MappingProxyType({})` is treated as an authoritative snapshot.
* **v22 (formal design for multi-process support)**:
  * Revised Section 11 from "Design Preparation" to Full Multi-Process Compatible Formal Design.
  * Added `ipc_mode` / `ipc_queue` / `ipc_queue_size` parameters to `ConfigureLogger`. `get_ipc_queue()` Added public function.
  * Newly added `IPCSendTransport` (child process → parent process dispatch) and `IPCListener` (parent process side mp.Queue consumer + route-based dispatch).
  * `LogEvent` Define TypedDict (`total=True`) as an internal serialization contract across process boundaries. `_ds_route` (sink group identity) added to specify dispatch destination.
  * `_ds_context` / `_ds_extra` always have a key, empty is represented by `{}`. The receiver side handles the key existence as an authoritative snapshot and maintains v21 `hasattr` semantics over IPC.
  * Define reserved area and collision rules for `_ds_extra` (standard LogRecord attribute / `_ds_*` prefix protection).
  * Clarify the role-specific `ConfigureLogger()` behavior of `ipc_mode='child'` (omit file sink / console sink / writer-side validation / worker initialization).
  * Console output of the child side normal log is not performed in the first version of v22. Only internal warnings are output directly with `print(..., file=sys.stderr)` (logger recursion prohibited).
  * The parent side `IPCListener` does not re-execute any Capture layer semantics (level judgment, logger hierarchy evaluation, `propagate` judgment). Direct dispatch only based on `_ds_route`.
  * Define parent-child bootstrap invariants (custom level match, routing topology match). If there is a mismatch, skip + warning (safe principle) instead of erroneous delivery.
  * Added a shutdown race countermeasure to send sentinel after ensuring child transmission has finished.
  * Add `{prefix}_IPC_MODE` environment variable. Added new file `_ipc.py`.
* **v22a (external log rotation coexistence)**:
  * Officially supports external log rotation coexistence limited to `routing_mode='none'` and added public API `ReopenLogFiles()`.
  * Added a contract to make `ReopenLogFiles()` fail-fast if any of the writer-side file sinks are `routing_mode != 'none'` or `ipc_mode='child'` (in v22h, `routing_mode != 'none'` is organized into `ValueError` through single / multiprocess).
  * Include the writer-side sink group (root / module separate path / listener side file sink) including `ipc_mode='parent'` / `is_async=True` in the re-open target.
  * Signal handler is not automatically registered, and `SIGHUP` coordination and calls from `logrotate postrotate` are the responsibility of the application/operation layer.
  * The Linux operation tutorial explains the combination of `logrotate` and `ReopenLogFiles()`, and clearly states that mixing with library built-in routing is prohibited.
  * IPC has clarified `queue.put()` repr retransmission when internal pickle fails, `is_async` constraint when `ipc_mode='child'`, and `multiprocessing` current context inheritance policy.
  * `get_ipc_queue()` is bound to the lifespan of the current Pipeline, and it has been clarified that reacquisition and child side redistribution are required after reinitialization or shutdown.


* **v22c (dsafelogger.mp redesign)**:
  * Reorganized the multiprocess formal design into the `dsafelogger.mp` namespace and separated the multiprocess version into a separate entrance while fully maintaining the single-process version API contract.
  * Define multiprocess public API as `ConfigureLogger()` / `AttachCurrentProcess()` / `DetachCurrentProcess()` / `GetWorkerInitializer()` / `GetLogger()` / `ReopenLogFiles()`.
  * `worker_model` is a developer-selected API, and the internal transport backend is hidden as `multiprocessing.Queue` fixed.
  * Added client / Writer model, bootstrap object `ctx`, attach contract, process-local reapplying of Drop-in Replacement, `ReopenLogFiles()` as control plane, basic semantics of safe shutdown.

* **v22d (control plane / QoS / active client registry fixed)**:
  * The log plane for normal logs and the control plane for control commands are clearly separated and mixing is prohibited.
  * Fixed the expected structure category of `ControlRequest` / `ControlAck`, `ctx`, `LogEvent`.
  * Clarified the QoS rules that `ATTACH` / `DETACH` / `STOP` cannot be dropped, and `REOPEN` / `STATUS` must be ACKed.
  * Fixed shutdown judgment to be based on active client registry instead of sentinel count.
* **v22e (Addition of constraints for IPC payload / executor definition)**:
  * Process boundary Payload is limited to picklable, and non-picklable synchronization objects such as `Event` / `Lock` / `Condition` are prohibited from being included in the payload.
  * Clarified that ACK should be returned via the control plane return route instead of the log plane.
  * `worker_model="executor"` only refers to `concurrent.futures.ProcessPoolExecutor`, and `ThreadPoolExecutor` is not covered.

* **v22f (registry / payload construction principles / Writer crash reinforcement)**:
  * Added `register_level()` idempotent re-registration rules for registry hash matching timing and spawn re-import.
  * Added construction principle to not include Strategy/Formatter instances in bootstrap payload, only raw dict/primitive values.
  * Added the reason for `_ds_context` / `_ds_extra` standing convention, process-local semantics of `logging.setLoggerClass()`, active client registry consistency during worker crash, and enhancements to Writer death detection.

* **v22g (`ipc_log_timeout` and log plane backpressure control)**:
  * Added `ipc_log_timeout` to the multiprocess version `ConfigureLogger()`, and published the specification of the transmission waiting time for the log plane queue of the normal log (`LOG`).
  * Added override by environment variable `{prefix}_IPC_LOG_TIMEOUT` and specified that it should be evaluated in the first layer of the three-layer configuration management pipeline.
  * Added hard limit for `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0`, excessive value continues with stderr warning + clip, `<=0` becomes Fail-Fast (`ValueError`).
  * Clarified that `ipc_log_timeout` does not apply to the control plane and is a parameter exclusively for backpressure control of `LOG`.
* **v22h (Writer death detection/ACK basis/version history maintenance)**:
  * Added Writer death detection to §11.22 and specified the drop + stderr warning policy when observing transmission failure, ACK timeout, and Writer termination.
  * Added the design basis of `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0`.
  * Organized the version number and order of the change history, and created individual entries for major changes in v22d / v22e / v22f.
  * Make `AttachCurrentProcess()` 3-phase, process-local rehydrate when inheriting fork, and clearly state the invariant conditions to not acquire `_mp_lifecycle_lock` and `_lifecycle_lock` at the same time.
  * Added CQS alignment of `CountStrategy` by `RoutingStrategy.on_emit()`, `OverflowError` retransmission in `AppendOnlyFileHandler.emit()`, defense-in-depth of `reopen()`.
  * Make Writer log/control thread non-daemon, control queue drain after `STOP`, make process-local async queue bound, and add drop contract for `emit()` after `stop()`.
  * Materialize the multiprocess Formatter freeze/rebuild contract based on allow-list and `FormatterSpec`, and clarify the boundaries where fork inheritance child does not replay session after Writer stops.
* **v22i (Reflection of post-implementation findings)**:
  * Changed the control plane reply channel from Queue-based to Pipe(`multiprocessing.Connection`)-based to solve the Queue-in-Queue failure problem.
  * Deprecated `reply_queue_factory_token` and changed ACK wait to `poll() + recv()`.
  * Moved the stop judgment of `_control_loop` from the beginning of the loop to the timeout side, and fixed the subsequent `ATTACH` rejection contract after `STOP` in an implementable form.
  * Added an implementation note to consider the acquisition route difference of `logging.Formatter.defaults` and `ValueError` for closed queue as a Python 3.14 difference.
  * Added `DetachCurrentProcess()` to the multiprocess public API to align the public contract with active client registry base shutdown.
  * Fork inheritance child does not reuse the parent's client identity, but updates the contract to re-register child-specific `client_id` on the same Writer session.
  * Clarified that when `mp_context` is specified, it must be applied consistently to all IPC primitives of log/control queue and Pipe reply path, `protocol_version` / `registry_hash` must be checked in bootstrap ready ACK, and root fallback of unknown route is prohibited.
* **v23 (v23 system design policy, delivery contract terminology, Overload Policy baseline)**:
  * Copied v22i basic design specifications as v23 and added v23 series design policy as §12. No behavior change.
  * §12.1 Writer invariants: Writer ownership / single serial drain / append-only write / Writer Clarification of parallelization exclusion.
  * §12.2 Things not to do in v23 series: Writer parallelization, flush contract weakening, silent drop, etc. are explicitly prohibited.
  * §12.3 Delivery contract terminology definitions: attempted / accepted / enqueued / rejected / dropped / delivered_per_sink / delivered / partial_delivered / writer_reject / overload_shed / unexpected_loss defined.
  * §12.4 Overload Policy and Survival-first Policy: Clarify the distinction between unexpected loss / policy-driven rejected / policy-driven dropped, bound wait policy, and prohibition of unbounded queue / indefinite block / silent drop.
  * Recorded inventory of differences from implementation in private planning notes.
* **v23a (benchmark sequence integrity verification)**:
  * Introduced `run_id` / `repeat_index` / `worker_index` / `sequence_no` to the multiprocess benchmark and upgraded it from line count matching to missing / duplicate / JSON parse failure / route mismatch verification.
  * Separated benchmark profile into `integrity_profile` / `performance_profile` / `overload_profile`.
* **v23b (CloseMarker drain contract)**:
  * Removed `multiprocessing.Queue.empty()` dependence from Writer shutdown/drain completion determination, and updated design to determine drain upon reaching CloseMarker for each client.
  * Added handling of `close_marker_failed` and degraded shutdown.
* **v23c (queue setting/counter by cause)**:
  * Added `ipc_log_queue_maxsize` / `ipc_client_queue_maxsize` to the multiprocess version `ConfigureLogger()` and added the corresponding environment variables to §4 / §11.16.
  * The client side drop counter was separated by cause, and the Writer side route/event reject counter was published to `STATUS`.
* **v23d (diagnostic benchmark)**:
  * Added a benchmark that measures latency stages such as capture / serialize / queue put / writer dispatch using a diagnostic wrapper without changing the production code.
* **v23e (Writer flush optimization)**:
  * Introduced writer-side centralized flush control and reduced dispatch fixed costs by `stream_flush_on_emit=False` of file handler and Writer batch / idle flush.
* **v23f (`_ds_route` structured JSON leak fix)**:
  * Exclude multiprocess internal routing field `_ds_route` from structured JSON public output. The degree of damage was recorded as minor and user approved.
* **v23g (audit support, flush opt-in, specification consistency)**:
  * Changed v23e's batch flush to an explicit opt-in of `writer_flush_batch>1` and reverted to a per-message flush contract with `writer_flush_batch=1` as the default.
  * Adjusted `_LOG_QUEUE_MAXSIZE` to 10000 to make the implementation consistent with the default value in §11.16.1.
  * Updated the policy to visualize drain deadline residual queue, flush error, handler sink/policy reject, and partial delivery with counter / warning / STATUS.
* **v23h (compatible with v23g audit results)**:
  * Revised §12.3 to clarify required/best-effort sink classification, per-record accounting rules, and single handler failure of `partial_delivered`.
  * `writer_event_reject` was separated into `writer_reconstruct_reject` (LogEvent reconstruct path) and `writer_close_marker_reject` (CloseMarker validation path), and `writer_best_effort_failures` was newly created.
  * Clarified that the rate-limited stderr rules (first time + every 100 items) on the Writer side will be uniformly applied to all reject counters including `writer_sink_reject` / `writer_policy_reject`.
  * Added to §11.16.1 / Detailed Design §15a.5 that log_queue is generated by `TrackedQueue` derived from `multiprocessing.queues.Queue`, and native `qsize()` compatibility is determined by an exception probe at init, and automatic fallback to `multiprocessing.Value` counter is performed on unsupported platforms (no OS determination).
  * The invalid value of env var `{prefix}_IPC_LOG_TIMEOUT` / `_IPC_LOG_QUEUE_MAXSIZE` / `_IPC_CLIENT_QUEUE_MAXSIZE` / `_WRITER_FLUSH_BATCH` was changed from warning + ignore to `ValueError` immediate raise (fail-fast).
  * Changed `ctx.writer_flush_batch < 1` to `ValueError` in `WriterRuntime.__init__`, and added a safety net when directly building `BootstrapContext`.
  * `_log_loop`'s idle / shutdown flush was replaced with `_batch_flush_enabled = (writer_flush_batch > 1)`'s flag control to avoid dead branches in per-message mode.
  * §12.4.1 Bounded shutdown contract newly established. `_log_thread` / `_control_thread` of `WriterRuntime` was changed to **`daemon=True`**, and if the thread is alive after the join timeout of `stop()`, a stderr visible warning including the stuck thread name is issued. Drain integrity is still guaranteed by `stop()`'s serial drain logic, and the daemon flag is used as a fail-safe escape based on the §12.4 "process survives" principle (**The decision to make it a non-daemon made in v22h was rescinded in v23h**. The rationale for the decision at that time, "safety of normal termination does not depend on daemon threads", was before the atexit call to `runtime.stop()` was established; with the current structure, `stop()` is responsible for draining, so `daemon=True` is acceptable.)
  * Added CloseMarker `session_id` / expected client verification, `mp.ConfigureLogger()` signature/environment variable list/benchmark profile queue prerequisite synchronization as v23g audit synchronization.
* **v23j (Supports review before OSS release/Public operation fixed)**:
  * No change in implementation behavior. Publish v23h's Writer-owned sinks, CloseMarker drain, classified delivery-state counters, and bounded shutdown contracts as official specifications.
  * Regarding the preview recommendation of OSS Review, `dsafelogger.mp` recorded the decision to treat it as an official API rather than a preview / experimental. The reason is that the value of MP has been redefined not as raw throughput but as the observability of writer-owned sinks and delivery state during abnormalities, and the corresponding resilience profile and standard quality gate have been developed.
  * OpenTelemetry / structlog coexistence tests are not skipped by optional dependencies, but are now executed as part of the full test suite that includes the `dev` dependency group. `optional_integration` marker is limited to diagnostic selection markers.
  * Eliminated dependence on `multiprocessing.Queue.empty()` from `tests/`, and clarified disclosure conditions to use the same context for `mp.ConfigureLogger(..., mp_context=ctx)` and worker process creation in spawn E2E.
  * Fixed benchmark public model. The artifact for each execution is `benchmarks/results/<session>/`, the public representative session is `benchmarks/summary/manifest.json`, the generated summary is `benchmarks/summary/*.md`, and the public analysis is manually edited `BENCHMARK.md`.
  * Confirmed the package release version to `0.2.0` and recorded the policy to match `pyproject.toml` and `dsafelogger.__version__`.

### v23j Publication Sync Addendum

Pre-publication synchronization includes coverage regeneration, API docs regeneration, addition of formal MP/external rotation for examples, enhancement of GitHub workflow gate, and readiness check of `docs/design/` publication design document. These are public artifact synchronizations that do not change the runtime behavior and keep the release version as `0.2.0`.

### v23j Type Validation CI Addendum

For the 0.2.2 pre-publication quality gate, CI adds type validation for the `py.typed` distribution. Source typing is checked with `mypy src` and `pyright src`, user-perspective smoke typing is checked with `pyright tests/typing_smoke`, and packaged typing is checked from the installed built wheel with `pyright --verifytypes dsafelogger --ignoreexternal` at a 100% completeness threshold. The verifytypes step uses `uv run --no-sync` so the wheel install is not replaced by the editable install before verification. The smoke-test directory is named `tests/typing_smoke/`, not `tests/typing/`, to avoid shadowing the standard-library `typing` module in spawn workers. These additions change only the public quality gate, not runtime behavior; the release-version bump is deferred until release readiness is confirmed.
