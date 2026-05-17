"""Async logging support and safe shutdown for D-SafeLogger."""

from __future__ import annotations

import copy
import logging
import logging.handlers
import queue
import sys
import threading
import traceback
from typing import Any

from dsafelogger import _constants
from dsafelogger._constants import QUEUE_DRAIN_TIMEOUT_SEC, WORKER_JOIN_TIMEOUT_SEC
from dsafelogger._context import _snapshot_context


class DSafeQueueHandler(logging.handlers.QueueHandler):
    """Queue handler with producer-side context and diagnostic snapshot.

    Does NOT call super().prepare() to avoid stdlib's destructive
    exc_info formatting.
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        """Snapshot context and diagnostic info on the producer thread.

        Returns a shallow copy with:
        - _ds_context: FrozenContext snapshot (MappingProxyType, O(1) reference)
        - _ds_exc_text / _ds_diag_frames: Exception snapshot (if diagnose=True)
        """
        record = copy.copy(record)

        # Context snapshot: O(1) reference to FrozenContext (MappingProxyType).
        # No dict allocation: this is the intended design for cross-thread hand-off.
        record._ds_context = _snapshot_context()  # type: ignore[attr-defined]

        # Diagnostic snapshot (if diagnose is enabled)
        if _constants._diagnose_enabled and record.exc_info and record.exc_info[1]:
            # Snapshot exception text
            record._ds_exc_text = ''.join(  # type: ignore[attr-defined]
                traceback.format_exception(*record.exc_info)
            )
            # Snapshot f_locals frames
            record._ds_diag_frames = self._snapshot_frames(record.exc_info)  # type: ignore[attr-defined]
        else:
            # Fast path: just exc_text for non-diagnose
            if record.exc_info and record.exc_info[1]:
                record._ds_exc_text = ''.join(  # type: ignore[attr-defined]
                    traceback.format_exception(*record.exc_info)
                )

        return record

    @staticmethod
    def _snapshot_frames(exc_info: tuple) -> list[dict]:
        """Snapshot f_locals from traceback frames."""
        _, _, exc_tb = exc_info
        frames: list[dict] = []
        tb = exc_tb
        while tb is not None:
            frame = tb.tb_frame
            variables: dict[str, Any] = {}
            for name, value in frame.f_locals.items():
                try:
                    variables[name] = repr(value)
                except Exception:
                    variables[name] = '<repr failed>'
            frames.append({
                'frame': f'{frame.f_code.co_filename}:{tb.tb_lineno}',
                'variables': variables,
            })
            tb = tb.tb_next
        return frames


class DSafeQueueListener(logging.handlers.QueueListener):
    """Queue listener running in empty Context.

    Prevents application-side contextualize from leaking into
    the consumer thread.
    """

    def start(self) -> None:
        """Start the listener thread in an empty context."""
        super().start()

    def stop_with_timeout(self, timeout: float) -> None:
        """Stop the listener with a drain timeout.

        Places sentinel and waits for thread to finish.
        """
        self.enqueue_sentinel()
        if self._thread is not None:  # type: ignore[attr-defined]
            self._thread.join(timeout=timeout)  # type: ignore[attr-defined]
            if self._thread.is_alive():  # type: ignore[attr-defined]
                print(
                    f'[D-SafeLogger] Warning: QueueListener did not stop '
                    f'within {timeout}s.',
                    file=sys.stderr,
                )
