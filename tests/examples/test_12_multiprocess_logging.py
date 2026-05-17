"""Runnable scenario for examples/12_multiprocess_logging.md."""

from __future__ import annotations

import json
import multiprocessing
import time

import pytest

from dsafelogger import mp
from dsafelogger._mp_protocol import BootstrapContext


def _mp_example_worker(log_ctx: BootstrapContext, result_queue) -> None:
    mp.AttachCurrentProcess(log_ctx)
    try:
        logger = mp.GetLogger("jobs.worker")
        with logger.contextualize(worker=1, request_id="req-mp-001"):
            logger.info("worker processed job", extra={"job_id": "job-42"})
        time.sleep(0.1)
        result_queue.put("done")
    finally:
        mp.DetachCurrentProcess()


@pytest.mark.timeout(30)
def test_multiprocess_logging_worker_reaches_writer(tmp_path, mp_state):
    spawn_ctx = multiprocessing.get_context("spawn")
    log_ctx = mp.ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="MPExample",
        console_out=False,
        structured=True,
        mp_context=spawn_ctx,
    )

    result_queue = spawn_ctx.Queue(1)
    process = spawn_ctx.Process(target=_mp_example_worker, args=(log_ctx, result_queue))
    process.start()
    process.join(timeout=15)
    assert process.exitcode == 0
    assert result_queue.get(timeout=5) == "done"

    time.sleep(0.2)
    mp.DetachCurrentProcess()

    records = [
        json.loads(line)
        for line in (tmp_path / "MPExample.log").read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        record["message"] == "worker processed job"
        and record["worker"] == 1
        and record["request_id"] == "req-mp-001"
        and record["job_id"] == "job-42"
        for record in records
    )
