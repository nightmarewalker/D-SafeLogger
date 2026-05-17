# Long-Running Service Logging

A service that runs for months generates terabytes of logs. Without rotation, you'll fill your disk,
crash production, and spend your weekend restoring from backups. D-SafeLogger's 9 routing strategies
handle this automatically — with append-only writes, automatic purge, and optional ZIP archival.

---

## The Problem

With `routing_mode='none'` (the default), everything goes into a single file. After a month of a
busy service you end up with:

```
logs/
└── MyService.log  ← 47 GB, impossible to open, disk 98% full
```

You can't `grep` it, you can't open it in an editor, and your monitoring starts paging you at 3 AM.

---

## Choosing a Strategy

| Your situation | Recommended strategy | Why |
|---|---|---|
| Standard web service | `daily` | One file per day, easy to grep by date |
| High-volume API (>1 GB/day) | `hourly` or `min_interval` | Smaller, more manageable files |
| Batch job that runs periodically | `startup_interval` | One file per run |
| Must control exact file sizes | `size` | Switch at N bytes |
| Fixed storage budget (7 days) | `cyclic_weekday` | Routes back to the same weekday files on a weekly cycle |

All 9 modes: `none`, `daily`, `hourly`, `min_interval`, `startup_interval`, `size`, `count`,
`cyclic_weekday`, `cyclic_month`.

---

## Daily Rotation with Purge

The most common pattern — one file per day, keep 30 days, compress old logs:

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs', pg_name='OrderService',
    routing_mode='daily',
    backup_count=30,     # keep 30 days
    archive_mode=True,   # ZIP old files instead of deleting
)

logger = GetLogger('orders')
logger.info('Service started')
```

### What the directory looks like

**After one week:**

```
logs/
├── OrderService_20260401.log
├── OrderService_20260402.log
├── OrderService_20260403.log
├── OrderService_20260404.log
├── OrderService_20260405.log
├── OrderService_20260406.log
└── OrderService_20260407.log          ← current
```

**After 30 days** (archive_mode=True kicks in):

```
logs/
├── OrderService_20260401.log.zip      ← compressed
├── OrderService_20260402.log.zip
├── ...
├── OrderService_20260429.log
├── OrderService_20260430.log
└── OrderService_20260501.log          ← current
```

**After 60 days** (purge removes files older than 30 periods):

```
logs/
├── OrderService_20260502.log.zip      ← oldest kept
├── ...
├── OrderService_20260530.log
├── OrderService_20260531.log
└── OrderService_20260601.log          ← current
```

Old ZIPs beyond `backup_count` are deleted automatically.

---

## Size-Based Rotation with Cycling

When you need tight control over file sizes — e.g., constrained embedded storage:

```python
ConfigureLogger(
    log_path='./logs', pg_name='App',
    routing_mode='size',
    max_bytes=10_485_760,   # 10 MB per file
    max_count=5,            # cycle through 5 files
    suffix_digits=3,        # 000-004 suffixes
)
```

The directory cycles through a fixed set of files:

```
logs/
├── App_000.log   ← oldest
├── App_001.log
├── App_002.log
├── App_003.log
├── App_004.log   ← current, writing
```

When `App_004.log` reaches 10 MB, the next write is routed back to `App_000.log`.
D-SafeLogger opens files append-only and does not rename or truncate active files;
cyclic modes bound the filename set. Internal purge/archive (`backup_count`, `archive_mode`) is
rejected for cyclic modes by design, so if you also need cumulative retention beyond the cycle
window, use an external rotation or archival system that copies closed routed files to long-term
storage.

---

## Hourly for High-Volume

For APIs that produce gigabytes per day, hourly rotation keeps individual files manageable:

```python
ConfigureLogger(
    log_path='./logs', pg_name='Gateway',
    routing_mode='hourly',
    backup_count=168,   # keep 7 days (24 × 7)
)
```

Each file covers one hour: `Gateway_2026040109.log`, `Gateway_2026040110.log`, etc.

---

## How Purge and Archive Work

- **Purge runs AFTER each file switch** — not on a timer, not in a cron job.
- Files older than `backup_count` periods are candidates for removal.
- With `archive_mode=True`, candidates are compressed to `.zip` at low priority instead of
  being deleted immediately.
- Both the archiver and purge workers join on `atexit` — no orphaned files, no partial ZIPs.

---

## Monitoring Rotation

Use the CLI to inspect your log directory:

```bash
dsafelogger ls ./logs
```

This lists all log files with sizes, dates, and sidecar status.

---

## Complete Runnable Example

Save this as `service_demo.py`:

```python
"""Simulates a long-running service with daily log rotation."""

import time
import random
from dsafelogger import ConfigureLogger, GetLogger

# Configure daily rotation: keep 7 days, archive old files
ConfigureLogger(
    log_path='./logs',
    pg_name='DemoService',
    routing_mode='daily',
    backup_count=7,
    archive_mode=True,
)

logger = GetLogger('service')

EVENTS = [
    ('info', 'Health check passed'),
    ('info', 'Request processed successfully'),
    ('info', 'Cache refreshed'),
    ('warning', 'Slow query detected: 2.3s'),
    ('error', 'Connection to database timed out'),
    ('info', 'Request processed successfully'),
    ('info', 'Scheduled task completed'),
]


def simulate_service():
    """Simulate a service that logs events continuously."""
    logger.info('DemoService starting up')

    cycle = 0
    try:
        while True:
            cycle += 1
            event_level, event_msg = random.choice(EVENTS)
            getattr(logger, event_level)(f'[cycle={cycle}] {event_msg}')
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info('DemoService shutting down')


if __name__ == '__main__':
    simulate_service()
```

---

## How to Run

```bash
# Basic run — logs rotate daily into ./logs/
python service_demo.py

# Let it run, then inspect the log directory
dsafelogger ls ./logs

# Stop with Ctrl+C — atexit ensures clean shutdown
```

In a real deployment you would run this as a systemd service or Docker container.
The rotation and purge happen automatically — no external log-rotate tooling required.
