# Quick Start

You're building a Python app and need application logging that can start small and grow into structured, file-backed, operationally controlled logging. D-SafeLogger keeps the first setup small while preserving the standard `logging` calling model.

## Install

```bash
pip install d-safelogger
```

## Your First Log

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path='./logs', pg_name='MyApp')
logger = GetLogger(__name__)
logger.info('Application started')
```

Output:

```
2026-04-03 09:15:22.738 [INF][app.py:4:<module>] Application started
```

Let's break that down:

| Component | Meaning |
|-----------|---------|
| `2026-04-03 09:15:22.738` | Timestamp with **millisecond** precision — essential for correlating events across services |
| `[INF]` | Built-in level abbreviation: `DBG` DEBUG, `INF` INFO, `WAR` WARNING, `ERR` ERROR, `CRI` CRITICAL (`TRC` and other custom levels are available after `register_level()`) |
| `[app.py:4:<module>]` | **Source location** — file name, line number, and function name so you can jump straight to the code |
| `Application started` | Your message |

No configuration guessing. Every log line tells you *exactly* where it came from.

## Add Features Incrementally

The best part: you never rewrite your setup. Choose the configuration you want at
process startup and keep the rest of your application code unchanged.

```python
# Start simple: console + file logging
ConfigureLogger(log_path='./logs', pg_name='MyApp')

# Or add daily routing with one more parameter
ConfigureLogger(log_path='./logs', pg_name='MyApp', routing_mode='daily')

# Or add routing + JSON output + integrity hashing
ConfigureLogger(
    log_path='./logs', pg_name='MyApp',
    routing_mode='daily', structured=True, enable_hash=True,
)
```

Each block is an alternative startup configuration. After an explicit
`ConfigureLogger()` call, later explicit calls in the same process are no-ops; set
the final options before your first logger is created.

## GetLogger Auto-Fire

For quick scripts, you don't even need `ConfigureLogger`:

```python
from dsafelogger import GetLogger

logger = GetLogger(__name__)
logger.info('This just works')
```

`GetLogger` detects that `ConfigureLogger` hasn't been called and auto-initializes
with sensible defaults (console output, INFO level). Perfect for one-off scripts
and notebooks.

## Understanding the Output Format

```
┌─── Date ────┐ ┌── Time ──────┐ ┌Lvl┐┌── Source Location ──┐ ┌── Message ──┐
2026-04-03      09:15:22.738     [INF] [app.py:4:<module>]     Application started
```

When you add context (covered in [Web API Logging](06_web_api_logging.md)),
key-value pairs appear at the end:

```
2026-04-03 09:15:22.738 [INF][api.py:12:handle] Order received [request_id:abc-123 user:alice]
```

## Complete Runnable Example

Save this as `quickstart.py` and run it:

```python
"""quickstart.py — D-SafeLogger in 30 seconds."""

from dsafelogger import ConfigureLogger, GetLogger

# Initialize: logs go to ./logs/ with daily rotation
ConfigureLogger(log_path='./logs', pg_name='QuickStart', routing_mode='daily')

logger = GetLogger(__name__)

# All five built-in log levels
logger.debug('Loaded 142 configuration entries from cache')
logger.info('Server started on port 8080')
logger.warning('TLS certificate expires in 7 days')
logger.error('Failed to connect to payment gateway')
logger.critical('Failed over to read-only mode')

print('\n✓ Check the ./logs/ directory for your log files.')
```

Expected output (console):

```
2026-04-03 09:15:22.738 [DBG][quickstart.py:11:<module>] Loaded 142 configuration entries from cache
2026-04-03 09:15:22.739 [INF][quickstart.py:12:<module>] Server started on port 8080
2026-04-03 09:15:22.739 [WAR][quickstart.py:13:<module>] TLS certificate expires in 7 days
2026-04-03 09:15:22.740 [ERR][quickstart.py:14:<module>] Failed to connect to payment gateway
2026-04-03 09:15:22.740 [CRI][quickstart.py:15:<module>] Failed over to read-only mode
```

The same entries are written to a date-stamped file inside `./logs/`.

## What's Next

- **[Configuration Guide](02_configuration_guide.md)** — Master the 3-layer config
  pipeline: code → INI → environment variables. Control log levels, rotation, and
  routing per module without touching code.
- **[Web API Logging](06_web_api_logging.md)** — Attach request IDs, user context,
  and route metadata to every log line automatically using `contextualize()`.
