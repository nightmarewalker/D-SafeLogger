# CLI Operations Guide

You don't always have Python available when you need to check logs. Maybe you're
SSH'd into a production server, or you're in a Docker container with minimal
tooling. The `dsafelogger` command-line tool understands D-SafeLogger's file naming
conventions and gives you three essential capabilities: scaffolding configuration,
listing log files, and live-tailing with transparent file-switch detection.

## Installation

The `dsafelogger` command is installed automatically with the library:

```bash
pip install d-safelogger
```

Verify the installation:
```bash
dsafelogger --help
```

## Command 1: `dsafelogger init` — Generate INI Template

Outputs a fully-documented INI configuration template to stdout. Redirect it to
a file to create your starting configuration:

```bash
dsafelogger init > logging.ini
```

The generated template includes every option with sensible defaults and inline
comments explaining each setting. A typical workflow:

```bash
# Generate the template
dsafelogger init > logging.ini

# Edit to match your environment
vim logging.ini

# Your app loads it at startup
# ConfigureLogger(config_file='logging.ini')
```

Example snippet from the generated output:
```ini
[global]
default_level = INFO
log_path = ./logs
pg_name = MyApp
# routing_mode = daily
# backup_count = 30
# is_async = false
# enable_hash = false
# structured = false
# console_out = true
```

## Command 2: `dsafelogger ls` — List Log Files

Lists all log files in a directory, grouped by program name:

```bash
dsafelogger ls ./logs
```

Output:
```
OrderService     OrderService_20260401.log      1,234,567 bytes  2026-04-01 23:59:59
OrderService     OrderService_20260402.log        987,654 bytes  2026-04-02 23:59:59
OrderService     OrderService_20260403.log        123,456 bytes  2026-04-03 14:30:22
PaymentWorker    PaymentWorker_20260403.log        45,678 bytes  2026-04-03 14:30:22
```

Files are grouped by `pg_name` and sorted by date, giving you an instant overview
of which services are writing and how much data they produce.

## Command 3: `dsafelogger tail -f` — Live Tail

Follow log output in real-time:

```bash
dsafelogger tail -f ./logs OrderService
```

The key advantage over system `tail -f`: **transparent file switching**. At midnight,
when `routing_mode=daily` creates `OrderService_20260404.log`, `dsafelogger tail -f`
automatically detects the new file and follows it. System `tail -f` stays stuck on
the old file.

Options:

```bash
# Show last 50 lines initially (default: 10)
dsafelogger tail -f ./logs OrderService -n 50

# Faster polling for low-latency monitoring
dsafelogger tail -f ./logs OrderService --poll-interval 0.1
```

Stop tailing with `Ctrl+C`.

## Production Workflow

A complete scenario from deployment to monitoring:

```bash
# 1. Generate configuration on the production server
dsafelogger init > /etc/myapp/logging.ini

# 2. Edit to match your production paths and settings
vim /etc/myapp/logging.ini

# 3. Deploy and start the application
#    (app loads logging.ini via ConfigureLogger(config_file=...))
systemctl start myapp

# 4. Verify logs are being written
dsafelogger ls /var/log/myapp
# Output:
#   OrderService     OrderService_20260403.log     123,456 bytes  2026-04-03 14:30:22
#   PaymentWorker    PaymentWorker_20260403.log      45,678 bytes  2026-04-03 14:30:22

# 5. Monitor the order service in real-time
dsafelogger tail -f /var/log/myapp OrderService
# Output streams live:
#   2026-04-03 14:30:22.001 [INF][app.py:35:main] Server started on port 8080
#   2026-04-03 14:30:23.456 [INF][app.py:52:handle] GET /orders → 200
#   ...

# 6. Midnight: daily rotation creates OrderService_20260404.log
#    tail -f seamlessly switches to the new file — no restart needed

# 7. Next day: verify yesterday's log integrity
sha256sum -c /var/log/myapp/OrderService_20260403.log.sha256
```

## Docker Usage

The CLI works inside containers with no extra setup:

```bash
# List log files in a running container
docker exec -it myapp-container dsafelogger ls /var/log/myapp

# Live-tail from inside the container
docker exec -it myapp-container dsafelogger tail -f /var/log/myapp OrderService

# Generate config during image build (Dockerfile)
# RUN dsafelogger init > /etc/myapp/logging.ini
```

## Complete Example

Create a small application to see all three commands in action.

Save as `cli_demo_app.py`:

```python
"""cli_demo_app.py — Generate logs for CLI demonstration."""

import time
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs',
    pg_name='CLIDemo',
    routing_mode='daily',
    enable_hash=True,
)

logger = GetLogger(__name__)

for i in range(50):
    logger.info(f'Processing request {i}')
    time.sleep(0.05)

logger.info('All requests processed')
print('Logs written to ./logs/')
```

### Walkthrough

```bash
# Step 1: Generate a config template
dsafelogger init > logging.ini

# Step 2: Run the demo app to generate log files
python cli_demo_app.py

# Step 3: List generated log files
dsafelogger ls ./logs
# Output:
#   CLIDemo    CLIDemo_20260403.log    4,567 bytes  2026-04-03 14:30:25

# Step 4: Tail the log (shows last 10 lines, then exits since app is done)
dsafelogger tail -f ./logs CLIDemo -n 20
```

## How to Run

```bash
pip install d-safelogger

# Generate config template
dsafelogger init > logging.ini

# Run the demo app
python cli_demo_app.py

# List log files
dsafelogger ls ./logs

# Live-tail (Ctrl+C to stop)
dsafelogger tail -f ./logs CLIDemo
```
