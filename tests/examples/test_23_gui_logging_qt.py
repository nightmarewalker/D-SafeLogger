"""Runnable bridge test for examples/23_gui_logging_qt.md."""

from __future__ import annotations

import logging
import os

import pytest

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_qt_log_handler_bridge_and_file_sink(tmp_path, clean_env):
    qtcore = pytest.importorskip("PySide6.QtCore")

    class QtLogBridge(qtcore.QObject):
        message = qtcore.Signal(str)

    class QtLogHandler(logging.Handler):
        def __init__(self, bridge: QtLogBridge) -> None:
            super().__init__()
            self._bridge = bridge

        def emit(self, record: logging.LogRecord) -> None:
            self._bridge.message.emit(self.format(record))

    captured: list[str] = []
    bridge = QtLogBridge()
    bridge.message.connect(captured.append)

    handler = QtLogHandler(bridge)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    ConfigureLogger(
        log_path=str(tmp_path),
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
        if handler in root.handlers:
            root.removeHandler(handler)
        handler.close()
        SafeShutdown()

    assert captured == ["INFO operator clicked refresh"]
    log_path = tmp_path / "QtApp.log"
    assert log_path.exists()
    assert "operator clicked refresh" in log_path.read_text(encoding="utf-8")
