"""Runnable scenario for examples/08_compliance_audit.md."""

from __future__ import annotations

import json
import re

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def test_compliance_audit_writes_hash_sidecars_and_manifest(tmp_path, clean_env):
    log_dir = tmp_path / "logs"
    manifest_dir = tmp_path / "audit-manifests"
    manifest = manifest_dir / "AuditService_manifest.txt"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="AuditService",
        console_out=False,
        structured=True,
        routing_mode="size",
        max_bytes=260,
        suffix_digits=3,
        enable_hash=True,
        manifest_path=str(manifest),
    )

    logger = GetLogger("audit")
    for idx in range(10):
        logger.info("audit event", extra={"audit_id": f"audit-{idx:03d}"})
    _shutdown()

    log_files = sorted(log_dir.glob("AuditService_*.log"))
    sidecars = sorted(log_dir.glob("AuditService_*.log.sha256"))
    assert log_files
    assert sidecars
    assert manifest.exists()

    sidecar_text = sidecars[0].read_text(encoding="utf-8").strip()
    assert re.match(r"^[0-9a-f]{64}  AuditService_\d{3}\.log$", sidecar_text)
    assert sidecar_text in manifest.read_text(encoding="utf-8")

    records = []
    for path in log_files:
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    assert any(record.get("audit_id") == "audit-009" for record in records)
