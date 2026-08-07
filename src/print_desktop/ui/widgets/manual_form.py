"""Manual cost-entry form — the heart of Option E (§21).

User picks a filament SKU from a dropdown (populated from /api/filaments/skus),
types grams + hours read off BambuStudio GUI's preview pane, and the cost panel
to the right updates live as they type.
"""


from PySide6.QtCore import Signal
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

from print_desktop.models.print_request import FilamentSku, JobPayload
from print_desktop.services.cost import calculate_costs
from print_desktop.storage.settings import Settings


class ManualForm(QWidget):
    """Form widget — emits payload_ready(JobPayload) on Save click."""

    payload_ready = Signal(object)  # JobPayload

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._skus: list[FilamentSku] = []
        self._build_ui()
        self._connect_change_signals()
        self._update_costs()

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
        self.sku_combo.addItem("(no SKU — enter price manually)", userData=None)

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

        self.spool_size_input = QDoubleSpinBox(self)
        self.spool_size_input.setRange(1, 50_000)
        self.spool_size_input.setSuffix(" g")
        self.spool_size_input.setDecimals(0)
        self.spool_size_input.setValue(self._settings.filament_size_g)

        self.spool_price_input = QDoubleSpinBox(self)
        self.spool_price_input.setRange(0, 100_000)
        self.spool_price_input.setPrefix("R ")
        self.spool_price_input.setDecimals(2)
        self.spool_price_input.setValue(self._settings.filament_price)

        self.electricity_input = QDoubleSpinBox(self)
        self.electricity_input.setRange(0, 100)
        self.electricity_input.setPrefix("R ")
        self.electricity_input.setSuffix(" / kWh")
        self.electricity_input.setDecimals(2)
        self.electricity_input.setValue(self._settings.electricity_rate)

        self.power_input = QDoubleSpinBox(self)
        self.power_input.setRange(0, 10_000)
        self.power_input.setSuffix(" W")
        self.power_input.setDecimals(0)
        self.power_input.setValue(self._settings.power_watts)

        self.printer_hourly_input = QDoubleSpinBox(self)
        self.printer_hourly_input.setRange(0, 10_000)
        self.printer_hourly_input.setPrefix("R ")
        self.printer_hourly_input.setSuffix(" / h")
        self.printer_hourly_input.setDecimals(2)
        self.printer_hourly_input.setValue(self._settings.printer_hourly_cost)

        self.margin_input = QDoubleSpinBox(self)
        self.margin_input.setRange(0, 1000)
        self.margin_input.setSuffix(" %")
        self.margin_input.setDecimals(0)
        self.margin_input.setValue(self._settings.profit_margin_pct)

        self.notes_input = QPlainTextEdit(self)
        self.notes_input.setPlaceholderText("Notes (optional)")
        self.notes_input.setFixedHeight(60)

        form.addRow("Filament SKU", self.sku_combo)
        form.addRow("Grams used", self.grams_input)
        form.addRow("Print hours", self.hours_input)
        form.addRow("Spool size", self.spool_size_input)
        form.addRow("Spool price", self.spool_price_input)
        form.addRow("Electricity rate", self.electricity_input)
        form.addRow("Printer power", self.power_input)
        form.addRow("Printer hourly", self.printer_hourly_input)
        form.addRow("Profit margin", self.margin_input)
        form.addRow("Notes", self.notes_input)

        outer.addWidget(form_widget, stretch=3)

        # Right column — live cost panel + Save CTA
        panel = QVBoxLayout()
        panel.setSpacing(8)

        heading = QLabel("Cost breakdown", self)
        heading.setProperty("heading", True)
        panel.addWidget(heading)

        self._cost_labels: dict[str, QLabel] = {}
        for key, label in [
            ("filament_cost", "Filament cost"),
            ("electricity_cost", "Electricity"),
            ("printer_usage_cost", "Printer usage"),
            ("total_cost", "Total cost"),
            ("profit", "Profit"),
            ("selling_price", "Selling price"),
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

    def _connect_change_signals(self) -> None:
        for w in (
            self.grams_input, self.hours_input, self.spool_size_input,
            self.spool_price_input, self.electricity_input, self.power_input,
            self.printer_hourly_input, self.margin_input,
        ):
            w.valueChanged.connect(self._update_costs)
        self.sku_combo.currentIndexChanged.connect(self._on_sku_changed)

    # ── Public API ───────────────────────────────────────────────────────────

    def set_skus(self, skus: list[FilamentSku]) -> None:
        self._skus = skus
        self.sku_combo.blockSignals(True)
        self.sku_combo.clear()
        self.sku_combo.addItem("(no SKU — enter price manually)", userData=None)
        for sku in skus:
            label = f"{sku.name}"
            if sku.color:
                label += f" — {sku.color}"
            # Available grams, not on-hand: filament already reserved for a
            # queued job cannot be promised to this one. Showing it here is the
            # difference between picking a spool and discovering at print time
            # that it is spoken for.
            label += f"  ({sku.grams_remaining:.0f}g free)"
            self.sku_combo.addItem(label, userData=sku.id)
        self.sku_combo.blockSignals(False)

    # ── Internals ────────────────────────────────────────────────────────────

    def _on_sku_changed(self, _idx: int) -> None:
        sku_id = self.sku_combo.currentData()
        if sku_id is not None:
            sku = next((s for s in self._skus if s.id == sku_id), None)
            if sku is not None and sku.cost_per_gram > 0:
                # Override spool_price input so cost reflects this SKU's WAC
                price_for_full_spool = sku.cost_per_gram * self.spool_size_input.value()
                self.spool_price_input.blockSignals(True)
                self.spool_price_input.setValue(price_for_full_spool)
                self.spool_price_input.blockSignals(False)
        self._update_costs()

    def _update_costs(self) -> None:
        try:
            r = calculate_costs(
                filament_size=self.spool_size_input.value(),
                filament_price=self.spool_price_input.value(),
                filament_used=self.grams_input.value(),
                total_print_hours=self.hours_input.value(),
                electricity_rate=self.electricity_input.value(),
                power_watts=self.power_input.value(),
                printer_hourly_cost=self.printer_hourly_input.value(),
                profit_margin_pct=self.margin_input.value(),
            )
        except ValueError:
            return
        for k, v in r.items():
            if k in self._cost_labels:
                self._cost_labels[k].setText(f"R {v:.2f}")

    def _build_payload(self) -> JobPayload:
        r = calculate_costs(
            filament_size=self.spool_size_input.value(),
            filament_price=self.spool_price_input.value(),
            filament_used=self.grams_input.value(),
            total_print_hours=self.hours_input.value(),
            electricity_rate=self.electricity_input.value(),
            power_watts=self.power_input.value(),
            printer_hourly_cost=self.printer_hourly_input.value(),
            profit_margin_pct=self.margin_input.value(),
        )
        return JobPayload(
            filament_sku_id=self.sku_combo.currentData() or 0,
            slicer_grams=self.grams_input.value(),
            slicer_seconds=int(self.hours_input.value() * 3600),
            filament_size=self.spool_size_input.value(),
            filament_price=self.spool_price_input.value(),
            electricity_rate=self.electricity_input.value(),
            power_watts=self.power_input.value(),
            printer_hourly_cost=self.printer_hourly_input.value(),
            profit_margin_pct=self.margin_input.value(),
            **r,
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
