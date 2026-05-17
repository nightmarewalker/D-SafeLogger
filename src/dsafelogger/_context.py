"""contextvars-based context management for D-SafeLogger."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from types import MappingProxyType
from typing import Any, Generator

_log_context: contextvars.ContextVar[MappingProxyType[str, Any]] = contextvars.ContextVar(
    'dsafelogger_context', default=MappingProxyType({}),
)

# Representative mutable types for fail-fast check
_MUTABLE_TYPES = (list, dict, set, bytearray)


def get_context() -> MappingProxyType[str, Any]:
    """Return current logging context MappingProxyType."""
    return _log_context.get()


def set_context(data: MappingProxyType[str, Any]) -> contextvars.Token:
    """Set logging context and return reset token."""
    return _log_context.set(data)


def reset_context(token: contextvars.Token) -> None:
    """Reset logging context to previous state using token."""
    _log_context.reset(token)


def _snapshot_context() -> MappingProxyType[str, Any] | None:
    """
    Return the current context snapshot safely for cross-thread/async queue hand-off.
    Returns None if the context is empty. This is an O(1) operation because
    MappingProxyType is treated as shallow immutable.
    """
    ctx = _log_context.get()
    return ctx if ctx else None


@contextmanager
def contextualize(**kwargs: Any) -> Generator[None, None, None]:
    """
    Add kwargs to the logging context within a 'with' block.
    
    Raises:
        TypeError: If any of the kwargs values are of a representative mutable type
                   (list, dict, set, etc.). This enforces the fail-fast rule to
                   prevent unintentional side effects due to shallow immutability
                   of MappingProxyType when handed off across threads/tasks.
    """
    # Fail-Fast: check if mutable values are passed
    # It catches common mutables. It doesn't trace arbitrarily deep or custom objects,
    # but serves as a strong guardrail for the 99% usage.
    for k, v in kwargs.items():
        if isinstance(v, _MUTABLE_TYPES):
            raise TypeError(
                f"contextualize() value for key '{k}' "
                f"is a mutable type {type(v).__name__}. "
                f"Only immutable values (str, int, float, tuple, etc.) are allowed."
            )

    curr = _log_context.get()
    
    # Merge existing and new
    # MappingProxyType needs to be unpacked to a dict, then updated, then wrapped
    if not kwargs:
        merged = curr
    else:
        new_dict = dict(curr)
        new_dict.update(kwargs)
        merged = MappingProxyType(new_dict)
    
    token = _log_context.set(merged)
    try:
        yield
    finally:
        _log_context.reset(token)
