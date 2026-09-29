"""Tests for build_offline_quote (services/offline.py) — the sourcing logic
behind Phase 6's offline fallback. Extracted as a pure function specifically
so this can be tested without a live MainWindow/ApiClient/TOML file.
"""

from decimal import Decimal

from print_desktop.services.offline import build_offline_quote

_SKUS = [{"id": 1, "name": "PLA Black", "color": "Black", "cost_per_gram": 0.45}]
_PRINTERS = [
    {
        "id": 1, "name": "Test Printer", "power_watts_default": 180.0,
        "purchase_price": 12000.0, "expected_life_hours": 4000.0,
    }
]


def _params(**overrides) -> dict:
    base = {
        "sku_id": 1,
        "grams": 128,
        "printer_id": 1,
        "print_hours": 6.7,
        "power_watts": None,
        "labour_minutes": 20,
        "consumables_cost": 0,
        "overhead_cost": 0,
        "failure_pct": 10,
        "margin_pct": 55,
    }
    base.update(overrides)
    return base


def test_offline_quote_reproduces_the_worked_example_to_the_cent():
    """plan.md's own Phase 6 accept criterion: "forced offline still quotes
    the worked example to the cent." — same inputs as the golden vector's
    worked_example_margin_on_price case."""
    result = build_offline_quote(
        _params(),
        _SKUS,
        _PRINTERS,
        cached_electricity_tariff_per_kwh=2.85,
        cached_labour_rate_per_hour=150.0,
        cached_pricing_mode="margin_on_price",
        cached_vat_pct=15.0,
    )
    assert result is not None
    assert result.filament_cost == Decimal("57.60")
    assert result.electricity_cost == Decimal("3.44")
    assert result.depreciation_cost == Decimal("20.10")
    assert result.labour_cost == Decimal("50.00")
    assert result.direct_cost == Decimal("131.14")
    assert result.failure_allowance == Decimal("13.11")
    assert result.true_cost == Decimal("144.25")
    assert result.price_ex_vat == Decimal("320.56")
    assert result.vat_amount == Decimal("48.08")
    assert result.price_incl_vat == Decimal("368.64")


def test_unknown_sku_returns_none():
    result = build_offline_quote(
        _params(sku_id=999),
        _SKUS,
        _PRINTERS,
        cached_electricity_tariff_per_kwh=2.85,
        cached_labour_rate_per_hour=150.0,
        cached_pricing_mode="margin_on_price",
        cached_vat_pct=15.0,
    )
    assert result is None


def test_unknown_printer_returns_none():
    result = build_offline_quote(
        _params(printer_id=999),
        _SKUS,
        _PRINTERS,
        cached_electricity_tariff_per_kwh=2.85,
        cached_labour_rate_per_hour=150.0,
        cached_pricing_mode="margin_on_price",
        cached_vat_pct=15.0,
    )
    assert result is None


def test_power_watts_override_is_used_when_present():
    with_override = build_offline_quote(
        _params(power_watts=250.0),
        _SKUS,
        _PRINTERS,
        cached_electricity_tariff_per_kwh=2.85,
        cached_labour_rate_per_hour=150.0,
        cached_pricing_mode="margin_on_price",
        cached_vat_pct=15.0,
    )
    without_override = build_offline_quote(
        _params(power_watts=None),
        _SKUS,
        _PRINTERS,
        cached_electricity_tariff_per_kwh=2.85,
        cached_labour_rate_per_hour=150.0,
        cached_pricing_mode="margin_on_price",
        cached_vat_pct=15.0,
    )
    assert with_override is not None and without_override is not None
    assert with_override.electricity_cost != without_override.electricity_cost


def test_zero_power_watts_falls_back_to_printer_default_not_zero():
    """params["power_watts"] or printer["power_watts_default"] — a
    genuinely-zero override (spinbox never touched) must fall back to the
    printer's default, not price electricity at literal zero."""
    result = build_offline_quote(
        _params(power_watts=0.0),
        _SKUS,
        _PRINTERS,
        cached_electricity_tariff_per_kwh=2.85,
        cached_labour_rate_per_hour=150.0,
        cached_pricing_mode="margin_on_price",
        cached_vat_pct=15.0,
    )
    assert result is not None
    assert result.electricity_cost == Decimal("3.44")  # matches the 180W-default worked example


def test_invalid_pricing_mode_returns_none_not_a_crash():
    result = build_offline_quote(
        _params(),
        _SKUS,
        _PRINTERS,
        cached_electricity_tariff_per_kwh=2.85,
        cached_labour_rate_per_hour=150.0,
        cached_pricing_mode="cost_plus",
        cached_vat_pct=15.0,
    )
    assert result is None
