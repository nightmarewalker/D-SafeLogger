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

from dsafelogger import ConfigureLogger, GetLogger, RegisterLevel, SafeShutdown


def smoke_basic_logger() -> None:
    ConfigureLogger()
    logger = GetLogger("typing-smoke")
    logger.info("hello")
    logger.warning("warn")


def smoke_console_only_logger() -> None:
    ConfigureLogger(console_out="only")
    logger = GetLogger("typing-smoke-console")
    logger.info("console only")


def smoke_custom_level() -> None:
    RegisterLevel("TRACE", 5, "TRC")


def smoke_safe_shutdown() -> None:
    SafeShutdown()


def smoke_contextualize() -> None:
    logger = GetLogger("typing-smoke-context")
    with logger.contextualize(request_id="abc"):
        logger.info("hello")


def smoke_multiprocess() -> None:
    from dsafelogger import mp
    ctx = mp.ConfigureLogger()
    init_fn, init_args = mp.GetWorkerInitializer(ctx)
    _ = (init_fn, init_args)


def smoke_delivery_status() -> None:
    from dsafelogger import mp

    status: mp.DeliveryStatus = mp.GetDeliveryStatus()
    attempted: int = status["attempted"]
    accepted: int = status["accepted"]
    delivered: int = status["delivered"]
    partial_delivered: int = status["partial_delivered"]
    known_rejected: int = status["known_rejected"]
    known_dropped: int = status["known_dropped"]
    unexplained_lost: int = status["unexplained_lost"]
    writer_rejects: dict[str, int] = status["writer_reject_breakdown"]
    worker_drops: dict[str, int] = status["worker_drop_breakdown"]
    writer_drops: dict[str, int] = status["writer_drop_breakdown"]
    complete: bool = status["snapshot_complete"]
    _ = (
        attempted,
        accepted,
        delivered,
        partial_delivered,
        known_rejected,
        known_dropped,
        unexplained_lost,
        writer_rejects,
        worker_drops,
        writer_drops,
        complete,
    )
