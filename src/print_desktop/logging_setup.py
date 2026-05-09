"""Stdlib logging to ~/Library/Logs/PrintDesktop/print-desktop.log.

Per plan §17 D1: RotatingFileHandler (5 MB × 5 files), INFO default,
DEBUG via --debug flag. View in macOS Console.app.

Per plan §17 D6: install sys.excepthook to write tracebacks + show
QMessageBox for uncaught Python exceptions before Qt event loop crashes.
"""

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path

LOG_DIR = Path.home() / "Library" / "Logs" / "PrintDesktop"
LOG_PATH = LOG_DIR / "print-desktop.log"


def setup(debug: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO

    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on re-init in dev
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    if debug:
        # Also stream to stderr in debug mode
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(stream)

    # Crash reporter — catches everything that escapes Qt's event loop
    def _excepthook(exc_type, exc_value, exc_tb):
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger("crash").critical("Uncaught exception:\n%s", tb)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None,
                    "Something went wrong",
                    f"PrintDesktop hit an unexpected error.\n\n"
                    f"A crash log was written to:\n{LOG_PATH}\n\n"
                    f"Please attach this file when reporting the issue.\n\n"
                    f"{exc_type.__name__}: {exc_value}",
                )
        except Exception:
            pass
        # Still call the original hook so dev sees the traceback in stderr
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
