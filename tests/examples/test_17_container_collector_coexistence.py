"""Runnable scenario for examples/17_container_collector_coexistence.md."""

from __future__ import annotations

import json

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def test_container_collector_coexistence(tmp_path, clean_env, capsys):
    log_dir = tmp_path / "container-audit"
    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="ContainerAudit",
        console_out=False,
        structured=True,
    )

    print(json.dumps({"stream": "platform", "event": "startup"}))

    audit = GetLogger("container.audit")
    audit.info(
        "local audit record",
        extra={"container_id": "local-dev", "operation": "startup"},
    )
    _shutdown()

    captured = capsys.readouterr()
    assert '"stream": "platform"' in captured.out

    log_file = log_dir / "ContainerAudit.log"
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert any(record["message"] == "local audit record" for record in records)
    assert any(record.get("container_id") == "local-dev" for record in records)

