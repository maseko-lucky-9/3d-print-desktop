"""Entry point. `python -m print_desktop` or via the py2app .app bundle."""

import asyncio
import sys
from pathlib import Path

import qasync
from PySide6.QtWidgets import QApplication

from print_desktop import logging_setup
from print_desktop.storage import settings as settings_module
from print_desktop.theme.styles import stylesheet
from print_desktop.ui.main_window import MainWindow


def _bundled_ca_path() -> Path | None:
    """Locate the homelab CA bundled at <App>.app/Contents/Resources/homelab-ca.pem
    or alongside the source tree during dev. Returns None if missing."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "homelab-ca.pem",
        Path(getattr(sys, "_MEIPASS", "")) / "homelab-ca.pem" if hasattr(sys, "_MEIPASS") else None,
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


def main() -> None:
    debug = "--debug" in sys.argv
    logging_setup.setup(debug=debug)

    settings = settings_module.load()
    ca = _bundled_ca_path()
    if ca is None and settings.ca_cert_path:
        p = Path(settings.ca_cert_path)
        if p.exists():
            ca = p

    app = QApplication(sys.argv)
    app.setApplicationName("3D Print Desktop")
    app.setOrganizationName("PrintDesktop")
    app.setStyleSheet(stylesheet())

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    win = MainWindow(settings, ca_path=ca)
    win.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
