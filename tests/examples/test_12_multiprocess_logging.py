"""Runnable scenario for examples/12_multiprocess_logging.md."""

from __future__ import annotations

import json
import multiprocessing
import re
import time

import pytest

from dsafelogger import mp
from dsafelogger._mp_protocol import BootstrapContext


def _mp_example_worker(log_ctx: BootstrapContext, worker_id: int, result_queue) -> None:
    mp.AttachCurrentProcess(log_ctx)
    try:
        logger = mp.GetLogger("jobs.worker")
        with logger.contextualize(worker=worker_id):
            logger.info("worker started")
            logger.info("worker finished")
        time.sleep(0.1)
        result_queue.put(worker_id)
    finally:
        mp.DetachCurrentProcess()


@pytest.mark.timeout(30)
def test_multiprocess_console_less_observability_outputs(tmp_path, mp_state):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    spawn_ctx = multiprocessing.get_context("spawn")
    mp.ConfigureLogger(
        log_path=str(logs_dir),
        pg_name="MPDemo",
        routing_mode="daily",
        console_out=False,
        structured=True,
        mp_context=spawn_ctx,
        runtime_warning_path=str(logs_dir / "runtime-warning.jsonl"),
        shutdown_report_path=str(logs_dir / "shutdown-report.json"),
    )

    logger = mp.GetLogger("jobs.parent")
    logger.info("parent status probe")

    # Writer processes records asynchronously; poll until accepted.
    # CI runners (especially GitHub Actions Windows/macOS) can be slow;
    # use a generous timeout well within the test-level @pytest.mark.timeout(30).
    deadline = time.monotonic() + 5.0
    status = mp.GetDeliveryStatus()
    while status["accepted"] < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
        status = mp.GetDeliveryStatus()

    assert status["accepted"] >= 1
    assert "writer_reject_breakdown" in status
    assert "worker_drop_breakdown" in status
    assert "writer_drop_breakdown" in status
    assert status["missing_detach_clients"] == 0

    # _mp_shutdown() detaches the parent and stops the Writer (which writes the
    # shutdown report). DetachCurrentProcess() alone does NOT stop the Writer.
    mp._mp_shutdown()

    report = json.loads((logs_dir / "shutdown-report.json").read_text(encoding="utf-8"))
    assert report["shutdown_result"] == "clean"
    assert report["missing_detach_clients"] == 0
    assert "warning_queue_drain_incomplete" in report


@pytest.mark.timeout(30)
def test_multiprocess_logging_worker_reaches_writer(tmp_path, mp_state):
    spawn_ctx = multiprocessing.get_context("spawn")
    log_ctx = mp.ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="MPDemo",
        routing_mode="daily",
        console_out=False,
        structured=True,
        mp_context=spawn_ctx,
    )

    result_queue = spawn_ctx.Queue(4)
    processes = [
        spawn_ctx.Process(target=_mp_example_worker, args=(log_ctx, worker_id, result_queue))
        for worker_id in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0
    assert sorted(result_queue.get(timeout=5) for _ in processes) == [0, 1, 2, 3]

    time.sleep(0.2)
    mp.DetachCurrentProcess()

    log_files = sorted(tmp_path.glob("MPDemo_*.log"))
    assert len(log_files) == 1
    assert re.fullmatch(r"MPDemo_\d{8}\.log", log_files[0].name)
    records = [
        json.loads(line)
        for line in log_files[0].read_text(encoding="utf-8").splitlines()
    ]
    assert {record["worker"] for record in records if record["message"] == "worker started"} == {
        0, 1, 2, 3,
    }
    assert {record["worker"] for record in records if record["message"] == "worker finished"} == {
        0, 1, 2, 3,
    }
