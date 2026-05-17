# Incident Response Bundle

This guide combines D-SafeLogger features into a small incident handoff bundle:
structured JSON Lines, contextual identifiers, diagnostic masking, SHA-256
sidecars, and a manifest.

D-SafeLogger is not an access-control system, DLP product, SIEM, or remote log
collector. The point of this pattern is to make local evidence files easier to
inspect and verify before handing them to your normal incident process.

## The Scenario

An operator needs a compact local bundle for a production incident:

- an `incident_id` attached to all related records;
- JSON Lines output for machine parsing;
- diagnostic locals enabled only by environment variable;
- sensitive local variables masked in diagnostic exception output;
- SHA-256 sidecars and a manifest for completed routed files.

## What Goes Into the Bundle

The bundle directory contains D-SafeLogger output files such as:

```text
incident_bundle/
├── Incident_000.log
├── Incident_000.log.sha256
└── Incident_001.log

audit-manifests/
└── Incident_manifest.txt
```

Hash sidecars are generated for completed files when routing switches to the
next destination.

## Safe Diagnostic Toggle

Diagnostic local-variable expansion is intentionally enabled through the
environment variable `D_LOG_DIAGNOSE=1`, not through normal application code.
Keep it off by default and enable it only for a bounded investigation window.

## Structured Evidence Logs

Use `structured=True` so each log line is a JSON object. Add incident and request
identifiers through `contextualize()` or `extra`.

## Integrity Sidecars and Manifest

Use `enable_hash=True` and `manifest_path=...` with a non-cyclic routing mode.
Do not treat the sidecar as a cryptographic signature; if an attacker can modify
the log, sidecar, and manifest with the same privileges, use external signing or
write-once storage.

The manifest is intentionally placed outside the log directory (`./audit-manifests/`) so that
retention, ACLs, backups, and append-only or immutable storage can be applied independently from the
operational log files. This is a placement recommendation, not a tamper-proofing claim.

## Complete Runnable Example

The tested scenario for this guide is maintained in
`tests/examples/test_10_incident_response_bundle.py`.

```python
"""incident_response_bundle.py"""

import os
from pathlib import Path

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def fail_payment() -> None:
    api_token = "tok_live_should_be_masked"
    raise RuntimeError(f"payment gateway rejected token length {len(api_token)}")


def main() -> None:
    os.environ["D_LOG_DIAGNOSE"] = "1"
    bundle_dir = Path("./logs/incident_bundle")
    manifest_dir = Path("./audit-manifests")
    manifest = manifest_dir / "Incident_manifest.txt"

    ConfigureLogger(
        log_path=str(bundle_dir),
        pg_name="Incident",
        console_out=False,
        structured=True,
        routing_mode="size",
        max_bytes=300,
        suffix_digits=3,
        enable_hash=True,
        manifest_path=str(manifest),
    )

    logger = GetLogger("incident.checkout")
    with logger.contextualize(incident_id="inc-20260515-001", request_id="req-77"):
        logger.info("incident investigation started")
        try:
            fail_payment()
        except RuntimeError:
            logger.exception("captured failing payment path")

        for idx in range(8):
            logger.info("bundle filler record", extra={"sequence": idx})

    _shutdown()
    print(f"bundle directory: {bundle_dir}")
    print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
```

## How to Run

```bash
python incident_response_bundle.py
```

For repository validation, run the maintained scenario test:

```bash
uv run pytest tests/examples/test_10_incident_response_bundle.py -q
```

## What to Check

- generated `.log` files contain JSON Lines records;
- `incident_id` and `request_id` appear in incident records;
- diagnostic local variable `api_token` is masked;
- at least one `.sha256` sidecar and `audit-manifests/Incident_manifest.txt` are present after routing.

## Operational Boundaries

- Masking applies to diagnostic local variables, not arbitrary message text or a
  complete DLP policy.
- SHA-256 sidecars detect accidental changes and support transfer verification;
  they do not replace external signing or access control.
- Remote aggregation remains the responsibility of your collector or SIEM.

## What's Next

- [CLI Operations Guide](14_cli_operations.md)
- [Compliance & Audit Logging](08_compliance_audit.md)
