"""Runnable scenario for examples/10_incident_response_bundle.md."""

from __future__ import annotations

import json
import os

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def _fail_payment() -> None:
    api_token = "tok_live_should_be_masked"
    raise RuntimeError(f"payment gateway rejected token length {len(api_token)}")


def test_incident_response_bundle(tmp_path, clean_env):
    os.environ["D_LOG_DIAGNOSE"] = "1"
    bundle_dir = tmp_path / "logs" / "incident_bundle"
    manifest_dir = tmp_path / "audit-manifests"
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
            _fail_payment()
        except RuntimeError:
            logger.exception("captured failing payment path")
        for idx in range(8):
            logger.info("bundle filler record", extra={"sequence": idx})
    _shutdown()

    log_files = sorted(bundle_dir.glob("Incident_*.log"))
    assert log_files

    records = []
    for path in log_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            records.append(json.loads(line))

    assert any(r.get("incident_id") == "inc-20260515-001" for r in records)
    assert any(r.get("request_id") == "req-77" for r in records)
    assert any(r.get("message") == "captured failing payment path" for r in records)
    assert "tok_live_should_be_masked" not in "\n".join(
        p.read_text(encoding="utf-8") for p in log_files
    )
    assert any("api_token" in json.dumps(r, ensure_ascii=False) for r in records)
    assert list(bundle_dir.glob("*.sha256"))
    assert manifest.exists()
