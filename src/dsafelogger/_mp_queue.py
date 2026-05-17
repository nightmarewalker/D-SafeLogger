"""Multiprocess Queue with cross-platform qsize() support (v23h).

`multiprocessing.Queue.qsize()` raises NotImplementedError on platforms
whose underlying semaphore lacks `sem_getvalue(3)` (notably macOS, but
potentially other minor OSes).  TrackedQueue probes this support once
at construction time and falls back to a `multiprocessing.Value` counter
when the native call is unavailable.

Design:
    - Linux / Windows: native qsize() is used. Zero per-put/get overhead.
    - macOS / unsupported: Value counter is updated on every put/get.
      qsize() returns the (approximate) tracked count.

The detection uses an EAFP-style probe (calling qsize() and catching
NotImplementedError) — explicit OS detection is intentionally avoided
so future or minor platforms behave correctly without code changes.
"""
from __future__ import annotations

import ctypes
from multiprocessing.queues import Queue as _MPQueueBase
from typing import Any


class TrackedQueue(_MPQueueBase):
    """multiprocessing.Queue subclass that guarantees a working qsize().

    Construction probes the native implementation once.  After that:
    - native supported → native qsize() is forwarded (no extra cost)
    - native unsupported → an internal Value counter is used

    The detected mode and counter are pickled to child processes so all
    workers share the same view of the queue depth.
    """

    def __init__(self, maxsize: int = 0, *, ctx: Any) -> None:
        super().__init__(maxsize, ctx=ctx)
        try:
            super().qsize()
            self._native_qsize_supported: bool = True
            self._tracked_count: Any = None
        except NotImplementedError:
            self._native_qsize_supported = False
            self._tracked_count = ctx.Value(ctypes.c_long, 0)

    def __getstate__(self) -> tuple:
        return super().__getstate__() + (
            self._native_qsize_supported,
            self._tracked_count,
        )

    def __setstate__(self, state: tuple) -> None:
        super().__setstate__(state[:-2])
        self._native_qsize_supported = state[-2]
        self._tracked_count = state[-1]

    def put(self, obj: Any, block: bool = True, timeout: float | None = None) -> None:
        super().put(obj, block=block, timeout=timeout)
        if self._tracked_count is not None:
            with self._tracked_count.get_lock():
                self._tracked_count.value += 1

    def put_nowait(self, obj: Any) -> None:
        super().put_nowait(obj)
        if self._tracked_count is not None:
            with self._tracked_count.get_lock():
                self._tracked_count.value += 1

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        result = super().get(block=block, timeout=timeout)
        if self._tracked_count is not None:
            with self._tracked_count.get_lock():
                if self._tracked_count.value > 0:
                    self._tracked_count.value -= 1
        return result

    def get_nowait(self) -> Any:
        result = super().get_nowait()
        if self._tracked_count is not None:
            with self._tracked_count.get_lock():
                if self._tracked_count.value > 0:
                    self._tracked_count.value -= 1
        return result

    def qsize(self) -> int:
        if self._native_qsize_supported:
            return super().qsize()
        return self._tracked_count.value

    def empty(self) -> bool:
        if self._native_qsize_supported:
            return super().empty()
        return self._tracked_count.value == 0
