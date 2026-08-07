"""Entry point. `python -m print_desktop` or via the py2app .app bundle."""

import asyncio
import os
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
    or alongside the source tree during dev. Returns None if missing.

    py2app is not PyInstaller: it never sets `sys._MEIPASS` (that is a
    PyInstaller-only convention). At runtime inside a frozen bundle, py2app
    sets `sys.frozen = "macosx_app"` and the RESOURCEPATH environment
    variable to <App>.app/Contents/Resources — the directory `data_files`
    with an empty destination (as setup.py uses for this file) actually
    copies into. Deriving the path via `__file__` instead only works in dev,
    because inside the bundle `__main__.py` is relocated under
    Contents/Resources/lib/pythonX.Y/print_desktop/, three parents up from
    which is Contents/Resources/lib — not Contents/Resources.
    """
    resource_dir = os.environ.get("RESOURCEPATH")
    candidates = [
        Path(resource_dir) / "homelab-ca.pem" if resource_dir else None,
        Path(__file__).resolve().parent.parent.parent / "homelab-ca.pem",
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
