# GUI Logging (Qt)

Qt applications often need two outputs at the same time:

- A live log panel for the operator.
- Durable local files for investigation after the GUI closes.

D-SafeLogger should own the durable file sink. Qt should own the GUI signal and
widget update path.

## Minimal Bridge Handler

```python
import logging

from PySide6 import QtCore


class QtLogBridge(QtCore.QObject):
    message = QtCore.Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, bridge: QtLogBridge) -> None:
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        self._bridge.message.emit(self.format(record))
```

## Using the Bridge With D-SafeLogger

```python
import logging

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

bridge = QtLogBridge()
handler = QtLogHandler(bridge)
handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

ConfigureLogger(
    log_path="./logs",
    pg_name="QtApp",
    structured=True,
    console_out=False,
)

root = logging.getLogger()
root.addHandler(handler)

try:
    logger = GetLogger("gui.main")
    logger.info("operator clicked refresh")
finally:
    root.removeHandler(handler)
    handler.close()
    SafeShutdown()
```

In a real GUI, connect `bridge.message` to a slot that appends text to a
`QPlainTextEdit` or a model used by a log view. Keep the file sink separate from
the GUI update path so a slow widget cannot block durable logging.

## What the Test Covers

The repository test for this example checks only the bridge behavior:

- `QtLogHandler` formats a `LogRecord`.
- The signal bridge receives the formatted message.
- D-SafeLogger writes an independent file sink.

It does not launch a full GUI event loop in CI.
