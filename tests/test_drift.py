"""Tests for the runtime drift detector (services/drift.py) — the actual
guarantee behind Phase 6's "won't silently drift" claim. Exercised directly,
not just incidentally through a live app, per the plan's own accept
criterion: "the detector is tested, not just present."
"""

from decimal import Decimal

from print_desktop.models.print_request import Printer, QuoteMaterialLine, QuoteResult
from print_desktop.services.cost import QuoteBreakdown
from print_desktop.services.drift import build_local_recompute, find_drift


def _printer(**overrides) -> Printer:
    base = {
        "id": 1, "name": "Test Printer", "power_watts_default": 180.0,
        "purchase_price": 12000.0, "expected_life_hours": 4000.0,
        "depreciation_per_hour": 3.0, "status": "active",
    }
    base.update(overrides)
    return Printer(**base)


def _quote_params(**overrides) -> dict:
    base = {
        "print_hours": 6.7,
        "labour_minutes": 20,
        "consumables_cost": 0,
        "overhead_cost": 0,
    }
    base.update(overrides)
    return base


def _server(**overrides) -> QuoteResult:
    base = {
        "material_lines": [
            QuoteMaterialLine(sku_id=1, grams=128.0, cost_per_g=0.45, line_cost=57.6)
        ],
        "filament_cost": 57.60,
        "electricity_cost": 3.44,
        "depreciation_cost": 20.10,
        "labour_cost": 50.00,
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
        "power_watts": 180.0,
    }
    base.update(overrides)
    return QuoteResult(**base)


def _local(**overrides) -> QuoteBreakdown:
    base = {
        "filament_cost": Decimal("57.60"),
        "electricity_cost": Decimal("3.44"),
        "depreciation_cost": Decimal("20.10"),
        "labour_cost": Decimal("50.00"),
        "direct_cost": Decimal("131.14"),
        "failure_allowance": Decimal("13.11"),
        "true_cost": Decimal("144.25"),
        "price_ex_vat": Decimal("320.56"),
        "profit": Decimal("176.31"),
        "margin_pct_actual": Decimal("55.00"),
        "vat_amount": Decimal("48.08"),
        "price_incl_vat": Decimal("368.64"),
    }
    base.update(overrides)
    return QuoteBreakdown(**base)


def test_matching_quotes_report_no_drift():
    assert find_drift(_server(), _local()) is None


def test_a_deliberately_corrupted_local_constant_is_caught():
    """Mirrors the plan's own accept criterion: corrupt one local constant
    and confirm the detector actually fires, not just that it exists."""
    corrupted = _local(true_cost=Decimal("999.99"))
    drift = find_drift(_server(), corrupted)
    assert drift is not None
    assert "true_cost" in drift
    assert "999.99" in drift


def test_every_compared_field_is_actually_checked():
    """A detector that only checks its first field would pass the test
    above vacuously. Confirm each of the eleven compared fields independently
    triggers a report when it alone disagrees."""
    fields = [
        "filament_cost", "electricity_cost", "depreciation_cost", "labour_cost",
        "direct_cost", "failure_allowance", "true_cost", "price_ex_vat",
        "profit", "vat_amount", "price_incl_vat",
    ]
    for field in fields:
        corrupted = _local(**{field: Decimal("999.99")})
        drift = find_drift(_server(), corrupted)
        assert drift is not None, f"{field} disagreeing should have been caught"
        assert field in drift


def test_a_genuine_sub_cent_gap_within_tolerance_is_not_reported_as_drift():
    """A real (if tiny) numeric gap, not just float(100.0) == float(Decimal
    ('100.00')) trivially agreeing with itself — the tolerance window must
    actually be doing something, not merely be unreachable in practice."""
    server = _server(true_cost=100.003)
    local = _local(true_cost=Decimal("100.00"))
    assert find_drift(server, local) is None


def test_a_gap_just_over_tolerance_is_reported_as_drift():
    server = _server(true_cost=100.01)
    local = _local(true_cost=Decimal("100.00"))
    drift = find_drift(server, local)
    assert drift is not None
    assert "true_cost" in drift


# ── build_local_recompute — the trickiest sourcing logic in this phase ─────


def test_build_local_recompute_matches_the_worked_example():
    server = _server()  # true_cost 144.25, price_incl_vat 368.64
    local = build_local_recompute(
        server,
        _quote_params(),
        _printer(purchase_price=12000.0, expected_life_hours=4000.0),
        electricity_tariff_per_kwh=2.85,
        labour_rate_per_hour=150.0,
    )
    assert local is not None
    assert find_drift(server, local) is None


def test_build_local_recompute_uses_the_servers_resolved_cost_per_g_not_a_guess():
    """The client can never independently know the FIFO/weighted-average
    rate the server resolved — using anything else here would make every
    quote "drift" by construction, defeating the whole detector."""
    server = _server(
        material_lines=[
            QuoteMaterialLine(sku_id=1, grams=128.0, cost_per_g=0.99, line_cost=126.72)
        ],
        filament_cost=126.72,
    )
    local = build_local_recompute(
        server,
        _quote_params(),
        _printer(),
        electricity_tariff_per_kwh=2.85,
        labour_rate_per_hour=150.0,
    )
    assert local is not None
    assert local.filament_cost == Decimal("126.72")  # matches the server's rate, not 0.45


def test_build_local_recompute_uses_server_echoed_power_watts_not_the_original_request():
    """The server may have defaulted power_watts from the printer's own
    default when the request omitted it — comparing against the (omitted)
    request value instead of the response's echo would false-positive on
    every quote that relied on that default."""
    server = _server(power_watts=999.0)  # a server-side default far from any request value
    local = build_local_recompute(
        server,
        _quote_params(),  # no power_watts key at all — mirrors an omitted override
        _printer(),
        electricity_tariff_per_kwh=2.85,
        labour_rate_per_hour=150.0,
    )
    assert local is not None
    # electricity_cost must reflect 999W (the echo), not crash on a missing
    # params["power_watts"] and not silently use some other wattage.
    expected_electricity = (
        Decimal("6.7") * (Decimal("999") / Decimal(1000)) * Decimal("2.85")
    ).quantize(Decimal("0.01"))
    assert local.electricity_cost == expected_electricity


def test_build_local_recompute_uses_the_printers_own_rates_not_settings():
    """purchase_price/expected_life_hours come from the specific printer the
    quote was against, not some other cached printer or a settings field."""
    server = _server()
    local = build_local_recompute(
        server,
        _quote_params(),
        _printer(purchase_price=6000.0, expected_life_hours=2000.0),  # same ratio, different scale
        electricity_tariff_per_kwh=2.85,
        labour_rate_per_hour=150.0,
    )
    assert local is not None
    # 6.7h * 6000/2000 = same depreciation_cost as the worked example's 12000/4000
    assert local.depreciation_cost == Decimal("20.10")


def test_build_local_recompute_returns_none_on_invalid_input_not_a_crash():
    server = _server(pricing_mode="cost_plus")
    local = build_local_recompute(
        server,
        _quote_params(),
        _printer(),
        electricity_tariff_per_kwh=2.85,
        labour_rate_per_hour=150.0,
    )
    assert local is None
