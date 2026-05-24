# Compliance & Audit Logging

In regulated industries — healthcare (HIPAA), finance (SOC 2, PCI-DSS), government (FedRAMP) —
proving that logs haven't been tampered with isn't optional. An attacker who gains access to your
server will edit or truncate logs to cover their tracks. D-SafeLogger provides cryptographic proof
of integrity: a SHA-256 hash for every completed log file, stored both as a sidecar (compatible
with `sha256sum -c`) and in a timestamped manifest.

---

## What You Get

When hashing and manifest are enabled, the log files and audit manifest are kept separate:

```
logs/
├── AuditService_20260401.log           ← log data
├── AuditService_20260401.log.sha256    ← sidecar hash
├── AuditService_20260402.log
├── AuditService_20260402.log.sha256
└── AuditService_20260403.log           ← current (no sidecar yet)

audit-manifests/
└── AuditService_manifest.txt           ← cumulative hash log
```

- Each completed (rotated) file gets a `.sha256` sidecar.
- The current file has no sidecar — it's still being written to.
- `AuditService_manifest.txt` accumulates every hash with a timestamp.

---

## Setting Up

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(
    log_path='./logs', pg_name='AuditService',
    routing_mode='daily',
    enable_hash=True,                       # SHA-256 sidecar per file
    manifest_path='./audit-manifests/AuditService_manifest.txt',
    structured=True,                        # JSON output for machine parsing
)

logger = GetLogger('audit')
logger.info('Audit logging initialized')
```

---

## Sidecar Format

Each `.sha256` file contains a single line, compatible with `sha256sum -c`:

```
a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01  AuditService_20260401.log
```

---

## Manifest Format

The manifest is a timestamped chain — each line records when a file was finalized and its hash:

```
[2026-04-01T23:59:59.999] a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01  AuditService_20260401.log
[2026-04-02T23:59:59.999] e5f6a7b8901234567890abcdef1234567890abcdef1234567890abcdef123456  AuditService_20260402.log
```

An auditor can verify the manifest against the sidecars to confirm nothing was altered.

---

## Threat Model and Limitations

The sidecar + manifest flow proves that a **completed** log file still matches the recorded SHA-256
digest. It does **not** make local logs tamper-proof by itself.

- If an attacker can rewrite the log file **and** its `.sha256` / manifest with the same OS
  permissions, they can regenerate matching hashes.
- The **current active log file** is not hashed until rotation/finalization happens.
- The manifest records operational metadata (when files were finalized), so it needs normal access
  control just like the logs themselves.

Place the manifest outside the log directory so retention, ACLs, backups, and append-only or
immutable storage replication can be managed independently. This placement helps operations; it is
not a tamper-proofing claim.

For stronger guarantees, ship sidecars/manifests to an **external append-only or immutable
store** (for example S3 Object Lock, WORM storage, or a separate audit system). If you need
cryptographic non-repudiation, layer a signing scheme on top.

---

## Verification

Verify a single file using the sidecar:

```bash
cd logs/
sha256sum -c AuditService_20260401.log.sha256
# AuditService_20260401.log: OK
```

If the file was modified, you'll see:

```
AuditService_20260401.log: FAILED
sha256sum: WARNING: 1 computed checksum did NOT match
```

---

## Automated Verification Script

Save this as `verify_logs.sh` to verify ALL sidecars in a directory:

```bash
#!/usr/bin/env bash
# Verify all .sha256 sidecars in the given log directory.
# Usage: ./verify_logs.sh ./logs

LOG_DIR="${1:-.}"
PASSED=0
FAILED=0

for sidecar in "$LOG_DIR"/*.sha256; do
    [ -f "$sidecar" ] || continue
    if sha256sum -c "$sidecar" --quiet 2>/dev/null; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
        echo "FAIL: $sidecar"
    fi
done

echo "---"
echo "Passed: $PASSED  Failed: $FAILED"
[ "$FAILED" -eq 0 ] && echo "ALL CHECKS PASSED" || exit 1
```

```bash
chmod +x verify_logs.sh
./verify_logs.sh ./logs
```

---

## Why Structured JSON Matters for Compliance

Auditors need to query logs programmatically, not grep plain text. With `structured=True`, every
log line is a JSON object:

```json
{"timestamp": "2026-04-03T09:15:22.738", "level": "WAR", "logger": "auth", "file": "auth.py", "line": 42, "function": "login", "message": "login failed for user bob"}
```

Query with `jq`:

```bash
# Find all login failures in the audit period
cat logs/*.log | jq 'select(.level == "WAR" and (.message | contains("login failed")))'

# Extract all data export events
cat logs/*.log | jq 'select(.message | contains("exported"))'

# Count errors per day
cat logs/*.log | jq -r '.timestamp[:10]' | sort | uniq -c
```

---

## Combining with a Custom Audit Level

Create a dedicated AUDIT level so audit events are never silenced by global level changes:

```python
from dsafelogger import ConfigureLogger, GetLogger, RegisterLevel

# AUDIT sits between WARNING (30) and ERROR (40)
# Even if default_level is WARNING, AUDIT events still appear.
RegisterLevel('AUDIT', 35, 'AUD', '\033[95m')

ConfigureLogger(
    log_path='./logs', pg_name='AuditService',
    routing_mode='daily',
    enable_hash=True,
    manifest_path='./audit-manifests/AuditService_manifest.txt',
    structured=True,
)

logger = GetLogger('audit')

# Normal application logs
logger.info('Service started')

# Audit events — always visible at WARNING level or above
logger.audit('User alice exported customer list')
logger.audit('Admin bob changed role for user charlie')
```

Because AUDIT (35) is above WARNING (30), these events survive even when `default_level='WARNING'`.

---

## Complete Runnable Example

Save this as `audit_demo.py`:

```python
"""Demonstrates compliance-grade audit logging with integrity verification."""

from dsafelogger import ConfigureLogger, GetLogger, RegisterLevel

# Register a custom AUDIT level before ConfigureLogger
RegisterLevel('AUDIT', 35, 'AUD', '\033[95m')

ConfigureLogger(
    log_path='./logs',
    pg_name='AuditService',
    routing_mode='daily',
    enable_hash=True,
    manifest_path='./audit-manifests/AuditService_manifest.txt',
    structured=True,
)

logger = GetLogger('audit')


def simulate_audit_events():
    """Simulate a day of audit-worthy events."""
    logger.info('AuditService started')

    # Normal operations
    logger.info('Connected to database')
    logger.info('Cache warmed up')

    # Audit events
    logger.audit('User alice logged in from 192.168.1.100')
    logger.audit('User alice exported customer list (1,204 records)')
    logger.warning('Failed login attempt for user bob from 10.0.0.5')
    logger.warning('Failed login attempt for user bob from 10.0.0.5')
    logger.warning('Failed login attempt for user bob from 10.0.0.5')
    logger.audit('Account bob locked after 3 failed attempts')

    # Sensitive operation
    logger.audit('Admin charlie changed role for user dave: viewer -> admin')
    logger.audit('Admin charlie exported full audit trail')

    logger.info('AuditService shutting down')


if __name__ == '__main__':
    simulate_audit_events()

    print('\n--- Verification ---')
    print('Run these commands to verify log integrity:')
    print('  cd logs/')
    print('  sha256sum -c *.sha256')
    print('  cat ../audit-manifests/AuditService_manifest.txt')
```

---

## How to Run

```bash
# Generate audit logs
python audit_demo.py

# Inspect the structured JSON output
cat logs/AuditService_*.log | python -m json.tool

# Verify integrity of completed (rotated) files
cd logs/
sha256sum -c *.sha256

# Check the manifest
cat ../audit-manifests/AuditService_manifest.txt
```

For a production deployment, schedule the verification script (`verify_logs.sh`) as a daily cron
job and alert if any check fails. Ship the manifest to a separate, append-only or immutable storage
system (e.g., S3 Object Lock) for stronger retention guarantees.
