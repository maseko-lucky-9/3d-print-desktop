"""Main window — shell with menubar + status bar + central HomeView.

Wires async API calls (qasync) to the HomeView signals. Polls /api/jobs
every 5 s for live tab counters per plan §17 N5.
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from print_desktop import __version__
from print_desktop.models.print_request import JobPayload, Printer
from print_desktop.services.api_client import ApiClient, wait_for_makerworld
from print_desktop.services.drift import build_local_recompute, find_drift
from print_desktop.services.offline import build_offline_quote
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
        # Retained purely so _detect_drift can look a printer's rates up by
        # id without a network round trip. Refreshed on every 5s poll tick
        # (_refresh_pricing_cache_quietly), not just at startup — a printer
        # edited from another LAN client mid-session (the backend is
        # intentionally no-auth and shared) would otherwise leave this
        # permanently stale, and _detect_drift would then report false
        # "drift" against a price that changed for a real reason, not a
        # formula bug.
        self._printers: list[Printer] = []

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

        # Initial load + 5s poll for jobs/SKUs. _refresh_async's poll tick
        # ALSO quietly re-fetches settings/printers to keep self._printers
        # and the drift/offline rate cache fresh (see
        # _refresh_pricing_cache_quietly) — but never pushes those into the
        # Settings tab or ManualForm's editable widgets on that cadence,
        # since a live app has no concurrent editors and re-pushing server
        # values into those inputs every 5s would stomp whatever the user is
        # mid-typing there. The widget-facing push happens once at startup
        # (_load_pricing_context) and again after a successful save (see
        # _save_settings_async/_save_printer_async).
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
        self._update_sku_cache(skus)
        await self._refresh_pricing_cache_quietly()
        save_settings(self._settings)  # one write per tick, not one per helper

    async def _refresh_pricing_cache_quietly(self) -> None:
        """Keeps self._printers and the cached settings rates fresh on the
        existing 5s poll tick — WITHOUT pushing into SettingsView/ManualForm's
        editable widgets, which is what _load_pricing_context_async is for
        and why that one stays startup/save-triggered only. Skipping this
        would leave _detect_drift comparing against whatever printer prices
        were true when the app launched: another LAN client editing a
        printer's price mid-session (the backend is intentionally no-auth
        and shared) would then make every subsequent quote against that
        printer look like formula drift, when nothing is actually wrong."""
        try:
            app_settings = await self._client.get_settings()
            printers = await self._client.list_printers(status="active")
        except Exception as exc:
            log.debug("Quiet pricing-cache refresh failed: %s", exc)
            return
        self._printers = printers
        self._update_pricing_cache(app_settings, printers)

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
        self._printers = printers
        self.home.set_app_settings(app_settings)
        self.home.set_printers(printers)
        self.settings_view.set_settings(app_settings)
        self.settings_view.set_printers(printers)
        self._update_pricing_cache(app_settings, printers)
        save_settings(self._settings)

    # ── Offline cache (Phase 6 of the costing-engine plan) ─────────────────
    #
    # Pure mutators of self._settings — never touch disk themselves. Every
    # call site persists once, explicitly, after whichever of these it
    # calls, so a tick that updates both SKUs and pricing context (the 5s
    # poll) writes the TOML file once, not twice. Read only by
    # _try_offline_quote/_detect_drift below; never used to prefill a
    # Settings-tab or ManualForm input (those come from the live server
    # response every time one succeeds).

    def _update_pricing_cache(self, s, printers: list[Printer]) -> None:
        self._settings.cached_pricing_mode = s.pricing_mode
        self._settings.cached_default_margin_pct = s.default_margin_pct
        self._settings.cached_vat_pct = s.vat_pct
        self._settings.cached_labour_rate_per_hour = s.labour_rate_per_hour
        self._settings.cached_electricity_tariff_per_kwh = s.electricity_tariff_per_kwh
        self._settings.cached_default_failure_pct = s.default_failure_pct
        self._update_printer_cache(printers)  # also stamps cached_at

    def _update_printer_cache(self, printers: list[Printer]) -> None:
        self._settings.cached_printers = [
            {
                "id": p.id,
                "name": p.name,
                "power_watts_default": p.power_watts_default,
                "purchase_price": p.purchase_price,
                "expected_life_hours": p.expected_life_hours,
            }
            for p in printers
        ]
        self._settings.cached_at = datetime.now(UTC).isoformat()

    def _update_sku_cache(self, skus) -> None:
        self._settings.cached_skus = [
            {"id": s.id, "name": s.name, "color": s.color, "cost_per_gram": s.cost_per_gram}
            for s in skus
        ]
        # cached_at is the pricing-context timestamp, not a per-field one —
        # SKU prices move independently of settings/printers, but a single
        # "rates as of <date>" badge is what the plan actually asks for, and
        # a SKU refresh alone (no settings/printers change) still counts as
        # "we successfully talked to the server just now".
        self._settings.cached_at = datetime.now(UTC).isoformat()

    def _try_offline_quote(self, params: dict):
        if not self._settings.cached_at:
            return None  # never successfully cached anything to fall back to
        return build_offline_quote(
            params,
            self._settings.cached_skus,
            self._settings.cached_printers,
            self._settings.cached_electricity_tariff_per_kwh,
            self._settings.cached_labour_rate_per_hour,
            self._settings.cached_pricing_mode,
            self._settings.cached_vat_pct,
        )

    def _detect_drift(self, result, params: dict) -> str | None:
        printer = next((p for p in self._printers if p.id == params["printer_id"]), None)
        if printer is None:
            return None  # can't recompute depreciation without the printer's rates
        local = build_local_recompute(
            result,
            params,
            printer,
            self._settings.cached_electricity_tariff_per_kwh,
            self._settings.cached_labour_rate_per_hour,
        )
        if local is None:
            return None
        drift = find_drift(result, local)
        if drift:
            log.warning("Local/server quote drift detected: %s", drift)
        return drift

    def _on_quote_requested(self, seq: int, params: dict) -> None:
        asyncio.ensure_future(self._quote_async(seq, params))

    async def _quote_async(self, seq: int, params: dict) -> None:
        try:
            result = await self._client.quote(**params)
        except Exception as exc:
            offline = self._try_offline_quote(params)
            if offline is not None:
                self.home.set_offline_quote_result(seq, offline, self._settings.cached_at)
            else:
                self.home.set_quote_error(seq, str(exc))
            return
        drift = self._detect_drift(result, params)
        self.home.set_quote_result(seq, result, drift)

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
        self._update_pricing_cache(updated, self._printers)
        save_settings(self._settings)

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
        self._printers = printers
        self.settings_view.set_printers(printers)
        self.settings_view.set_printers_status("Saved.")
        self.home.set_printers(printers)
        self._update_printer_cache(printers)
        save_settings(self._settings)

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
