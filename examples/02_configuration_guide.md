# Configuration Guide

The hardest part of logging isn't writing `logger.info()` — it's managing
configuration across environments. You need DEBUG locally, INFO in staging,
WARNING in production. You need different rotation policies for different modules.
And you need ops teams to override settings without code changes.

D-SafeLogger solves this with a **3-layer configuration pipeline** where every
layer can be mixed, matched, and overridden independently.

## The Problem

Consider a real scenario. You have one codebase deployed to three environments:

| Environment | Level | Rotation | Extras |
|-------------|-------|----------|--------|
| Development | DEBUG | None | Color console |
| Staging | INFO | Daily, 14 days | JSON output |
| Production | WARNING | Daily, 30 days | JSON + integrity hashing |

Hardcoding any of this means redeploying to change a log level at 3 AM during an
incident. Environment-only config means you can't commit a baseline. D-SafeLogger
lets you set **developer defaults in code**, commit a **deployment baseline in INI**,
and **override anything at runtime with environment variables**.

## The 3-Layer Pipeline

Higher layers always win:

```
┌──────────────────────────┐
│  Layer 1: Env Vars       │  ← Always wins (ops/emergency override)
│  D_LOG_LEVEL=WARNING     │
├──────────────────────────┤
│  Layer 2: INI File       │  ← Deployment baseline (committed or mounted)
│  [global]                │
│  default_level = INFO    │
├──────────────────────────┤
│  Layer 3: Code Args      │  ← Developer defaults (fallback)
│  default_level='DEBUG'   │
└──────────────────────────┘
  Result: WARNING (Layer 1 wins)
```

If Layer 1 sets a value, it takes precedence. If not, Layer 2 is checked. If that
is also absent, Layer 3 applies. This means:

- **Developers** set sensible defaults in code (Layer 3).
- **DevOps** commits an INI file per environment (Layer 2).
- **On-call engineers** override at runtime without a redeploy (Layer 1).

## Layer 3: Code Defaults

The simplest starting point — pass parameters directly:

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs',
    pg_name='MyApp',
    default_level='DEBUG',
    routing_mode='daily',
    backup_count=7,
)

logger = GetLogger(__name__)
logger.info('Running with code defaults')
```

These values are your **fallback**. They apply unless overridden by Layer 2 or 1.

## Layer 2: INI Configuration

Generate a template INI file:

```bash
dsafelogger init > logging.ini
```

Here's a realistic production configuration:

```ini
[global]
default_level = INFO
log_path = /var/log/myapp
pg_name = OrderService
routing_mode = daily
backup_count = 30
structured = true
enable_hash = true

[dsafelogger:myapp.db]
level = DEBUG
path = db_queries.log

[dsafelogger:myapp.api]
level = WARNING

[dsafelogger:myapp.tasks]
level = INFO
path = background_tasks.log
```

**`[global]`** sets the baseline for all loggers. **Per-module sections**
(`[dsafelogger:module.name]`) override specific settings:

| Section | Effect |
|---------|--------|
| `[dsafelogger:myapp.db]` | DB queries logged at DEBUG to a dedicated `db_queries.log` |
| `[dsafelogger:myapp.api]` | API module only logs WARNING and above |
| `[dsafelogger:myapp.tasks]` | Background tasks go to their own file at INFO |

> This is a compact configuration-layer example of normal production isolation.
> For a focused guide to per-module log control across production, development,
> and incident response, see `24_per_module_log_control.md`.

Load it in one line:

```python
ConfigureLogger(config_file='logging.ini')
```

Or combine with code defaults (INI values override code):

```python
ConfigureLogger(
    config_file='logging.ini',
    log_path='./logs',        # overridden by INI's /var/log/myapp
    default_level='DEBUG',    # overridden by INI's INFO
)
```

## Layer 1: Environment Variables

Environment variables **always win**. The default prefix is `D_LOG`.

### Common Variables

| Variable | Effect | Example |
|----------|--------|---------|
| `D_LOG_LEVEL` | Override global log level | `D_LOG_LEVEL=WARNING` |
| `D_LOG_CONFIG` | Point to a different INI file | `D_LOG_CONFIG=/etc/myapp/logging.ini` |
| `D_LOG_DIAGNOSE` | Enable D-SafeLogger diagnostic mode | `D_LOG_DIAGNOSE=1` |
| `D_LOG_CONSOLE` | Enable/disable console output | `D_LOG_CONSOLE=0` |
| `D_LOG_COLOR` | Enable/disable colored output | `D_LOG_COLOR=0` |
| `D_LOG_HASH` | Enable/disable integrity hashing | `D_LOG_HASH=1` |
| `D_LOG_MODULES` | Per-module level and optional path overrides | `D_LOG_MODULES=myapp.db:TRACE,myapp.api:ERROR` |

### Docker / Kubernetes Example

```bash
# Emergency: bump a single service to DEBUG without redeploying
docker run \
  -e D_LOG_LEVEL=DEBUG \
  -e D_LOG_DIAGNOSE=1 \
  myapp:latest

# Kubernetes: set in your deployment manifest
env:
  - name: D_LOG_LEVEL
    value: "WARNING"
  - name: D_LOG_MODULES
    value: "myapp.payment:DEBUG,myapp.api:ERROR"
```

### Per-Module Env Override

`D_LOG_MODULES` lets you surgically adjust one module without touching others:

```bash
# Only the DB module gets TRACE; everything else stays at the INI/code default
export D_LOG_MODULES="myapp.db:TRACE"
python -m myapp
```

`D_LOG_MODULES` can also redirect a selected module to a dedicated file:

```bash
export D_LOG_MODULES="myapp.checkout:TRACE:/var/log/myapp/incidents/checkout_trace.log"
python -m myapp
```

<!-- example-test: tests/examples/test_24_per_module_log_control.py -->

For the full guide to per-module destinations, path resolution, Windows drive-letter paths, and incident files, see `24_per_module_log_control.md`.

## Dict Configuration

For programmatic setups (test harnesses, dynamic config), pass a dict:

```python
config = {
    'global': {
        'default_level': 'INFO',
        'log_path': './logs',
        'pg_name': 'TestRunner',
        'structured': True,
    },
    'dsafelogger:tests.integration': {
        'level': 'DEBUG',
        'path': 'integration.log',
    },
}

ConfigureLogger(config_dict=config)
```

This is equivalent to the INI format but lives entirely in Python.

## Complete Runnable Example

Save the INI as `config_demo.ini`:

```ini
[global]
default_level = INFO
log_path = ./logs
pg_name = ConfigDemo
routing_mode = daily

[dsafelogger:myapp.db]
level = DEBUG
path = db_debug.log
```

Save the script as `config_demo.py`:

```python
"""config_demo.py — Demonstrates the 3-layer configuration pipeline."""

from dsafelogger import ConfigureLogger, GetLogger

# Layer 3 (code) provides fallback defaults.
# Layer 2 (INI) overrides them.
# Layer 1 (env vars) overrides everything.
ConfigureLogger(
    config_file='config_demo.ini',
    default_level='DEBUG',   # INI overrides this to INFO
)

app_logger = GetLogger('myapp.app')
db_logger = GetLogger('myapp.db')

app_logger.debug('This will NOT appear — global level is INFO from INI')
app_logger.info('Application initialized')
db_logger.debug('SELECT * FROM users WHERE active = 1')
db_logger.info('Query returned 42 rows')

print('\n--- Env override example ---')
print('Run with D_LOG_LEVEL=WARNING python config_demo.py to suppress INFO logs.')
app_logger.warning('Connection pool running low')

print('\n✓ Check ./logs/ for output files.')
```

Run it:

```bash
python config_demo.py

# Override from the command line before ConfigureLogger() runs:
D_LOG_LEVEL=DEBUG python config_demo.py
```

`ConfigureLogger()` is intentionally idempotent after the first explicit call. To
change settings, provide env vars before process startup or start a new process
with different configuration.

## What's Next

- **[Per-module Log Control](24_per_module_log_control.md)** — Control module-specific destinations and levels for production, development, and incident response.
- **[Web API Logging](06_web_api_logging.md)** — See the configuration pipeline in
  action with per-module routing, JSON output, and request context.
- **[Long-Running Service](07_long_running_service.md)** — Deep dive into all 9
  rotation strategies, backup retention, and ZIP archival.
- **[Compliance & Audit Logging](08_compliance_audit.md)** — Tamper-proof your log
  files with SHA-256 hashing and structured JSON for auditors.
