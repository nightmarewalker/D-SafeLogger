"""Runnable scenario for examples/19_sentry_coexistence.md."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_sentry_coexistence_records_local_jsonl_without_remote_claim(tmp_path, clean_env):
    pytest.importorskip("sentry_sdk")

    script = tmp_path / "sentry_case.py"
    script.write_text(
        """
import os
import sys

import sentry_sdk

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    traces_sample_rate=0.0,
)

ConfigureLogger(
    log_path=sys.argv[1],
    pg_name="SentryLocal",
    structured=True,
    console_out=False,
)

logger = GetLogger("checkout.sentry")

try:
    raise RuntimeError("payment provider rejected request")
except RuntimeError as exc:
    sentry_sdk.capture_exception(exc)
    logger.exception(
        "captured local exception",
        extra={"system": "sentry", "remote_delivery_claimed": False},
    )
finally:
    SafeShutdown()

print("ok")
""".lstrip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("SENTRY_DSN", None)
    src_path = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = (
        src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    )

    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path)],
        text=True,
        capture_output=True,
        timeout=20,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"
    assert result.stderr == ""

    log_path = tmp_path / "SentryLocal.log"
    assert log_path.exists()
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["message"] == "captured local exception"
    assert records[0]["system"] == "sentry"
    assert records[0]["remote_delivery_claimed"] is False
