# External Rotation and Reopen

This example shows how to coexist with an external rotator such as `logrotate`.
It is a compatibility path, not D-SafeLogger's main file lifecycle model.

D-SafeLogger has built-in append-only routing modes (`daily`, `hourly`, `size`,
`count`, etc.). Prefer those when the application itself can own file switching.

Use `ReopenLogFiles()` only when operations require an external rotator.
Configure D-SafeLogger with `routing_mode='none'`, let the external tool handle
rename/create, and call `ReopenLogFiles()` from the application after that.

Why this is a compatibility path: in the main D-SafeLogger model, the library
opens the next destination at the routing boundary instead of renaming or
truncating the active file. `ReopenLogFiles()` is only valid for
`routing_mode='none'`, i.e. when an external system owns rotation and
D-SafeLogger only reconnects its sinks afterwards.

## Single-Process Example

```python
"""external_reopen_demo.py - cooperate with external log rotation."""

import signal
from dsafelogger import ConfigureLogger, GetLogger, ReopenLogFiles


ConfigureLogger(
    log_path='/var/log/myapp',
    pg_name='myapp',
    routing_mode='none',
    console_out=False,
)

logger = GetLogger('myapp')


def handle_sighup(signum, frame):
    ReopenLogFiles()
    logger.info('log files reopened after external rotation')


signal.signal(signal.SIGHUP, handle_sighup)
logger.info('service started')
```

## logrotate Snippet

```text
/var/log/myapp/myapp.log {
    daily
    rotate 14
    missingok
    notifempty
    create 0640 myapp myapp
    postrotate
        kill -HUP $(cat /run/myapp.pid)
    endscript
}
```

## Multiprocess Example

For `dsafelogger.mp`, call `mp.ReopenLogFiles()` from an attached process. The
request is sent to the Writer runtime and acknowledged through the control plane.

```python
from dsafelogger import mp


def handle_rotation_notice() -> None:
    mp.ReopenLogFiles()
```

## Constraints

- `ReopenLogFiles()` requires `routing_mode='none'` for active file sinks.
- It does not install signal handlers; your service or supervisor must call it.
- It is for rename/create external rotation. It is not needed for D-SafeLogger's
  built-in routing modes.
- The active file is reopened; completed files can then be compressed, shipped, or
  hashed by your external retention pipeline.
