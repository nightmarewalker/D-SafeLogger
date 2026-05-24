# Testing and Warnings

D-SafeLogger stays on the standard logging path, so pytest `caplog` and
`warnings.warn()` routing through `logging.captureWarnings(True)` continue to
work.

## Lifecycle Rule For Tests

D-SafeLogger's public lifecycle is one configure per process. `SafeShutdown()`
is a terminal API for application shutdown. It is **not** a test-between-reset
API, because after it runs `ConfigureLogger()` and `GetLogger()` intentionally
raise `RuntimeError` in the same process.

For test suites that need fresh logger configuration per test, use one of these
patterns:

- A project-local `conftest.py` fixture that resets private state for your own
test process.
- A subprocess per scenario when you need public API behavior only.

## caplog With D-SafeLogger File Output

```python
import logging

from dsafelogger import ConfigureLogger, GetLogger


def test_application_log_is_captured_by_caplog(tmp_path, caplog):
    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="PytestCaplog",
        structured=True,
        console_out=False,
    )

    logger = GetLogger("tests.caplog")

    with caplog.at_level(logging.INFO, logger="tests.caplog"):
        logger.info("caplog and file sink both receive this", extra={"case": "caplog"})

    assert "caplog and file sink both receive this" in caplog.text
    assert "caplog and file sink both receive this" in (
        tmp_path / "PytestCaplog.log"
    ).read_text(encoding="utf-8")
```

## warnings.warn Routed Through logging

```python
import logging
import warnings

from dsafelogger import ConfigureLogger


def test_warnings_are_routed_and_restored(tmp_path):
    original_showwarning = warnings.showwarning

    ConfigureLogger(
        log_path=str(tmp_path),
        pg_name="WarningsRoute",
        structured=True,
        console_out=False,
    )

    logging.captureWarnings(True)
    try:
        warnings.warn("deprecated option", DeprecationWarning, stacklevel=1)
    finally:
        logging.captureWarnings(False)

    assert warnings.showwarning is original_showwarning
    assert "deprecated option" in (tmp_path / "WarningsRoute.log").read_text(
        encoding="utf-8"
    )
```
