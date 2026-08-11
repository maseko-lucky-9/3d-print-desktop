"""Widget tests for ManualForm — first real usage of pytest-qt in this repo.

No qasync/asyncio machinery is needed: ManualForm never touches the network
directly, it only emits signals (quote_requested/payload_ready) that
MainWindow wires up to ApiClient. These tests exercise the widget in
isolation, driving it exactly the way MainWindow does.
"""

import pytest

from print_desktop.models.print_request import (
    AppSettings,
    FilamentSku,
    Printer,
    QuoteMaterialLine,
    QuoteResult,
)
from print_desktop.ui.widgets.manual_form import ManualForm


def _sku(id_=1, name="PETG Red", grams=500.0, cost=2.5) -> FilamentSku:
    return FilamentSku(id=id_, name=name, grams_remaining=grams, cost_per_gram=cost)


def _printer(id_=1, name="Primary", power=200.0, price=12000.0, life=4000.0) -> Printer:
    return Printer(
        id=id_,
        name=name,
        power_watts_default=power,
        purchase_price=price,
        expected_life_hours=life,
        depreciation_per_hour=price / life,
        status="active",
    )


def _quote_result(**overrides) -> QuoteResult:
    base = {
        "material_lines": [
            QuoteMaterialLine(sku_id=1, grams=100.0, cost_per_g=0.576, line_cost=57.6)
        ],
        "filament_cost": 57.6,
        "electricity_cost": 3.44,
        "depreciation_cost": 20.1,
        "labour_cost": 50.0,
        "direct_cost": 131.14,
        "failure_allowance": 13.11,
        "true_cost": 144.25,
        "price_ex_vat": 320.56,
        "profit": 176.31,
        "margin_pct_actual": 55.0,
        "vat_amount": 48.08,
        "price_incl_vat": 368.64,
        "pricing_mode": "margin_on_price",
        "margin_pct": 55.0,
        "failure_pct": 10.0,
        "vat_pct": 15.0,
        "power_watts": 200.0,
    }
    base.update(overrides)
    return QuoteResult(**base)


def _app_settings(**overrides) -> AppSettings:
    base = {
        "id": 1,
        "electricity_tariff_per_kwh": 2.85,
        "vat_pct": 15.0,
        "labour_rate_per_hour": 150.0,
        "pricing_mode": "margin_on_price",
        "default_margin_pct": 55.0,
        "default_failure_pct": 10.0,
        "currency": "ZAR",
    }
    base.update(overrides)
    return AppSettings(**base)


@pytest.fixture
def form(qtbot):
    w = ManualForm()
    qtbot.addWidget(w)
    return w


def test_incomplete_form_does_not_request_a_quote(qtbot, form):
    """Grams/hours alone, with no SKU or printer picked, must not fire."""
    with qtbot.waitSignal(form.quote_requested, timeout=700, raising=False) as blocker:
        form.grams_input.setValue(100.0)
        form.hours_input.setValue(2.0)
    assert not blocker.signal_triggered


def test_complete_form_requests_a_quote_once_after_debounce(qtbot, form):
    form.set_skus([_sku()])
    form.set_printers([_printer()])
    with qtbot.waitSignal(form.quote_requested, timeout=1000) as blocker:
        form.sku_combo.setCurrentIndex(1)
        form.printer_combo.setCurrentIndex(1)
        form.grams_input.setValue(100.0)
        form.hours_input.setValue(2.0)
    seq, params = blocker.args
    assert seq == form._quote_seq
    assert params["sku_id"] == 1
    assert params["printer_id"] == 1
    assert params["grams"] == 100.0
    assert params["print_hours"] == 2.0


def test_selecting_a_printer_prefills_its_default_power(qtbot, form):
    form.set_printers([_printer(power=210.0)])
    form.printer_combo.setCurrentIndex(1)
    assert form.power_input.value() == 210.0


def test_set_printers_preserves_current_selection_across_refresh(qtbot, form):
    form.set_printers([_printer(id_=1, name="A"), _printer(id_=2, name="B")])
    form.printer_combo.setCurrentIndex(2)
    assert form.printer_combo.currentData() == 2

    form.set_printers([_printer(id_=1, name="A"), _printer(id_=2, name="B (renamed)")])

    assert form.printer_combo.currentData() == 2


def test_set_quote_result_populates_breakdown_and_enables_save(qtbot, form):
    form.set_skus([_sku()])
    form.set_printers([_printer()])
    form.sku_combo.setCurrentIndex(1)
    form.printer_combo.setCurrentIndex(1)
    assert not form.save_btn.isEnabled()

    form.set_quote_result(form._quote_seq, _quote_result())

    assert form.save_btn.isEnabled()
    assert form.draft_btn.isEnabled()
    assert form._cost_labels["true_cost"].text() == "R 144.25"
    assert form._cost_labels["price_incl_vat"].text() == "R 368.64"


def test_set_quote_result_ignores_a_stale_sequence(qtbot, form):
    """A slow response for an input state the user has since changed must
    never re-enable Save with numbers that no longer match the form."""
    form.set_skus([_sku()])
    form.set_printers([_printer()])
    form.sku_combo.setCurrentIndex(1)
    form.printer_combo.setCurrentIndex(1)
    stale_seq = form._quote_seq
    form.grams_input.setValue(50.0)  # bumps _quote_seq past stale_seq
    assert form._quote_seq != stale_seq

    form.set_quote_result(stale_seq, _quote_result())

    assert form._last_quote is None
    assert not form.save_btn.isEnabled()


def test_set_quote_error_disables_save_and_shows_message(qtbot, form):
    form.set_skus([_sku()])
    form.set_printers([_printer()])
    form.sku_combo.setCurrentIndex(1)
    form.printer_combo.setCurrentIndex(1)
    form.set_quote_result(form._quote_seq, _quote_result())
    assert form.save_btn.isEnabled()

    form.set_quote_error(form._quote_seq, "Backend unreachable")

    assert not form.save_btn.isEnabled()
    assert form.quote_error_label.text() == "Backend unreachable"
    assert form._cost_labels["true_cost"].text() == "R 0.00"


def test_build_payload_uses_frozen_quote_values_not_live_recompute(qtbot, form):
    form.set_skus([_sku()])
    form.set_printers([_printer()])
    form.set_app_settings(_app_settings())
    # Go through the real debounce -> _fire_quote path rather than calling
    # set_quote_result directly: _fire_quote is what captures
    # _pending_labour_rate, and skipping it would silently leave
    # payload.labour_rate as None regardless of what this test asserts.
    with qtbot.waitSignal(form.quote_requested, timeout=1000) as blocker:
        form.sku_combo.setCurrentIndex(1)
        form.printer_combo.setCurrentIndex(1)
        form.grams_input.setValue(100.0)
        form.hours_input.setValue(2.0)
        form.labour_minutes_input.setValue(20.0)
    seq, _params = blocker.args
    form.set_quote_result(seq, _quote_result())

    payload = form._build_payload()

    assert payload.filament_sku_id == 1
    assert payload.printer_id == 1
    assert payload.filament_price == 0.576
    assert payload.power_watts == 200.0  # echoed back by the quote response
    assert payload.direct_cost == 131.14
    assert payload.total_cost == 144.25
    assert payload.selling_price == 320.56
    assert payload.price_incl_vat == 368.64
    assert payload.labour_rate == 150.0  # frozen from AppSettings at fire time
    assert payload.pricing_mode == "margin_on_price"


def test_build_payload_freezes_labour_rate_from_fire_time_not_save_time(qtbot, form):
    """_validate_costs on the backend recomputes labour_cost from
    labour_minutes*labour_rate and checks it against direct_cost — so the
    labour_rate sent at Save MUST match the rate this specific quote was
    actually priced with, even if the Settings tab was saved with a new
    rate in the meantime (which updates self._app_settings without
    invalidating the on-screen quote, by design)."""
    form.set_skus([_sku()])
    form.set_printers([_printer()])
    form.set_app_settings(_app_settings(labour_rate_per_hour=150.0))
    with qtbot.waitSignal(form.quote_requested, timeout=1000) as blocker:
        form.sku_combo.setCurrentIndex(1)
        form.printer_combo.setCurrentIndex(1)
        form.grams_input.setValue(100.0)
        form.hours_input.setValue(2.0)
    seq, _params = blocker.args
    form.set_quote_result(seq, _quote_result())
    assert form._build_payload().labour_rate == 150.0

    # A settings-tab save lands while this quote is still on screen.
    form.set_app_settings(_app_settings(labour_rate_per_hour=999.0))

    # The payload must still reflect the rate the on-screen quote was
    # actually computed with, not the newly-saved one.
    assert form._build_payload().labour_rate == 150.0


def test_sku_no_longer_in_list_invalidates_the_quote(qtbot, form):
    """The previously-selected SKU disappearing from a refresh (e.g.
    archived by another LAN client) must not leave Save enabled for a
    payload referencing no SKU at all."""
    form.set_skus([_sku(id_=1), _sku(id_=2, name="PLA Blue")])
    form.set_printers([_printer()])
    form.sku_combo.setCurrentIndex(1)  # id=1
    form.printer_combo.setCurrentIndex(1)
    form.set_quote_result(form._quote_seq, _quote_result())
    assert form.save_btn.isEnabled()

    form.set_skus([_sku(id_=2, name="PLA Blue")])  # id=1 is gone

    assert form.sku_combo.currentData() is None
    assert form._last_quote is None
    assert not form.save_btn.isEnabled()


def test_printer_no_longer_in_list_invalidates_the_quote(qtbot, form):
    form.set_skus([_sku()])
    form.set_printers([_printer(id_=1, name="A"), _printer(id_=2, name="B")])
    form.sku_combo.setCurrentIndex(1)
    form.printer_combo.setCurrentIndex(1)  # id=1
    form.set_quote_result(form._quote_seq, _quote_result())
    assert form.save_btn.isEnabled()

    form.set_printers([_printer(id_=2, name="B")])  # id=1 is gone

    assert form.printer_combo.currentData() is None
    assert form._last_quote is None
    assert not form.save_btn.isEnabled()


def test_set_app_settings_prefills_defaults_only_once(qtbot, form):
    """A later call (e.g. after the user saves new settings mid-session)
    must update stored settings for lookups but not overwrite an input the
    user may already be editing."""
    form.set_app_settings(_app_settings(default_margin_pct=55.0, default_failure_pct=10.0))
    assert form.margin_input.value() == 55.0
    assert form.failure_pct_input.value() == 10.0

    form.margin_input.setValue(42.0)
    form.set_app_settings(_app_settings(default_margin_pct=99.0, default_failure_pct=1.0))

    assert form.margin_input.value() == 42.0
