"""Runnable scenarios for examples/18_console_progress_coexistence.md."""

from __future__ import annotations

import io
import json
import logging

import pytest

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_tqdm_progress_with_durable_file_logging(tmp_path, clean_env):
    tqdm_mod = pytest.importorskip("tqdm")

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="TqdmProgress",
        structured=True,
        console_out=False,
    )

    logger = GetLogger("jobs.tqdm")
    for item in tqdm_mod.tqdm(range(3), desc="import", file=io.StringIO()):
        logger.info("processed item", extra={"item": item, "renderer": "tqdm"})

    SafeShutdown()

    log_path = tmp_path / "TqdmProgress.log"
    assert log_path.exists()
    records = _read_jsonl(log_path)
    assert [record["renderer"] for record in records] == ["tqdm", "tqdm", "tqdm"]
    assert [record["item"] for record in records] == [0, 1, 2]
    assert not any(
        handler.__class__.__module__.startswith("dsafelogger")
        for handler in logging.getLogger().handlers
    )


def test_rich_progress_with_durable_file_logging_and_no_handler_leak(tmp_path, clean_env):
    rich_console = pytest.importorskip("rich.console")
    rich_logging = pytest.importorskip("rich.logging")
    rich_progress = pytest.importorskip("rich.progress")

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="RichProgress",
        structured=True,
        console_out=False,
    )

    console = rich_console.Console(file=io.StringIO(), force_terminal=False)
    rich_handler = rich_logging.RichHandler(
        console=console,
        show_time=False,
        show_path=False,
    )
    root = logging.getLogger()
    root.addHandler(rich_handler)

    try:
        logger = GetLogger("jobs.rich")
        with rich_progress.Progress(console=console, transient=True) as progress:
            task = progress.add_task("export", total=3)
            for item in range(3):
                logger.info("processed item", extra={"item": item, "renderer": "rich"})
                progress.advance(task)
    finally:
        if rich_handler in root.handlers:
            root.removeHandler(rich_handler)
        rich_handler.close()
        SafeShutdown()

    log_path = tmp_path / "RichProgress.log"
    assert log_path.exists()
    records = _read_jsonl(log_path)
    assert [record["renderer"] for record in records] == ["rich", "rich", "rich"]
    assert [record["item"] for record in records] == [0, 1, 2]
    assert rich_handler not in root.handlers
