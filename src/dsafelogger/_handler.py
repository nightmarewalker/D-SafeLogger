"""Append-only file handler for D-SafeLogger."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from dsafelogger._integrity import HashWorker
from dsafelogger._purge import ArchiveWorker, PurgeWorker
from dsafelogger._routing import RoutingStrategy


class AppendOnlyFileHandler(logging.Handler):
    """Append-only file handler with routing strategy support.

    Avoids file renaming (Windows lock safety) by using stream switching.

    v23h: classified as a *required* sink (`_ds_required = True`), meaning
    file delivery must succeed for the record to count as `delivered`
    (§12.3 配送契約).  Failures are reflected in `_writer_sink_reject` /
    `_writer_policy_reject` and contribute to `_writer_partial_delivered`
    when the route has multiple required sinks.
    """

    _ds_required: bool = True

    def __init__(
        self,
        strategy: RoutingStrategy,
        backup_count: int = 0,
        archive_mode: bool = False,
        enable_hash: bool = False,
        manifest_path: str | None = None,
        encoding: str = 'utf-8',
        stream_flush_on_emit: bool = True,
    ) -> None:
        super().__init__()
        self._strategy = strategy
        self._backup_count = backup_count
        self._archive_mode = archive_mode
        self._enable_hash = enable_hash
        self._manifest_path = manifest_path
        self._encoding = encoding
        # When False the caller is responsible for periodic flush (e.g. Writer
        # batch-flush mode).  Default True preserves the existing per-emit flush.
        self._stream_flush_on_emit = stream_flush_on_emit
        self._stream: Any = None
        self._current_path: Path | None = None
        # Use parent logging.Handler.lock (created by createLock() in __init__).
        # Do NOT add a separate RLock here: emit() is called from within
        # Handler.handle() which already holds self.lock, so a second RLock
        # would be redundant on CPython and wasteful on Free-Threaded builds.
        self._open_file()

    def _open_file(self) -> None:
        """Open current log file for appending."""
        path = self._strategy.get_current_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = open(path, 'a', encoding=self._encoding)
        self._current_path = path

    def _close_stream(self) -> None:
        """Close current file stream."""
        if self._stream is not None:
            try:
                self._stream.flush()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _switch_file(self, record: logging.LogRecord) -> None:
        """Switch to next file per routing strategy."""
        old_path = self._current_path

        try:
            new_path = self._strategy.advance()
        except OverflowError:
            raise

        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_stream = open(new_path, 'a', encoding=self._encoding)
        except OSError:
            self.handleError(record)
            return

        # New stream opened successfully, close old stream and switch
        self._close_stream()
        self._current_path = new_path
        self._stream = new_stream

        # Post-switch actions
        if old_path and old_path != new_path:
            self._handle_post_switch(old_path)

    def _handle_post_switch(self, old_path: Path) -> None:
        """Handle hash/purge/archive after file switch."""
        from dsafelogger import _register_worker, _unregister_worker

        # Cyclic strategies don't need purge/archive, but completed files can still
        # be hashed before the next cycle overwrites them.
        if self._strategy.is_cyclic():
            if not self._enable_hash:
                return
        elif self._backup_count > 0:
            if self._archive_mode:
                worker = ArchiveWorker(
                    directory=old_path.parent,
                    pg_name=self._strategy._pg_name,
                    backup_count=self._backup_count,
                    switched_file=old_path,
                    enable_hash=self._enable_hash,
                    manifest_path=self._manifest_path,
                    unregister_fn=_unregister_worker,
                )
            else:
                worker = PurgeWorker(
                    directory=old_path.parent,
                    pg_name=self._strategy._pg_name,
                    backup_count=self._backup_count,
                    switched_file=old_path,
                    enable_hash=self._enable_hash,
                    manifest_path=self._manifest_path,
                    unregister_fn=_unregister_worker,
                )
            _register_worker(worker)
            worker.start()
            return

        if self._enable_hash:
            worker = HashWorker(
                file_path=old_path,
                manifest_path=Path(self._manifest_path) if self._manifest_path else None,
                unregister_fn=_unregister_worker,
            )
            _register_worker(worker)
            worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        """Write log record to file, switching if needed."""
        try:
            if self._strategy.should_switch():
                self._switch_file(record)

            msg = self.format(record) + '\n'
            if self._stream is not None:
                self._stream.write(msg)
                if self._stream_flush_on_emit:
                    self._stream.flush()

            self._strategy.on_emit()

        except Exception:
            self.handleError(record)

    def reopen(self) -> None:
        """Re-open the current log file stream after external rotation.

        Called by ReopenLogFiles() when an external log rotator (e.g. logrotate)
        has renamed the current file and created a new one at the same path.

        Only supported with NoneStrategy (routing_mode='none').  Other strategies
        manage their own file switching, so mixing external rotation with
        D-SafeLogger's own routing would corrupt the routing state.

        Raises:
            ValueError: If routing_mode is not 'none'.
        """
        from dsafelogger._routing import NoneStrategy
        self.acquire()
        try:
            if not isinstance(self._strategy, NoneStrategy):
                raise ValueError(
                    "ReopenLogFiles() is only supported with routing_mode='none'. "
                    f"Current strategy: {type(self._strategy).__name__}. "
                    "Do not mix D-SafeLogger routing with external log rotation."
                )
            self._close_stream()
            self._open_file()
        finally:
            self.release()

    def close(self) -> None:
        """Close handler and release resources."""
        self.acquire()
        try:
            self._close_stream()
        finally:
            self.release()
        super().close()

    def flush(self) -> None:
        """Flush current stream."""
        self.acquire()
        try:
            if self._stream is not None:
                try:
                    self._stream.flush()
                except Exception:
                    pass
        finally:
            self.release()
