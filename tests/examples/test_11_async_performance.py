"""Runnable scenario for examples/11_async_performance.md."""

from __future__ import annotations

import json
import threading
import time

from dsafelogger import ConfigureLogger, GetLogger, _shutdown


def test_async_performance_preserves_context_from_threads(tmp_path, clean_env):
    log_dir = tmp_path / "logs"

    ConfigureLogger(
        log_path=str(log_dir),
        pg_name="AsyncPerfDemo",
        console_out=False,
        is_async=True,
        structured=True,
    )

    logger = GetLogger("async.demo")

    def worker(worker_id: int) -> None:
        with logger.contextualize(worker=worker_id):
            for idx in range(3):
                logger.info("Processing item", extra={"item": idx})
                time.sleep(0.001)
            logger.info("Worker finished")

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    _shutdown()

    records = [
        json.loads(line)
        for line in (log_dir / "AsyncPerfDemo.log").read_text(encoding="utf-8").splitlines()
    ]
    finished_workers = {
        record["worker"] for record in records if record["message"] == "Worker finished"
    }
    assert finished_workers == {0, 1, 2}
    assert any(record.get("item") == 2 for record in records)
