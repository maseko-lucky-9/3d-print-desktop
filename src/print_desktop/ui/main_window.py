"""Main window — shell with menubar + status bar + central HomeView.

Wires async API calls (qasync) to the HomeView signals. Polls /api/jobs
every 5 s for live tab counters per plan §17 N5.
"""

import asyncio
import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QInputDialog, QMainWindow, QMessageBox

from print_desktop import __version__
from print_desktop.models.print_request import JobPayload
from print_desktop.services.api_client import ApiClient, wait_for_makerworld
from print_desktop.storage.settings import Settings
from print_desktop.storage.settings import save as save_settings
from print_desktop.ui.home import HomeView

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, ca_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"3D Print Desktop {__version__}")
        self.resize(1100, 800)
        self._settings = settings
        self._client = ApiClient(
            settings.backend_url,
            ca_path=ca_path,
            makerworld_session_cookie=settings.makerworld_session_cookie,
        )

        self.home = HomeView(settings, self)
        self.setCentralWidget(self.home)

        self.home.submit_job.connect(self._on_submit_job)
        self.home.import_makerworld_url.connect(self._on_import_makerworld)
        self.home.feature_clicked.connect(self._on_feature_clicked)

        self._build_menu_bar()
        self._restore_window_state()

        # Initial load + 5s poll
        QTimer.singleShot(0, self._refresh)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start(5000)

    # ── Menubar (§17 N2) ──────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("File")

        cookie_act = QAction("MakerWorld cookie…", self)
        cookie_act.triggered.connect(self._on_set_cookie)
        file_menu.addAction(cookie_act)

        file_menu.addSeparator()

        quit_act = QAction("Quit", self)
        quit_act.setShortcut(QKeySequence.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = menu.addMenu("Help")
        about_act = QAction("About 3D Print Desktop", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About 3D Print Desktop",
            f"<b>3D Print Desktop {__version__}</b><br>"
            "Native macOS client for the print-calc backend.<br><br>"
            "Built with PySide6.<br>"
            "Source: github.com/maseko-lucky-9/3d-print-desktop",
        )

    def _on_set_cookie(self) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self,
            "MakerWorld session cookie",
            "Paste your makerworld.com Cookie header",
            self._settings.makerworld_session_cookie,
        )
        if not ok:
            return
        self._settings.makerworld_session_cookie = text.strip()
        save_settings(self._settings)
        self._client.set_makerworld_cookie(self._settings.makerworld_session_cookie)
        QMessageBox.information(self, "MakerWorld cookie", "Cookie saved.")

    # ── Window state restoration (§17 N5) ──────────────────────────────────

    def _restore_window_state(self) -> None:
        qs = QSettings("PrintDesktop", "Window")
        geo = qs.value("geometry")
        if isinstance(geo, (bytes, bytearray, QByteArray)):
            self.restoreGeometry(geo)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        qs = QSettings("PrintDesktop", "Window")
        qs.setValue("geometry", self.saveGeometry())
        # Persist any settings updates made during the session
        save_settings(self._settings)
        # Schedule client close on the asyncio loop
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._client.aclose())
        except Exception:
            pass
        super().closeEvent(event)

    # ── API plumbing (qasync-driven) ───────────────────────────────────────

    def _refresh(self) -> None:
        asyncio.ensure_future(self._refresh_async())

    async def _refresh_async(self) -> None:
        try:
            skus = await self._client.list_filament_skus()
            jobs = await self._client.list_jobs()
        except Exception as exc:
            log.warning("Refresh failed: %s", exc)
            return
        self.home.set_skus(skus)
        self.home.set_jobs(jobs)

    def _on_submit_job(self, payload: JobPayload, send_to_printer: bool) -> None:
        asyncio.ensure_future(self._submit_async(payload, send_to_printer))

    async def _submit_async(self, payload: JobPayload, send_to_printer: bool) -> None:
        try:
            job = await self._client.create_job(payload)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        if send_to_printer:
            try:
                await self._client.send_to_printer(job.id)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Saved, but send-to-printer failed",
                    f"The job was created (ID {job.id}) but the printer rejected it:\n\n{exc}",
                )

        await self._refresh_async()

    def _on_import_makerworld(self, url: str) -> None:
        asyncio.ensure_future(self._import_async(url))

    async def _import_async(self, url: str) -> None:
        try:
            imp = await self._client.import_makerworld(url)
            result = await wait_for_makerworld(self._client, imp.id, timeout_seconds=60)
        except Exception as exc:
            message = str(exc)
            if self._settings.makerworld_session_cookie:
                message += (
                    "\n\nYour MakerWorld cookie may have expired. "
                    "Re-copy it via File > MakerWorld cookie..."
                )
            QMessageBox.critical(self, "MakerWorld import failed", message)
            return
        if result.status == "success":
            QMessageBox.information(
                self,
                "Imported",
                f"Model added to the catalogue (model_id={result.model_id}). "
                "Open it in BambuStudio to slice, then come back to enter cost details.",
            )
        else:
            message = result.error_message or "Unknown error"
            if self._settings.makerworld_session_cookie:
                message += (
                    "\n\nYour MakerWorld cookie may have expired. "
                    "Re-copy it via File > MakerWorld cookie..."
                )
            QMessageBox.warning(self, "Import failed", message)

    def _on_feature_clicked(self, slug: str) -> None:
        if slug == "makerworld":
            self.home.hero.url_input.setFocus()
        elif slug == "history":
            self.home.tabs._on_click("printed")  # show printed tab
        elif slug == "send_to_printer":
            QMessageBox.information(
                self,
                "Send to Printer",
                "Fill the form below and click Save & Send to Printer.",
            )
