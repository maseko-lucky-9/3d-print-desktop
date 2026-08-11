"""Widget tests for SettingsView."""

import pytest

from print_desktop.models.print_request import AppSettings, Printer
from print_desktop.ui.settings_view import SettingsView


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


def _printer(id_=1, name="Primary", price=12000.0, life=4000.0) -> Printer:
    return Printer(
        id=id_,
        name=name,
        power_watts_default=200.0,
        purchase_price=price,
        expected_life_hours=life,
        depreciation_per_hour=price / life,
        status="active",
    )


@pytest.fixture
def view(qtbot):
    w = SettingsView()
    qtbot.addWidget(w)
    return w


def test_save_settings_button_disabled_until_settings_load(qtbot, view):
    """A GET /api/settings that never completes (or fails) must not leave a
    clickable Save button behind every spinbox's bare 0.0 default — PUT is a
    full replace, so one click there would zero the shop's real settings."""
    assert not view.save_settings_btn.isEnabled()

    view.set_settings(_app_settings())

    assert view.save_settings_btn.isEnabled()


def test_set_settings_populates_the_form(qtbot, view):
    view.set_settings(_app_settings())
    assert view.pricing_mode_combo.currentData() == "margin_on_price"
    assert view.margin_input.value() == 55.0
    assert view.vat_input.value() == 15.0
    assert view.labour_rate_input.value() == 150.0
    assert view.electricity_input.value() == 2.85
    assert view.failure_pct_input.value() == 10.0


def test_save_settings_emits_every_required_field(qtbot, view):
    view.set_settings(_app_settings())
    view.margin_input.setValue(60.0)

    with qtbot.waitSignal(view.save_settings_requested, timeout=1000) as blocker:
        view.save_settings_btn.click()

    (fields,) = blocker.args
    assert fields == {
        "pricing_mode": "margin_on_price",
        "default_margin_pct": 60.0,
        "vat_pct": 15.0,
        "labour_rate_per_hour": 150.0,
        "electricity_tariff_per_kwh": 2.85,
        "default_failure_pct": 10.0,
        "currency": "ZAR",
    }


def test_currency_is_carried_through_unedited(qtbot, view):
    """currency has no editable UI (not in the plan's field list) but PUT is
    a full replace — the loaded value must still round-trip on save, not
    silently reset to some default."""
    view.set_settings(_app_settings(currency="USD"))
    with qtbot.waitSignal(view.save_settings_requested, timeout=1000) as blocker:
        view.save_settings_btn.click()
    (fields,) = blocker.args
    assert fields["currency"] == "USD"


def test_set_printers_builds_one_row_per_printer(qtbot, view):
    view.set_printers([_printer(id_=1, name="Primary"), _printer(id_=2, name="Backup")])
    assert set(view._printer_price_inputs) == {1, 2}
    assert set(view._printer_life_inputs) == {1, 2}
    assert view._printer_price_inputs[1].value() == 12000.0
    assert view._printer_life_inputs[1].value() == 4000.0


def test_save_printer_emits_id_and_fields(qtbot, view):
    view.set_printers([_printer(id_=7, price=15000.0, life=5000.0)])
    view._printer_price_inputs[7].setValue(16000.0)

    with qtbot.waitSignal(view.save_printer_requested, timeout=1000) as blocker:
        view._on_save_printer(7)

    printer_id, fields = blocker.args
    assert printer_id == 7
    assert fields == {"purchase_price": 16000.0, "expected_life_hours": 5000.0}


def test_set_printers_preserves_unsaved_edits_across_a_refresh(qtbot, view):
    """A refresh (startup, or after another printer's save) must not blow
    away a value the user is mid-editing on a printer's row."""
    view.set_printers([_printer(id_=1, price=12000.0), _printer(id_=2, price=8000.0)])
    view._printer_price_inputs[1].setValue(99999.0)  # unsaved edit

    view.set_printers([_printer(id_=1, price=12000.0), _printer(id_=2, price=8000.0)])

    assert view._printer_price_inputs[1].value() == 99999.0


def test_set_printers_empty_list_shows_a_placeholder_not_a_crash(qtbot, view):
    view.set_printers([])
    assert view.printers_form.rowCount() == 1
