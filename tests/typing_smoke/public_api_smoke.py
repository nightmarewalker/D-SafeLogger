"""Public API typing smoke test.

This file is NOT executed at runtime. It exists solely so that pyright
can verify the public API signatures from a user's perspective.
pytest's default collection pattern does not match this filename, so it
is excluded automatically.

The enclosing directory is intentionally named ``typing_smoke`` (not
``typing``) so that it cannot shadow the stdlib ``typing`` module when
spawn-based child processes inherit ``sys.path`` from the parent test
process.
"""
from __future__ import annotations

from dsafelogger import ConfigureLogger, GetLogger


def smoke_basic_logger() -> None:
    ConfigureLogger()
    logger = GetLogger("typing-smoke")
    logger.info("hello")
    logger.warning("warn")


def smoke_contextualize() -> None:
    logger = GetLogger("typing-smoke-context")
    with logger.contextualize(request_id="abc"):
        logger.info("hello")


def smoke_multiprocess() -> None:
    from dsafelogger import mp
    ctx = mp.ConfigureLogger()
    init_fn, init_args = mp.GetWorkerInitializer(ctx)
    _ = (init_fn, init_args)
