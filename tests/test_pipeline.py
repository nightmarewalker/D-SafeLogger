"""Tests for dsafelogger._pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from dsafelogger._pipeline import PipelineBuilder, ResolvedConfig
from dsafelogger._transport import DirectTransport, QueueTransport


def test_pipeline_builder_sync(tmp_path: Path):
    config = ResolvedConfig(
        pg_name='test',
        log_dir=tmp_path,
        file_fmt='%(message)s',
        console_fmt='%(message)s',
        routing_mode='none',
        routing_kwargs={},
        backup_count=0,
        archive_mode=False,
        enable_hash=False,
        manifest_path=None,
        encoding='utf-8',
        diagnose=False,
        max_level='INFO',
        console=True,
        is_async=False,
        queue_size=-1,
        log_level='DEBUG',
        color_stream=False,
        module_configs={},
        color_overrides={},
    )

    builder = PipelineBuilder()
    pipeline = builder.build(config)
    
    assert isinstance(pipeline.transport, DirectTransport)
    
    # 2 handlers: file and console
    assert len(pipeline.transport._target_handlers) == 2


def test_pipeline_builder_applies_resolved_datefmt_to_text_formatters(tmp_path: Path):
    config = ResolvedConfig(
        pg_name='test',
        log_dir=tmp_path,
        file_fmt='%(asctime)s.%(msecs)03d %(message)s',
        console_fmt='%(asctime)s.%(msecs)03d %(message)s',
        routing_mode='none',
        routing_kwargs={},
        backup_count=0,
        archive_mode=False,
        enable_hash=False,
        manifest_path=None,
        encoding='utf-8',
        diagnose=False,
        max_level='INFO',
        console=True,
        is_async=False,
        queue_size=-1,
        log_level='DEBUG',
        color_stream=False,
        module_configs={},
        color_overrides={},
        datefmt='%H:%M:%S',
    )

    pipeline = PipelineBuilder().build(config)
    file_handler, console_handler = pipeline.transport._target_handlers

    assert file_handler.formatter.datefmt == '%H:%M:%S'
    assert console_handler.formatter.datefmt == '%H:%M:%S'


def test_pipeline_builder_async(tmp_path: Path):
    config = ResolvedConfig(
        pg_name='test',
        log_dir=tmp_path,
        file_fmt='json',
        console_fmt='json',
        routing_mode='daily',
        routing_kwargs={},
        backup_count=0,
        archive_mode=False,
        enable_hash=False,
        manifest_path=None,
        encoding='utf-8',
        diagnose=True,
        max_level='INFO',
        console=False,
        is_async=True,
        queue_size=10,
        log_level='DEBUG',
        color_stream=False,
        module_configs={},
        color_overrides={},
    )

    builder = PipelineBuilder()
    pipeline = builder.build(config)
    
    assert isinstance(pipeline.transport, QueueTransport)
    
    # 1 handler: file (console=False)
    assert len(pipeline.transport._target_handlers) == 1
    assert pipeline.transport._queue.maxsize == 10
