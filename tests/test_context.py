"""Tests for dsafelogger._context (FrozenContext / contextvars-based)."""

from __future__ import annotations

import asyncio
import threading
from types import MappingProxyType

import pytest
from dsafelogger._context import (
    _snapshot_context,
    contextualize,
    get_context,
    reset_context,
    set_context,
)


class TestFrozenContextBasic:
    """UT-FC-001 to UT-FC-006: FrozenContext Basic & Integrity"""

    def test_default_is_mapping_proxy(self):
        """UT-FC-001: Default context should be an empty MappingProxyType."""
        ctx = get_context()
        assert isinstance(ctx, MappingProxyType)
        assert len(ctx) == 0

    def test_contextualize_basic(self):
        """UT-FC-002, 003: contextualize() updates context and restores on exit."""
        with contextualize(user_id=123):
            ctx = get_context()
            assert isinstance(ctx, MappingProxyType)
            assert ctx['user_id'] == 123
        
        # After exit, it should be restored
        assert 'user_id' not in get_context()

    def test_contextualize_nested(self):
        """UT-FC-006: new contextualize() creates a new MappingProxyType."""
        with contextualize(req_id='A'):
            ctx1 = get_context()
            assert ctx1['req_id'] == 'A'
            
            with contextualize(req_id='B', user='bob'):
                ctx2 = get_context()
                assert ctx2['req_id'] == 'B'
                assert ctx2['user'] == 'bob'
                assert id(ctx1) != id(ctx2)
            
            ctx3 = get_context()
            assert ctx3['req_id'] == 'A'
            assert 'user' not in ctx3
            assert id(ctx1) == id(ctx3)

    def test_contextualize_fail_fast_mutables(self):
        """UT-FC-004: Passing mutable types should raise TypeError."""
        mutables = [
            [1, 2, 3],
            {'a': 1},
            set([1]),
            bytearray(b'abc')
        ]
        
        for m in mutables:
            with pytest.raises(TypeError, match="is a mutable type"):
                with contextualize(val=m):
                    pass
        
        # Immutable types should pass
        immutables = [
            (1, 2),
            "string",
            b"bytes",
            123,
            45.6
        ]
        for im in immutables:
            with contextualize(val=im):
                assert get_context()['val'] == im

    def test_snapshot_context_returns_none_if_empty(self):
        """UT-FC-005: _snapshot_context() should return None if empty."""
        assert _snapshot_context() is None

    def test_snapshot_context_returns_id_match(self):
        """UT-FC-005: _snapshot_context() should return the exact same object id."""
        with contextualize(uid=1):
            snap = _snapshot_context()
            assert snap is not None
            assert id(snap) == id(get_context())
            assert isinstance(snap, MappingProxyType)

    def test_manual_set_reset(self):
        """Manual set_context and reset_context with MappingProxyType."""
        token = set_context(MappingProxyType({'manual': 1}))
        try:
            assert get_context()['manual'] == 1
        finally:
            reset_context(token)
        assert 'manual' not in get_context()


class TestFrozenContextConcurrency:
    """UT-FC-007 and Thread safety."""

    def test_thread_isolation(self):
        """Context in thread A doesn't affect thread B."""
        results = {}

        def thread_worker(name, val):
            with contextualize(worker=val):
                import time
                time.sleep(0.01)
                results[name] = _snapshot_context()

        t1 = threading.Thread(target=thread_worker, args=('A', 1))
        t2 = threading.Thread(target=thread_worker, args=('B', 2))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results['A']['worker'] == 1
        assert results['B']['worker'] == 2

    @pytest.mark.asyncio
    async def test_async_task_isolation(self):
        """UT-FC-007: Context in async task A doesn't leak to task B."""
        results = {}

        async def task_a():
            with contextualize(task='A'):
                await asyncio.sleep(0.01)
                results['A'] = _snapshot_context()

        async def task_b():
            # No context
            await asyncio.sleep(0.02)
            results['B'] = _snapshot_context()

        await asyncio.gather(task_a(), task_b())
        assert results['A']['task'] == 'A'
        assert results['B'] is None
