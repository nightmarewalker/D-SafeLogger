"""Pipeline abstraction for D-SafeLogger.

Coordinates Capture, Transport, and Sink layers.
reopen_file_sinks() supports external log rotation coexistence.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from dsafelogger._transport import Transport, TransportFactory


class FormatterConfigDict(TypedDict, total=False):
    fmt: str
    datefmt: str


@dataclass(frozen=True)
class ResolvedConfig:
    """Resolved configuration holding 3-layer merged parameters."""
    pg_name: str
    log_dir: Path
    file_fmt: str | FormatterConfigDict | logging.Formatter
    console_fmt: str | FormatterConfigDict | logging.Formatter
    routing_mode: str
    routing_kwargs: dict
    backup_count: int
    archive_mode: bool
    enable_hash: bool
    manifest_path: Path | None
    encoding: str
    diagnose: bool
    max_level: str
    console: bool
    is_async: bool
    queue_size: int
    log_level: str
    color_stream: bool
    module_configs: dict[str, dict]
    color_overrides: dict[str, str]


class Pipeline:
    """Active logging pipeline encompassing Transport and Root attach points."""

    def __init__(
        self,
        transport: Transport,
        module_transports: dict[str, Transport],
    ) -> None:
        self.transport = transport
        self.module_transports = module_transports

    def start(self) -> None:
        """Start the pipeline (listener threads)."""
        self.transport.start()
        for t in self.module_transports.values():
            t.start()

    def stop(self, timeout: float | None = None) -> None:
        """Stop the pipeline, joining workers and flushing output."""
        self.transport.stop(timeout)
        for t in self.module_transports.values():
            t.stop(timeout)

    def get_root_handler(self) -> logging.Handler:
        """Return the root handler to be attached to loggers."""
        return self.transport.get_root_handler()

    def get_module_handler(self, mod_name: str) -> logging.Handler | None:
        """Return the handler for a named module, or None if not configured."""
        t = self.module_transports.get(mod_name)
        return t.get_root_handler() if t is not None else None

    def reopen_file_sinks(self) -> int:
        """Re-open all writer-side file sinks after external log rotation.

        Collects AppendOnlyFileHandler instances from root and module transports,
        de-duplicates by object id, then calls reopen() on each one.

        Each handler's reopen() raises ValueError if routing_mode != 'none'.

        Returns:
            Number of file sinks successfully reopened.
        """
        seen: set[int] = set()
        count = 0
        for h in self._collect_file_handlers():
            hid = id(h)
            if hid not in seen:
                seen.add(hid)
                if hasattr(h, 'reopen'):
                    h.reopen()  # may raise ValueError for non-NoneStrategy
                    count += 1
        return count

    def _collect_file_handlers(self) -> list[logging.Handler]:
        """Collect writer-side handlers from all transports."""
        handlers: list[logging.Handler] = []
        handlers.extend(self.transport.get_sink_handlers())
        for t in self.module_transports.values():
            handlers.extend(t.get_sink_handlers())
        return handlers


class PipelineBuilder:
    """Builder for constructing a Pipeline from a ResolvedConfig."""

    def build(self, config: ResolvedConfig) -> Pipeline:
        """Assemble a Pipeline from configuration."""
        from dsafelogger._formatter import (
            DiagnosticFormatter,
            DiagnosticStructuredFormatter,
            DSafeFormatter,
            StructuredFormatter,
        )
        from dsafelogger._handler import AppendOnlyFileHandler
        from dsafelogger._routing import create_strategy

        # 1. Root strategy
        strategy = create_strategy(
            routing_mode=config.routing_mode,
            base_dir=config.log_dir,
            pg_name=config.pg_name,
            **config.routing_kwargs,
        )

        # 2. Root sink handlers
        handlers: list[logging.Handler] = []

        file_handler = AppendOnlyFileHandler(
            strategy=strategy,
            backup_count=config.backup_count,
            archive_mode=config.archive_mode,
            enable_hash=config.enable_hash,
            manifest_path=str(config.manifest_path) if config.manifest_path else None,
            encoding=config.encoding,
        )

        # Formatter for file sink
        if isinstance(config.file_fmt, logging.Formatter):
            file_formatter = config.file_fmt
        else:
            file_fmt_val = self._parse_fmt(config.file_fmt)
            if file_fmt_val.get('fmt') == 'json':
                file_formatter = (
                    DiagnosticStructuredFormatter() if config.diagnose else StructuredFormatter()
                )
            else:
                file_formatter = (
                    DiagnosticFormatter(**file_fmt_val) if config.diagnose else DSafeFormatter(**file_fmt_val)
                )

        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

        # Console handler
        if config.console:
            from dsafelogger._color import ColorStreamHandler
            console_handler = ColorStreamHandler(
                stream=sys.stderr,
                color_enabled=config.color_stream,
                color_overrides=config.color_overrides if config.color_overrides else None,
            )
            if isinstance(config.console_fmt, logging.Formatter):
                console_formatter = config.console_fmt
            else:
                console_fmt_val = self._parse_fmt(config.console_fmt)
                if console_fmt_val.get('fmt') == 'json':
                    console_formatter = (
                        DiagnosticStructuredFormatter() if config.diagnose else StructuredFormatter()
                    )
                else:
                    console_formatter = (
                        DiagnosticFormatter(**console_fmt_val) if config.diagnose else DSafeFormatter(**console_fmt_val)
                    )
            console_handler.setFormatter(console_formatter)
            handlers.append(console_handler)

        for h in handlers:
            h.setLevel(logging.NOTSET)

        # 3. Module transports
        module_transports: dict[str, Transport] = {}
        for mod_name, mod_conf in config.module_configs.items():
            mod_path = mod_conf.get('path')
            if mod_path:
                mod_path_str = str(mod_path)
                if os.sep not in mod_path_str and '/' not in mod_path_str:
                    mod_full_path = config.log_dir / mod_path_str
                else:
                    mod_full_path = Path(mod_path_str)

                mod_routing = mod_conf.get('routing_mode', 'none')
                mod_strategy = create_strategy(
                    routing_mode=mod_routing,
                    base_dir=mod_full_path.parent,
                    pg_name=mod_full_path.stem,
                    interval=mod_conf.get('interval', config.routing_kwargs.get('interval', 10)),
                    max_bytes=mod_conf.get('max_bytes', config.routing_kwargs.get('max_bytes', 0)),
                    max_lines=mod_conf.get('max_lines', config.routing_kwargs.get('max_lines', 0)),
                    max_count=mod_conf.get('max_count', config.routing_kwargs.get('max_count')),
                    suffix_digits=mod_conf.get('suffix_digits', config.routing_kwargs.get('suffix_digits', 3)),
                )

                mod_handler = AppendOnlyFileHandler(
                    strategy=mod_strategy,
                    backup_count=mod_conf.get('backup_count', config.backup_count),
                    archive_mode=mod_conf.get('archive_mode', config.archive_mode),
                    enable_hash=config.enable_hash,
                    manifest_path=str(config.manifest_path) if config.manifest_path else None,
                )
                mod_handler.setFormatter(file_formatter)
                mod_handler.setLevel(logging.NOTSET)

                mod_transport = TransportFactory.create(
                    is_async=config.is_async,
                    handlers=[mod_handler],
                    queue_size=config.queue_size,
                )
                module_transports[mod_name] = mod_transport

        # 4. Root transport
        transport = TransportFactory.create(
            is_async=config.is_async,
            handlers=handlers,
            queue_size=config.queue_size,
        )

        return Pipeline(transport, module_transports)

    @staticmethod
    def _parse_fmt(fmt_val: str | FormatterConfigDict) -> dict:
        if isinstance(fmt_val, str):
            if fmt_val.lower() == 'json':
                return {'fmt': 'json'}
            return {'fmt': fmt_val}
        return dict(fmt_val)
