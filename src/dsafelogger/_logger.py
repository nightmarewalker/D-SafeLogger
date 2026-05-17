"""DSafeLogger class for D-SafeLogger."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from dsafelogger._context import get_context, reset_context, set_context


class DSafeLogger(logging.Logger):
    """Extended Logger with contextualize support.

    Provides a context manager for adding key-value pairs to log output
    within a specific scope. Uses contextvars for thread/async safety.
    """

    @contextmanager
    def contextualize(self, **kwargs: object) -> Generator[None, None, None]:
        """Context manager to add key-value pairs to log output.

        Example::

            with logger.contextualize(task_id=42, worker='db'):
                logger.info('Processing started')
                # Output: ... [task_id:42 worker:db]

        Nested usage is supported; inner contexts override outer ones.
        Context is automatically cleaned up on exit.
        """
        # Delegating to the _context.py implementation
        from dsafelogger._context import contextualize as ctx_contextualize
        with ctx_contextualize(**kwargs):
            yield
