"""Main window — shell with menubar + status bar + central HomeView.

Wires async API calls (qasync) to the HomeView signals. Polls /api/jobs
every 5 s for live tab counters per plan §17 N5.
"""

import asyncio
import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from print_desktop import __version__
from print_desktop.models.print_request import JobPayload
from print_desktop.services.api_client import ApiClient, wait_for_makerworld
from print_desktop.storage.settings import Settings
from print_desktop.storage.settings import save as save_settings
from print_desktop.ui.home import HomeView
from print_desktop.ui.settings_view import SettingsView

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, ca_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"3D Print Desktop {__version__}")
        self.resize(1100, 800)
        self._settings = settings
        self._client = ApiClient(settings.backend_url, ca_path=ca_path)

        self.home = HomeView(self)
        self.settings_view = SettingsView(self)

        tabs = QTabWidget(self)
        tabs.addTab(self.home, "Jobs")
        tabs.addTab(self.settings_view, "Settings")
        self.setCentralWidget(tabs)

        self.home.submit_job.connect(self._on_submit_job)
        self.home.import_makerworld_url.connect(self._on_import_makerworld)
        self.home.feature_clicked.connect(self._on_feature_clicked)
        self.home.quote_requested.connect(self._on_quote_requested)
        self.settings_view.save_settings_requested.connect(self._on_save_settings_requested)
        self.settings_view.save_printer_requested.connect(self._on_save_printer_requested)

        self._build_menu_bar()
        self._restore_window_state()

        # Initial load + 5s poll for jobs/SKUs. Pricing context (settings +
        # printers) is loaded once at startup only, deliberately NOT on the
        # 5s poll — a live app has no concurrent editors, and re-pushing
        # server values into the Settings tab every 5s would stomp whatever
        # the user is mid-typing there. It's refreshed again after a
        # successful save instead (see _save_settings_async/_save_printer_async).
        QTimer.singleShot(0, self._refresh)
        QTimer.singleShot(0, self._load_pricing_context)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start(5000)

    # ── Menubar (§17 N2) ──────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
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
            # Previously log-only — the SKU dropdown went silently empty for
            # months because nothing surfaced this anywhere a user would see
            # it. A background 5s poll failing must not pop a modal dialog on
            # every tick (that would mean one QMessageBox every 5s while the
            # backend is down), so the status bar is the right amount of
            # "explicit" here: visible, non-blocking, self-clearing.
            log.warning("Refresh failed: %s", exc)
            self.statusBar().showMessage(f"Backend unreachable — retrying: {exc}", 6000)
            return
        self.statusBar().clearMessage()
        self.home.set_skus(skus)
        self.home.set_jobs(jobs)

    def _load_pricing_context(self) -> None:
        asyncio.ensure_future(self._load_pricing_context_async())

    async def _load_pricing_context_async(self) -> None:
        try:
            app_settings = await self._client.get_settings()
            printers = await self._client.list_printers(status="active")
        except Exception as exc:
            log.warning("Loading pricing context failed: %s", exc)
            self.statusBar().showMessage(f"Could not load pricing settings: {exc}", 6000)
            return
        self.home.set_app_settings(app_settings)
        self.home.set_printers(printers)
        self.settings_view.set_settings(app_settings)
        self.settings_view.set_printers(printers)

    def _on_quote_requested(self, seq: int, params: dict) -> None:
        asyncio.ensure_future(self._quote_async(seq, params))

    async def _quote_async(self, seq: int, params: dict) -> None:
        try:
            result = await self._client.quote(**params)
        except Exception as exc:
            self.home.set_quote_error(seq, str(exc))
            return
        self.home.set_quote_result(seq, result)

    def _on_save_settings_requested(self, fields: dict) -> None:
        asyncio.ensure_future(self._save_settings_async(fields))

    async def _save_settings_async(self, fields: dict) -> None:
        try:
            updated = await self._client.update_settings(**fields)
        except Exception as exc:
            self.settings_view.set_settings_status(f"Save failed: {exc}")
            return
        self.settings_view.set_settings_status("Saved.")
        # ManualForm needs the fresh labour_rate_per_hour for its next Save
        # payload, but must not have its own in-progress margin/failure %
        # inputs reset by this — set_app_settings only prefills once, ever.
        self.home.set_app_settings(updated)

    def _on_save_printer_requested(self, printer_id: int, fields: dict) -> None:
        asyncio.ensure_future(self._save_printer_async(printer_id, fields))

    async def _save_printer_async(self, printer_id: int, fields: dict) -> None:
        try:
            await self._client.update_printer(printer_id, **fields)
        except Exception as exc:
            self.settings_view.set_printers_status(f"Save failed: {exc}")
            return
        try:
            printers = await self._client.list_printers(status="active")
        except Exception as exc:
            self.settings_view.set_printers_status(f"Saved, but refresh failed: {exc}")
            return
        self.settings_view.set_printers(printers)
        self.settings_view.set_printers_status("Saved.")
        self.home.set_printers(printers)

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
            QMessageBox.critical(self, "MakerWorld import failed", str(exc))
            return
        if result.status == "success":
            QMessageBox.information(
                self,
                "Imported",
                f"Model added to the catalogue (model_id={result.model_id}). "
                "Open it in BambuStudio to slice, then come back to enter cost details.",
            )
        else:
            QMessageBox.warning(self, "Import failed", result.error_message or "Unknown error")

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
