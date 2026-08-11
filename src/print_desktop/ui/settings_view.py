"""Settings tab — shop-wide pricing policy (GET/PUT /api/settings) plus each
printer's purchase price / expected life hours (PATCH /api/printers/{id}).

These rates used to live in local TOML, overridable per job in the manual
form. Per plan.md's Settings model docstring: "a rate that lives on one
client cannot be frozen into a server-side cost snapshot, and two clients
reading different rates would quote different prices for the same print" —
so they live here instead, edited once, shared by every client.

Follows the same architecture as HomeView: this widget touches no network
code itself. It emits signals; MainWindow does the actual ApiClient calls
and pushes results back in via set_settings()/set_printers()/
set_settings_status()/set_printers_status().
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from print_desktop.models.print_request import AppSettings, Printer


class SettingsView(QWidget):
    save_settings_requested = Signal(dict)
    save_printer_requested = Signal(int, dict)  # printer_id, fields

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._currency = "ZAR"  # overwritten by set_settings; PUT still needs it (full replace)
        self._printer_price_inputs: dict[int, QDoubleSpinBox] = {}
        self._printer_life_inputs: dict[int, QDoubleSpinBox] = {}
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(24)

        heading = QLabel("Pricing settings", content)
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)

        self.pricing_mode_combo = QComboBox(content)
        self.pricing_mode_combo.addItem("Margin on price", userData="margin_on_price")
        self.pricing_mode_combo.addItem("Markup on cost", userData="markup_on_cost")

        self.margin_input = QDoubleSpinBox(content)
        self.margin_input.setRange(0, 1000)
        self.margin_input.setSuffix(" %")
        self.margin_input.setDecimals(2)

        self.vat_input = QDoubleSpinBox(content)
        self.vat_input.setRange(0, 100)
        self.vat_input.setSuffix(" %")
        self.vat_input.setDecimals(2)

        self.labour_rate_input = QDoubleSpinBox(content)
        self.labour_rate_input.setRange(0, 100_000)
        self.labour_rate_input.setPrefix("R ")
        self.labour_rate_input.setSuffix(" / h")
        self.labour_rate_input.setDecimals(2)

        self.electricity_input = QDoubleSpinBox(content)
        self.electricity_input.setRange(0, 100)
        self.electricity_input.setPrefix("R ")
        self.electricity_input.setSuffix(" / kWh")
        self.electricity_input.setDecimals(2)

        self.failure_pct_input = QDoubleSpinBox(content)
        self.failure_pct_input.setRange(0, 1000)
        self.failure_pct_input.setSuffix(" %")
        self.failure_pct_input.setDecimals(2)

        form.addRow("Pricing mode", self.pricing_mode_combo)
        form.addRow("Default margin", self.margin_input)
        form.addRow("VAT rate", self.vat_input)
        form.addRow("Labour rate", self.labour_rate_input)
        form.addRow("Electricity tariff", self.electricity_input)
        form.addRow("Default failure allowance", self.failure_pct_input)
        layout.addLayout(form)

        self.save_settings_btn = QPushButton("Save pricing settings", content)
        self.save_settings_btn.setProperty("primary", True)
        # Disabled until a real GET /api/settings response has populated the
        # form: the startup load runs once and is never retried on failure,
        # and every field above defaults to Qt's bare 0.0 — an enabled
        # button here would let a transient startup hiccup be followed by
        # one click that PUTs an all-zero pricing policy over the shop's
        # real settings (PUT is a full replace).
        self.save_settings_btn.setEnabled(False)
        self.save_settings_btn.clicked.connect(self._on_save_settings)
        layout.addWidget(self.save_settings_btn)

        self.settings_status = QLabel("", content)
        self.settings_status.setProperty("muted", True)
        layout.addWidget(self.settings_status)

        printers_heading = QLabel("Printers", content)
        printers_heading.setProperty("heading", True)
        layout.addWidget(printers_heading)

        self.printers_form = QFormLayout()
        self.printers_form.setSpacing(10)
        layout.addLayout(self.printers_form)

        self.printers_status = QLabel("", content)
        self.printers_status.setProperty("muted", True)
        layout.addWidget(self.printers_status)

        layout.addStretch(1)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Public API ───────────────────────────────────────────────────────────

    def set_settings(self, s: AppSettings) -> None:
        self._currency = s.currency
        idx = self.pricing_mode_combo.findData(s.pricing_mode)
        if idx >= 0:
            self.pricing_mode_combo.setCurrentIndex(idx)
        self.margin_input.setValue(s.default_margin_pct)
        self.vat_input.setValue(s.vat_pct)
        self.labour_rate_input.setValue(s.labour_rate_per_hour)
        self.electricity_input.setValue(s.electricity_tariff_per_kwh)
        self.failure_pct_input.setValue(s.default_failure_pct)
        self.save_settings_btn.setEnabled(True)

    def set_settings_status(self, message: str) -> None:
        self.settings_status.setText(message)

    def set_printers(self, printers: list[Printer]) -> None:
        # Full rebuild, same as ManualForm's SKU/printer combos — but each
        # row here is a pair of *editable, unsaved* spinboxes, not a
        # read-only display, so a naive rebuild would blow away whatever the
        # user is mid-typing every time this is called (startup, and after
        # any printer save). Snapshot current values by printer id first and
        # restore them into the rebuilt rows, rather than resetting to the
        # server's values on every refresh.
        pending_price = {pid: inp.value() for pid, inp in self._printer_price_inputs.items()}
        pending_life = {pid: inp.value() for pid, inp in self._printer_life_inputs.items()}

        while self.printers_form.rowCount():
            self.printers_form.removeRow(0)
        self._printer_price_inputs.clear()
        self._printer_life_inputs.clear()

        if not printers:
            self.printers_form.addRow(QLabel("No printers yet.", self))
            return

        for p in printers:
            price = QDoubleSpinBox(self)
            price.setRange(0, 10_000_000)
            price.setPrefix("R ")
            price.setDecimals(2)
            price.setValue(pending_price.get(p.id, p.purchase_price))

            life = QDoubleSpinBox(self)
            life.setRange(0.01, 1_000_000)
            life.setSuffix(" h")
            life.setDecimals(2)
            life.setValue(pending_life.get(p.id, p.expected_life_hours))

            save_btn = QPushButton("Save", self)
            save_btn.clicked.connect(lambda _checked=False, pid=p.id: self._on_save_printer(pid))

            self._printer_price_inputs[p.id] = price
            self._printer_life_inputs[p.id] = life

            self.printers_form.addRow(f"{p.name} — purchase price", price)
            self.printers_form.addRow(f"{p.name} — expected life", life)
            self.printers_form.addRow("", save_btn)

    def set_printers_status(self, message: str) -> None:
        self.printers_status.setText(message)

    # ── Internals ────────────────────────────────────────────────────────────

    def _on_save_settings(self) -> None:
        self.save_settings_requested.emit(
            {
                "pricing_mode": self.pricing_mode_combo.currentData(),
                "default_margin_pct": self.margin_input.value(),
                "vat_pct": self.vat_input.value(),
                "labour_rate_per_hour": self.labour_rate_input.value(),
                "electricity_tariff_per_kwh": self.electricity_input.value(),
                "default_failure_pct": self.failure_pct_input.value(),
                "currency": self._currency,
            }
        )

    def _on_save_printer(self, printer_id: int) -> None:
        self.save_printer_requested.emit(
            printer_id,
            {
                "purchase_price": self._printer_price_inputs[printer_id].value(),
                "expected_life_hours": self._printer_life_inputs[printer_id].value(),
            },
        )
