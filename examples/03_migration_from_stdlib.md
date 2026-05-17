# Migrating from stdlib `logging`

If you already have a Python application using `logging.basicConfig()`,
`TimedRotatingFileHandler`, or `dictConfig()`, migrating to D-SafeLogger is
straightforward. Your existing `logger.info()` calls don't change. Your third-party
libraries keep logging normally. Only the setup code changes — typically from
10-20 lines to 1-3 lines.

## Prerequisites

- **Python 3.11+**
- Install D-SafeLogger:

```bash
pip install d-safelogger
```

## Migration Pattern 1: basicConfig → ConfigureLogger

**Before** (stdlib):
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
```

**After** (D-SafeLogger):
```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path='.', pg_name='app')
logger = GetLogger(__name__)
```

**What you gain**: Source location in every line (`[file:line:func]`), millisecond
timestamps, automatic directory creation, ANSI console colors, and consistent
formatting across all loggers.

## Migration Pattern 2: TimedRotatingFileHandler → routing_mode

**Before** (stdlib):
```python
import logging
from logging.handlers import TimedRotatingFileHandler
import os

os.makedirs('./logs', exist_ok=True)
handler = TimedRotatingFileHandler(
    './logs/app.log', when='midnight', backupCount=30,
)
handler.suffix = '%Y%m%d'
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger('myapp')
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

**After** (D-SafeLogger):
```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs',
    pg_name='app',
    routing_mode='daily',
    backup_count=30,
)
logger = GetLogger('myapp')
```

**What you gain**: Append-only file strategy (no rename at midnight, no locking
issues on Windows), SHA-256 hashing option, automatic purge/archive of old files.

## Migration Pattern 3: dictConfig → config_dict

**Before** (typical Django/Flask setup):
```python
import logging.config

LOGGING = {
    'version': 1,
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/app.log',
            'maxBytes': 10_000_000,
            'backupCount': 5,
            'formatter': 'standard',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'INFO',
    },
}
logging.config.dictConfig(LOGGING)
```

**After** (D-SafeLogger):
```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs',
    pg_name='app',
    max_bytes=10_000_000,
    backup_count=5,
)
logger = GetLogger(__name__)
```

The entire dict structure — handlers, formatters, root config — collapses into
a single function call.

## What About Library Loggers?

This is where D-SafeLogger really shines. During `ConfigureLogger()`, it calls
`logging.setLoggerClass(DSafeLogger)`, which means **subsequent**
`logging.getLogger()` call — including those inside third-party libraries —
returns a DSafeLogger instance.

```python
from dsafelogger import ConfigureLogger

ConfigureLogger(log_path='./logs', pg_name='MyWebApp')

# SQLAlchemy, Flask, httpx, boto3 — all use logging.getLogger() internally.
# They now automatically get D-SafeLogger formatting, rotation, and hashing.
from sqlalchemy import create_engine
engine = create_engine('sqlite:///mydb.db', echo=True)
# SQLAlchemy's debug logs go through D-SafeLogger with source location,
# millisecond timestamps, and your configured rotation policy.
```

Output in `logs/MyWebApp.log`:
```
2026-04-03 09:15:22.738 [INF][engine.py:3242:connect] BEGIN (implicit)
2026-04-03 09:15:22.740 [INF][engine.py:3248:connect] SELECT 1
```

No library code changes needed. No adapter wrappers. No handler injection.

## Gradual Migration

You don't have to migrate everything at once:

1. **Install**: `pip install d-safelogger`
2. **Replace setup code**: Swap your `basicConfig()` / `dictConfig()` / handler
   chain with a single `ConfigureLogger()` call
3. **Keep using `logging.getLogger` after setup**: calls made after
   `ConfigureLogger()` return DSafeLogger instances thanks to `setLoggerClass`.
   Logger objects created before setup should be reacquired if they need
   D-SafeLogger-specific methods.
4. **Gradually adopt `GetLogger`**: Where you want `contextualize()` support,
   switch from `logging.getLogger(name)` to `GetLogger(name)`

```python
import logging
from dsafelogger import ConfigureLogger, GetLogger

# Step 2: Replace setup
ConfigureLogger(log_path='./logs', pg_name='MyApp')

# Step 3: Existing code — still works
old_logger = logging.getLogger('mymodule')
old_logger.info('This works — old_logger is a DSafeLogger instance')

# Step 4: New code — gains contextualize()
new_logger = GetLogger('mymodule.new')
with new_logger.contextualize(request_id='abc-123'):
    new_logger.info('Enhanced with context')
```

## What You Can Remove

After migrating, you can safely delete:

| Remove | Why |
|---|---|
| `os.makedirs()` for log directories | D-SafeLogger creates directories automatically |
| `from logging.handlers import ...` | Not needed — rotation is built-in |
| `logging.Formatter(...)` setup | Built-in defaults with source location |
| `handler.setFormatter()` / `logger.addHandler()` | One function call does it all |
| `logrotate` / cron rotation config | Usually replaced by built-in routing; if ops must keep external rotation, use `routing_mode='none'` plus `ReopenLogFiles()` |
| `logging.config.dictConfig(...)` | Replaced by `ConfigureLogger()` |

## Complete Before/After Example

A realistic medium-sized application migration.

**Before** — `app_stdlib.py`:
```python
"""app_stdlib.py — Typical stdlib logging setup."""

import logging
import logging.handlers
import os

# Create log directory
os.makedirs('./logs', exist_ok=True)

# File handler with rotation
file_handler = logging.handlers.TimedRotatingFileHandler(
    './logs/webapp.log', when='midnight', backupCount=30,
)
file_handler.suffix = '%Y%m%d'
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
))

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
))

# Root logger
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(file_handler)
root.addHandler(console_handler)

logger = logging.getLogger('webapp')

def handle_request(path: str):
    logger.info(f'Handling {path}')
    # ... business logic ...
    logger.info(f'Completed {path}')

if __name__ == '__main__':
    logger.info('Server starting')
    handle_request('/api/users')
    handle_request('/api/orders')
    logger.info('Server stopped')
```

**After** — `app_migrated.py`:
```python
"""app_migrated.py — Same application with D-SafeLogger."""

from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs',
    pg_name='webapp',
    routing_mode='daily',
    backup_count=30,
)

logger = GetLogger('webapp')

def handle_request(path: str):
    with logger.contextualize(path=path):
        logger.info('Handling request')
        # ... business logic ...
        logger.info('Request completed')

if __name__ == '__main__':
    logger.info('Server starting')
    handle_request('/api/users')
    handle_request('/api/orders')
    logger.info('Server stopped')
```

### Output Comparison

stdlib (`logs/webapp.log`):
```
2026-04-03 12:34:56,789 [INFO] webapp: Server starting
2026-04-03 12:34:56,790 [INFO] webapp: Handling /api/users
2026-04-03 12:34:56,791 [INFO] webapp: Completed /api/users
2026-04-03 12:34:56,792 [INFO] webapp: Server stopped
```

D-SafeLogger (`logs/webapp_20260403.log`):
```
2026-04-03 12:34:56.789 [INF][app_migrated.py:18:<module>] Server starting
2026-04-03 12:34:56.790 [INF][app_migrated.py:13:handle_request] Handling request [path:/api/users]
2026-04-03 12:34:56.791 [INF][app_migrated.py:15:handle_request] Request completed [path:/api/users]
2026-04-03 12:34:56.792 [INF][app_migrated.py:13:handle_request] Handling request [path:/api/orders]
2026-04-03 12:34:56.793 [INF][app_migrated.py:15:handle_request] Request completed [path:/api/orders]
2026-04-03 12:34:56.794 [INF][app_migrated.py:21:<module>] Server stopped
```

The migrated version gives you: exact source location, millisecond precision,
structured context fields, daily rotation without file renames, and 21 fewer
lines of setup code.

## How to Run

```bash
pip install d-safelogger

# Run the stdlib version
python app_stdlib.py

# Run the migrated version
python app_migrated.py

# Compare the outputs
cat logs/webapp.log
cat logs/webapp_20260403.log
```
