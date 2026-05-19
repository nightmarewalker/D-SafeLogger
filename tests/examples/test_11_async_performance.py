"""Runnable scenario for examples/11_async_performance.md."""

from __future__ import annotations

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
    )

    logger = GetLogger("async.demo")

    def worker(worker_id: int, iterations: int = 20) -> None:
        with logger.contextualize(worker=worker_id):
            for idx in range(iterations):
                logger.info(f"Processing item {idx}")
                time.sleep(0.001)
            logger.info("Worker finished")

    num_workers = 8
    start = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(num_workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - start

    logger.info(f"All {num_workers} workers done in {elapsed:.3f}s")
    _shutdown()

    output = (log_dir / "AsyncPerfDemo.log").read_text(encoding="utf-8")
    assert output.count("Worker finished") == num_workers
    assert "Processing item 19" in output
    assert f"All {num_workers} workers done" in output
    assert "worker:0" in output
    assert "worker:7" in output
