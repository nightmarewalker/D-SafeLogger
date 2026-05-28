# Per-module Log Control

D-SafeLogger can control log levels and file destinations per module.

This is useful when one module is operationally more important, much noisier
than the rest of the application, or temporarily under investigation.

Per-module log control is not only a debugging convenience. It can be part of
the normal production logging layout.

The same `logging.getLogger(__name__)` call sites can support different
operational layouts:

- in normal production, isolate high-volume or high-value modules into dedicated files;
- during development, lower one module's level without increasing verbosity application-wide;
- during incident response, redirect a suspect module to a dedicated incident file for a bounded investigation.

## Why Control Logs per Module?

A single application often contains modules with very different logging needs.

Database access can be noisy. Payment, authentication, and audit code can be
operationally important. Background workers can produce long-running task logs
that do not belong in the main request-flow log.

Per-module log control lets you keep the main log readable while giving selected
modules their own level and destination policy.

## Normal production: isolate selected modules

In production, not every module has to share the same log file or the same log level.

Some modules are operationally more important. Some modules are simply much
noisier than the rest of the application. Some background workers produce long
task traces that should not be mixed into the main request or lifecycle log.

```ini
[global]
default_level = INFO
log_path = /var/log/myapp
pg_name = OrderService
routing_mode = daily
backup_count = 30
structured = true
enable_hash = true

# High-volume module:
# Keep query noise out of the main application log.
[dsafelogger:myapp.db]
level = WARNING
path = db_warnings.log

# High-value module:
# Keep payment anomalies easy to inspect and retain separately.
[dsafelogger:myapp.payment]
level = WARNING
path = payment_alerts.log

# Background worker:
# Keep long-running task events away from request lifecycle logs.
[dsafelogger:myapp.tasks]
level = INFO
path = worker_tasks.log
```

This is a normal production layout, not an emergency-only setting. The main log
stays focused on application lifecycle and request flow, while noisy,
high-value, or long-running modules get their own operational files.

## Development: lower one module's level

During development, setting the whole application to `DEBUG` can make the log
harder to read. If the investigation target is known, lower only that module's
level and send it to a dedicated file.

```ini
[global]
default_level = INFO
log_path = ./logs
pg_name = OrderServiceDev
routing_mode = daily
structured = false

[dsafelogger:myapp.parser]
level = DEBUG
path = parser_debug.log

[dsafelogger:myapp.db]
level = DEBUG
path = db_debug.log
```

This keeps unrelated application logs at `INFO` while giving the target modules
their own debug files.

## Incident response: redirect a suspect module

For a bounded production investigation, avoid turning the entire application to
`TRACE` unless you really need to. Redirect only the suspect module to a
dedicated incident file.

```bash
export D_LOG_MODULES="myapp.checkout:TRACE:/var/log/myapp/incidents/checkout_trace.log"
python -m myapp
```

Windows PowerShell:

```powershell
$env:D_LOG_MODULES = "myapp.checkout:TRACE:C:\Logs\MyApp\incidents\checkout_trace.log"
python -m myapp
```

This keeps the main application log readable while collecting high-detail
evidence for the suspect module.

Use module-specific incident paths for bounded investigation windows. Remove
the override after the investigation. Keeping `TRACE`-level output enabled for
high-volume modules can produce large files and may expose more operational
detail than normal production logging.

For diagnostic-mode local variable expansion combined with module-specific
incident files, see `09_debugging_production.md`.

## Choosing the Right Mode

The same mechanism can serve different operational goals depending on the situation.

| Situation | Goal | Typical setting |
|---|---|---|
| Normal production | Isolate high-volume, high-value, or long-running modules | `myapp.payment:WARNING -> payment_alerts.log` |
| Development | Focus on one module without application-wide DEBUG | `myapp.parser:DEBUG -> parser_debug.log` |
| Incident response | Redirect one suspect module for a bounded investigation | `myapp.checkout:TRACE -> incidents/checkout_trace.log` |

## Module-specific Path Resolution

A module-specific `path` may be either a simple file name or an explicit path.

- If `path` is a simple file name, it is placed under the global `log_path`.
- If `path` contains a path separator, it is treated as an explicit path.

```ini
[global]
default_level = INFO
log_path = ./logs
pg_name = MyApp

# Stored under ./logs/db_queries.log
[dsafelogger:myapp.db]
level = DEBUG
path = db_queries.log

# Explicit POSIX path
[dsafelogger:myapp.audit]
level = INFO
path = /var/log/myapp/audit.log
```

Windows explicit paths are also supported in normal INI configuration:

```ini
[dsafelogger:myapp.audit]
level = INFO
path = C:\Logs\MyApp\audit.log
```

A path such as `logs/db_queries.log` contains a path separator, so it is treated
as an explicit relative path rather than a simple file name under `global.log_path`.

## Fail-fast Validation for Module-specific Paths

During `ConfigureLogger()`, the parent directory of each module-specific `path`
is validated with the same fail-fast writable-directory check as the global log
directory.

If the directory does not exist, D-SafeLogger attempts to create it. If directory
creation or test writing fails, configuration fails immediately.

## Environment Override with D_LOG_MODULES

`D_LOG_MODULES` lets you surgically adjust selected modules without touching others.

```bash
# Only the DB module gets TRACE; everything else stays at the INI/code default.
export D_LOG_MODULES="myapp.db:TRACE"
python -m myapp
```

It can also redirect a selected module to a dedicated file:

```bash
# Lower one suspect module's level and write it to an incident file.
export D_LOG_MODULES="myapp.checkout:TRACE:/var/log/myapp/incidents/checkout_trace.log"
python -m myapp
```

On Windows, the parser uses a maximum of two `:` splits, so drive-letter paths
can be used as the third field:

```powershell
$env:D_LOG_MODULES = "myapp.checkout:TRACE:C:\Logs\MyApp\incidents\checkout_trace.log"
python -m myapp
```

## Related Examples

- `02_configuration_guide.md` explains the general configuration layers and precedence rules.
- `09_debugging_production.md` expands the incident-response mode with diagnostic local-variable expansion.
- `04_stdlib_ecosystem_coexistence.md` includes a concrete production-isolation example when coexisting with stdlib logging.
- `06_web_api_logging.md` includes concrete production-isolation examples for database and payment modules in a web API.
