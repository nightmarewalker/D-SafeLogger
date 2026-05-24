"""Runnable scenario for examples/08_compliance_audit.md."""

from __future__ import annotations

import json
import re
from datetime import datetime

from dsafelogger import ConfigureLogger, GetLogger, _shutdown, RegisterLevel
from dsafelogger import _routing


def test_compliance_audit_writes_daily_hash_sidecars_and_manifest(tmp_path, clean_env, monkeypatch):
    log_dir = tmp_path / "logs"
    manifest_dir = tmp_path / "audit-manifests"
    manifest = manifest_dir / "AuditService_manifest.txt"

    class FakeDateTime:
        current = datetime(2026, 4, 1, 23, 59, 59)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(_routing, "datetime", FakeDateTime)

    RegisterLevel("AUDIT", 35, "AUD", "\033[95m")

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="AuditService",
        console_out=False,
        structured=True,
        routing_mode="daily",
        enable_hash=True,
        manifest_path=str(manifest),
    )

    logger = GetLogger("audit")
    logger.info("AuditService started")
    logger.audit("User alice logged in from 192.168.1.100")

    FakeDateTime.current = datetime(2026, 4, 2, 0, 0, 1)
    logger.audit("Admin charlie exported full audit trail")
    _shutdown()

    log_files = sorted(log_dir.glob("AuditService_*.log"))
    sidecars = sorted(log_dir.glob("AuditService_*.log.sha256"))
    assert [path.name for path in log_files] == [
        "AuditService_20260401.log",
        "AuditService_20260402.log",
    ]
    assert [path.name for path in sidecars] == ["AuditService_20260401.log.sha256"]
    assert manifest.exists()

    sidecar_text = sidecars[0].read_text(encoding="utf-8").strip()
    assert re.match(r"^[0-9a-f]{64}  AuditService_20260401\.log$", sidecar_text)
    assert sidecar_text in manifest.read_text(encoding="utf-8")

    records = []
    for path in log_files:
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    assert any(record["level"] == "AUD" for record in records)
    assert any(record["message"] == "Admin charlie exported full audit trail" for record in records)
