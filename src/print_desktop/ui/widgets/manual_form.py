"""Manual cost-entry form — the heart of Option E (§21).

User picks a filament SKU and a printer, types grams/hours read off
BambuStudio GUI's preview pane, and the cost panel to the right updates from
a debounced `POST /api/quote` round trip — every price line is server-computed
(§Phase 3/4/5 of the costing-engine plan), never recomputed locally. The old
free-form "no SKU, enter price manually" escape hatch is gone: the engine
always prices off a real SKU's FIFO/weighted-average cost and a real
printer's purchase price / expected life hours, never a client-guessed rate.

Phase 6 adds two more states MainWindow can push in: an OFFLINE quote (the
server is unreachable but a cached rate context lets services/cost.py
compute the same breakdown locally — informational only, Save stays
disabled) and a DRIFT warning (the server answered, but MainWindow's own
local recomputation of the same inputs disagreed with it by more than a
cent — Save stays enabled, since the numbers on screen are still the
server's authoritative ones; the badge is a signal to a human, not a block).
"""

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from print_desktop.models.print_request import (
    AppSettings,
    FilamentSku,
    JobPayload,
    Printer,
    QuoteResult,
)
from print_desktop.services.cost import QuoteBreakdown

QUOTE_DEBOUNCE_MS = 400


def _format_cached_at(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %H:%M")
    except ValueError:
        return iso


class ManualForm(QWidget):
    """Form widget — emits payload_ready(JobPayload) on Save click and
    quote_requested(dict) whenever the debounced quote inputs change."""

    payload_ready = Signal(object)  # JobPayload
    quote_requested = Signal(int, dict)  # seq, kwargs for ApiClient.quote()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._skus: list[FilamentSku] = []
        self._printers: list[Printer] = []
        self._app_settings: AppSettings | None = None
        self._app_settings_applied = False
        self._last_quote: QuoteResult | None = None
        # The quote response doesn't echo labour_rate_per_hour (only the
        # labour_cost it produced), but _validate_costs on save recomputes
        # labour_cost from labour_minutes*labour_rate and checks it against
        # direct_cost — so whatever labour_rate accompanies a save MUST be
        # the rate this specific quote was actually priced with, not
        # whatever self._app_settings has evolved into since (a settings-tab
        # save updates self._app_settings without invalidating an on-screen
        # quote, by design — see set_app_settings). Frozen at fire time in
        # _fire_quote, applied alongside the response in set_quote_result,
        # gated by the same seq check as everything else about that quote.
        self._last_quote_labour_rate: float | None = None
        self._pending_labour_rate: float | None = None
        # Debouncing does not stop two requests from both being in flight at
        # once (change -> fire A -> change again before A resolves -> fire
        # B). Without this, a slow A arriving after a fast B would overwrite
        # B's fresher numbers on screen — a stale price silently replacing a
        # correct one right before Save. Every response carries the seq it
        # was requested with; only the most recent one is ever applied.
        self._quote_seq = 0
        self._build_ui()
        self._connect_change_signals()
        self._update_save_enabled()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setSpacing(24)

        # Left column — input form
        form_widget = QWidget(self)
        form = QFormLayout(form_widget)
        form.setLabelAlignment(form.labelAlignment())
        form.setSpacing(10)

        self.sku_combo = QComboBox(self)
        self.sku_combo.addItem("(select a filament SKU)", userData=None)

        self.printer_combo = QComboBox(self)
        self.printer_combo.addItem("(select a printer)", userData=None)

        self.grams_input = QDoubleSpinBox(self)
        self.grams_input.setRange(0, 100_000)
        self.grams_input.setSuffix(" g")
        self.grams_input.setDecimals(2)
        self.grams_input.setValue(0.0)

        self.hours_input = QDoubleSpinBox(self)
        self.hours_input.setRange(0, 1000)
        self.hours_input.setSuffix(" h")
        self.hours_input.setDecimals(2)
        self.hours_input.setValue(0.0)

        self.power_input = QDoubleSpinBox(self)
        self.power_input.setRange(0, 10_000)
        self.power_input.setSuffix(" W")
        self.power_input.setDecimals(0)
        self.power_input.setValue(0.0)

        self.labour_minutes_input = QDoubleSpinBox(self)
        self.labour_minutes_input.setRange(0, 100_000)
        self.labour_minutes_input.setSuffix(" min")
        self.labour_minutes_input.setDecimals(0)
        self.labour_minutes_input.setValue(0.0)

        self.consumables_input = QDoubleSpinBox(self)
        self.consumables_input.setRange(0, 100_000)
        self.consumables_input.setPrefix("R ")
        self.consumables_input.setDecimals(2)
        self.consumables_input.setValue(0.0)

        self.overhead_input = QDoubleSpinBox(self)
        self.overhead_input.setRange(0, 100_000)
        self.overhead_input.setPrefix("R ")
        self.overhead_input.setDecimals(2)
        self.overhead_input.setValue(0.0)

        self.failure_pct_input = QDoubleSpinBox(self)
        self.failure_pct_input.setRange(0, 1000)
        self.failure_pct_input.setSuffix(" %")
        self.failure_pct_input.setDecimals(2)
        self.failure_pct_input.setValue(0.0)

        self.margin_input = QDoubleSpinBox(self)
        self.margin_input.setRange(0, 1000)
        self.margin_input.setSuffix(" %")
        self.margin_input.setDecimals(2)
        self.margin_input.setValue(0.0)

        self.notes_input = QPlainTextEdit(self)
        self.notes_input.setPlaceholderText("Notes (optional)")
        self.notes_input.setFixedHeight(60)

        form.addRow("Filament SKU", self.sku_combo)
        form.addRow("Printer", self.printer_combo)
        form.addRow("Grams used", self.grams_input)
        form.addRow("Print hours", self.hours_input)
        form.addRow("Printer power", self.power_input)
        form.addRow("Labour time", self.labour_minutes_input)
        form.addRow("Consumables", self.consumables_input)
        form.addRow("Overhead", self.overhead_input)
        form.addRow("Failure allowance", self.failure_pct_input)
        form.addRow("Profit margin", self.margin_input)
        form.addRow("Notes", self.notes_input)

        outer.addWidget(form_widget, stretch=3)

        # Right column — live cost panel + Save CTA
        panel = QVBoxLayout()
        panel.setSpacing(8)

        heading = QLabel("Cost breakdown", self)
        heading.setProperty("heading", True)
        panel.addWidget(heading)

        self.quote_error_label = QLabel("", self)
        self.quote_error_label.setProperty("error", True)
        self.quote_error_label.setWordWrap(True)
        panel.addWidget(self.quote_error_label)

        # Offline / drift badge (Phase 6) — mutually exclusive with each
        # other and with quote_error_label (a hard error means neither an
        # offline fallback nor a server response exists to compare/show).
        self.quote_status_label = QLabel("", self)
        self.quote_status_label.setProperty("muted", True)
        self.quote_status_label.setWordWrap(True)
        panel.addWidget(self.quote_status_label)

        self._cost_labels: dict[str, QLabel] = {}
        for key, label in [
            ("filament_cost", "Filament cost"),
            ("electricity_cost", "Electricity"),
            ("printer_usage_cost", "Printer usage"),
            ("labour_cost", "Labour"),
            ("direct_cost", "Direct cost"),
            ("failure_allowance", "Failure allowance"),
            ("true_cost", "True cost"),
            ("profit", "Profit"),
            ("price_ex_vat", "Selling price (ex VAT)"),
            ("vat_amount", "VAT"),
            ("price_incl_vat", "Price incl. VAT"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label, self)
            lbl.setProperty("muted", True)
            value = QLabel("R 0.00", self)
            self._cost_labels[key] = value
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(value)
            panel.addLayout(row)

        panel.addStretch(1)

        self.save_btn = QPushButton("Save & Send to Printer", self)
        self.save_btn.setProperty("primary", True)
        self.save_btn.setMinimumHeight(40)
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.style().unpolish(self.save_btn)
        self.save_btn.style().polish(self.save_btn)
        panel.addWidget(self.save_btn)

        self.draft_btn = QPushButton("Save as draft", self)
        self.draft_btn.setMinimumHeight(36)
        self.draft_btn.clicked.connect(self._on_save_draft)
        panel.addWidget(self.draft_btn)

        panel_widget = QWidget(self)
        panel_widget.setLayout(panel)
        outer.addWidget(panel_widget, stretch=2)

        # Debounce: restart on every relevant change, fire once input settles.
        self._quote_timer = QTimer(self)
        self._quote_timer.setSingleShot(True)
        self._quote_timer.setInterval(QUOTE_DEBOUNCE_MS)
        self._quote_timer.timeout.connect(self._fire_quote)

    def _connect_change_signals(self) -> None:
        for w in (
            self.grams_input, self.hours_input, self.power_input,
            self.labour_minutes_input, self.consumables_input,
            self.overhead_input, self.failure_pct_input, self.margin_input,
        ):
            w.valueChanged.connect(self._schedule_quote)
        self.sku_combo.currentIndexChanged.connect(self._schedule_quote)
        self.printer_combo.currentIndexChanged.connect(self._on_printer_changed)

    # ── Public API ───────────────────────────────────────────────────────────

    def set_skus(self, skus: list[FilamentSku]) -> None:
        self._skus = skus
        current = self.sku_combo.currentData()
        self.sku_combo.blockSignals(True)
        self.sku_combo.clear()
        self.sku_combo.addItem("(select a filament SKU)", userData=None)
        for sku in skus:
            label = f"{sku.name}"
            if sku.color:
                label += f" — {sku.color}"
            # Available grams, not on-hand: filament already reserved for a
            # queued job cannot be promised to this one.
            label += f"  ({sku.grams_remaining:.0f}g free)"
            self.sku_combo.addItem(label, userData=sku.id)
        idx = self.sku_combo.findData(current) if current is not None else -1
        self.sku_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.sku_combo.blockSignals(False)
        # Signals were blocked for the rebuild itself, so if the previously
        # selected SKU is no longer in the new list (archived/deleted — the
        # backend is LAN-shared and no-auth, so another client can do this
        # mid-session), the combo silently falls back to the placeholder
        # with no currentIndexChanged firing. Left alone, _last_quote would
        # keep referencing a SKU that's no longer selected, and Save would
        # stay enabled for a payload with filament_sku_id=None.
        if self.sku_combo.currentData() != current:
            self._schedule_quote()

    def set_printers(self, printers: list[Printer]) -> None:
        self._printers = printers
        current = self.printer_combo.currentData()
        self.printer_combo.blockSignals(True)
        self.printer_combo.clear()
        self.printer_combo.addItem("(select a printer)", userData=None)
        for p in printers:
            self.printer_combo.addItem(p.name, userData=p.id)
        idx = self.printer_combo.findData(current) if current is not None else -1
        self.printer_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.printer_combo.blockSignals(False)
        # Same reasoning as set_skus above — route through _on_printer_changed
        # (not just _schedule_quote) so a genuine selection change also
        # re-syncs power_input the same way a user-driven change would.
        if self.printer_combo.currentData() != current:
            self._on_printer_changed(self.printer_combo.currentIndex())

    def set_app_settings(self, s: AppSettings) -> None:
        # Prefill defaults ONCE, on first load only. A later call (e.g. after
        # the user saves new rates in the Settings tab) still needs to update
        # self._app_settings for labour_rate/vat_pct lookups at Save time —
        # it just must not stomp values the user may be mid-edit on here.
        self._app_settings = s
        if not self._app_settings_applied:
            self._app_settings_applied = True
            self.failure_pct_input.blockSignals(True)
            self.failure_pct_input.setValue(s.default_failure_pct)
            self.failure_pct_input.blockSignals(False)
            self.margin_input.blockSignals(True)
            self.margin_input.setValue(s.default_margin_pct)
            self.margin_input.blockSignals(False)

    def set_quote_result(self, seq: int, result: QuoteResult, drift: str | None = None) -> None:
        if seq != self._quote_seq:
            return  # superseded by a later request; this response is stale
        self._last_quote = result
        self._last_quote_labour_rate = self._pending_labour_rate
        self.quote_error_label.setText("")
        display = {
            "filament_cost": result.filament_cost,
            "electricity_cost": result.electricity_cost,
            "printer_usage_cost": result.depreciation_cost,
            "labour_cost": result.labour_cost,
            "direct_cost": result.direct_cost,
            "failure_allowance": result.failure_allowance,
            "true_cost": result.true_cost,
            "profit": result.profit,
            "price_ex_vat": result.price_ex_vat,
            "vat_amount": result.vat_amount,
            "price_incl_vat": result.price_incl_vat,
        }
        for k, v in display.items():
            self._cost_labels[k].setText(f"R {v:.2f}")
        if drift:
            # Save stays enabled: the numbers on screen and about to be
            # submitted are still the server's authoritative ones. This is a
            # signal that two independent money formulas disagree, not a
            # reason to block a user who did nothing wrong.
            self._set_quote_status(
                f"⚠ Local calculation disagrees with the server ({drift})", "warning"
            )
        else:
            self._set_quote_status("", "muted")
        self._update_save_enabled()

    def set_offline_quote_result(self, seq: int, breakdown: QuoteBreakdown, cached_at: str) -> None:
        if seq != self._quote_seq:
            return  # superseded by a later request; this response is stale
        self._last_quote = None  # offline numbers are never submittable
        self.quote_error_label.setText("")
        display = {
            "filament_cost": breakdown.filament_cost,
            "electricity_cost": breakdown.electricity_cost,
            "printer_usage_cost": breakdown.depreciation_cost,
            "labour_cost": breakdown.labour_cost,
            "direct_cost": breakdown.direct_cost,
            "failure_allowance": breakdown.failure_allowance,
            "true_cost": breakdown.true_cost,
            "profit": breakdown.profit,
            "price_ex_vat": breakdown.price_ex_vat,
            "vat_amount": breakdown.vat_amount,
            "price_incl_vat": breakdown.price_incl_vat,
        }
        for k, v in display.items():
            self._cost_labels[k].setText(f"R {v:.2f}")
        self._set_quote_status(
            f"Offline — rates as of {_format_cached_at(cached_at)}. Reconnect to save.", "muted"
        )
        self._update_save_enabled()

    def set_quote_error(self, seq: int, message: str) -> None:
        if seq != self._quote_seq:
            return  # superseded by a later request; this response is stale
        self._last_quote = None
        self.quote_error_label.setText(message)
        self._set_quote_status("", "muted")
        self._clear_cost_labels()
        self._update_save_enabled()

    # ── Internals ────────────────────────────────────────────────────────────

    def _set_quote_status(self, text: str, style: str) -> None:
        self.quote_status_label.setText(text)
        self.quote_status_label.setProperty("muted", style == "muted")
        self.quote_status_label.setProperty("warning", style == "warning")
        self.quote_status_label.style().unpolish(self.quote_status_label)
        self.quote_status_label.style().polish(self.quote_status_label)

    def _on_printer_changed(self, _idx: int) -> None:
        printer_id = self.printer_combo.currentData()
        if printer_id is not None:
            printer = next((p for p in self._printers if p.id == printer_id), None)
            if printer is not None:
                self.power_input.blockSignals(True)
                self.power_input.setValue(printer.power_watts_default)
                self.power_input.blockSignals(False)
        self._schedule_quote()

    def _clear_cost_labels(self) -> None:
        for lbl in self._cost_labels.values():
            lbl.setText("R 0.00")

    def _update_save_enabled(self) -> None:
        enabled = self._last_quote is not None
        self.save_btn.setEnabled(enabled)
        self.draft_btn.setEnabled(enabled)

    def _current_quote_params(self) -> dict | None:
        sku_id = self.sku_combo.currentData()
        printer_id = self.printer_combo.currentData()
        grams = self.grams_input.value()
        hours = self.hours_input.value()
        if sku_id is None or printer_id is None or grams <= 0 or hours <= 0:
            return None
        return {
            "sku_id": sku_id,
            "grams": grams,
            "printer_id": printer_id,
            "print_hours": hours,
            "power_watts": self.power_input.value() or None,
            "labour_minutes": self.labour_minutes_input.value(),
            "consumables_cost": self.consumables_input.value(),
            "overhead_cost": self.overhead_input.value(),
            "failure_pct": self.failure_pct_input.value(),
            "margin_pct": self.margin_input.value(),
        }

    def _schedule_quote(self, *_args) -> None:
        # Bump the seq HERE, not in _fire_quote: a request already in flight
        # for the pre-edit input must be recognisable as stale the instant
        # this edit happens, even if its response arrives before the next
        # debounced request is actually sent (still inside the debounce
        # window). Bumping only when the next request fires would leave that
        # arrival window where an old response still matches the "current"
        # seq and gets applied against inputs it was never quoted for.
        self._quote_seq += 1
        self._last_quote = None
        # A drift/offline badge from the previous quote is now describing
        # inputs the user has already changed — leaving it up for the
        # ~400ms debounce window (plus network latency) would show a stale
        # banner more prominently than a stale number alone ever was.
        self._set_quote_status("", "muted")
        self._update_save_enabled()
        self._quote_timer.start()

    def _fire_quote(self) -> None:
        params = self._current_quote_params()
        if params is None:
            self.quote_error_label.setText("")
            self._set_quote_status("", "muted")
            self._clear_cost_labels()
            return
        # Freeze the rate this request will actually be priced with, not
        # whatever self._app_settings might evolve into before the response
        # lands (see the field's own comment in __init__).
        self._pending_labour_rate = (
            self._app_settings.labour_rate_per_hour if self._app_settings else None
        )
        self.quote_requested.emit(self._quote_seq, params)

    def _build_payload(self) -> JobPayload:
        q = self._last_quote
        if q is None:
            raise RuntimeError("_build_payload called with no quote on hand")
        material = q.material_lines[0]
        return JobPayload(
            filament_sku_id=self.sku_combo.currentData(),
            printer_id=self.printer_combo.currentData(),
            slicer_grams=self.grams_input.value(),
            slicer_seconds=int(self.hours_input.value() * 3600),
            filament_price=material.cost_per_g,
            filament_cost=q.filament_cost,
            electricity_cost=q.electricity_cost,
            printer_usage_cost=q.depreciation_cost,
            power_watts=q.power_watts,
            labour_minutes=self.labour_minutes_input.value(),
            labour_rate=self._last_quote_labour_rate,
            consumables_cost=self.consumables_input.value(),
            overhead_cost=self.overhead_input.value(),
            failure_pct=q.failure_pct,
            direct_cost=q.direct_cost,
            total_cost=q.true_cost,
            profit=q.profit,
            selling_price=q.price_ex_vat,
            vat_pct=q.vat_pct,
            price_incl_vat=q.price_incl_vat,
            pricing_mode=q.pricing_mode,
            notes=self.notes_input.toPlainText().strip() or None,
        )

    def _on_save(self) -> None:
        payload = self._build_payload()
        self.payload_ready.emit(payload)

    def _on_save_draft(self) -> None:
        # Same payload, save-and-send is opt-in; drafts just emit the payload too
        # MainWindow decides whether to chain a send_to_printer call
        payload = self._build_payload()
        self.payload_ready.emit(payload)
