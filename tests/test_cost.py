"""Cost math tests — mirrors backend/tests/test_costing.py's structure and
oracle. Phase 6 of the costing-engine plan: calculate_costs is a from-scratch
Decimal port of backend/costing/engine.py, not the old markup-only float
formula, so every test here is new.
"""

import json
import os
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from print_desktop.services.cost import InvalidQuoteInput, calculate_costs, q_money

VECTORS_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "quote_vectors.json")


def _load_vectors():
    with open(VECTORS_PATH) as f:
        return json.load(f)["vectors"]


def _dec(v) -> Decimal:
    return Decimal(str(v))


# ── The worked example ──────────────────────────────────────────────────────


def test_worked_example_matches_the_spec_exactly():
    r = calculate_costs(
        grams=Decimal(128),
        cost_per_g=Decimal("0.45"),
        print_hours=Decimal("6.7"),
        power_watts=Decimal(180),
        electricity_tariff_per_kwh=Decimal("2.85"),
        printer_purchase_price=Decimal(12000),
        printer_expected_life_hours=Decimal(4000),
        labour_minutes=Decimal(20),
        labour_rate_per_hour=Decimal(150),
        consumables_cost=Decimal(0),
        overhead_cost=Decimal(0),
        failure_pct=Decimal(10),
        margin_pct=Decimal(55),
        pricing_mode="margin_on_price",
        vat_pct=Decimal(15),
    )
    assert r.filament_cost == Decimal("57.60")
    assert r.electricity_cost == Decimal("3.44")
    assert r.depreciation_cost == Decimal("20.10")
    assert r.labour_cost == Decimal("50.00")
    assert r.direct_cost == Decimal("131.14")
    assert r.failure_allowance == Decimal("13.11")
    assert r.true_cost == Decimal("144.25")
    assert r.price_ex_vat == Decimal("320.56")
    assert r.profit == Decimal("176.31")
    assert r.margin_pct_actual == Decimal("55.00")
    assert r.vat_amount == Decimal("48.08")
    assert r.price_incl_vat == Decimal("368.64")


def test_markup_on_cost_matches_the_spec_cross_check():
    base = {
        "grams": Decimal(128),
        "cost_per_g": Decimal("0.45"),
        "print_hours": Decimal("6.7"),
        "power_watts": Decimal(180),
        "electricity_tariff_per_kwh": Decimal("2.85"),
        "printer_purchase_price": Decimal(12000),
        "printer_expected_life_hours": Decimal(4000),
        "labour_minutes": Decimal(20),
        "labour_rate_per_hour": Decimal(150),
        "consumables_cost": Decimal(0),
        "overhead_cost": Decimal(0),
        "failure_pct": Decimal(10),
        "pricing_mode": "markup_on_cost",
        "vat_pct": Decimal(15),
    }
    r55 = calculate_costs(**base, margin_pct=Decimal(55))
    assert r55.true_cost == Decimal("144.25")
    assert r55.price_ex_vat == Decimal("223.59")

    r50 = calculate_costs(**base, margin_pct=Decimal(50))
    assert r50.price_ex_vat == Decimal("216.38")


# ── Validation ───────────────────────────────────────────────────────────────


def _valid_kwargs(**overrides):
    base = {
        "grams": Decimal(100),
        "cost_per_g": Decimal("0.5"),
        "print_hours": Decimal(2),
        "power_watts": Decimal(200),
        "electricity_tariff_per_kwh": Decimal("2.5"),
        "printer_purchase_price": Decimal(12000),
        "printer_expected_life_hours": Decimal(4000),
        "labour_minutes": Decimal(0),
        "labour_rate_per_hour": Decimal(150),
        "consumables_cost": Decimal(0),
        "overhead_cost": Decimal(0),
        "failure_pct": Decimal(10),
        "margin_pct": Decimal(50),
        "pricing_mode": "margin_on_price",
        "vat_pct": Decimal(15),
    }
    base.update(overrides)
    return base


def test_margin_on_price_100_pct_rejected():
    with pytest.raises(InvalidQuoteInput, match="must be < 100"):
        calculate_costs(**_valid_kwargs(margin_pct=Decimal(100)))


def test_markup_on_cost_100_pct_doubles_true_cost():
    r = calculate_costs(**_valid_kwargs(pricing_mode="markup_on_cost", margin_pct=Decimal(100)))
    assert r.price_ex_vat == r.true_cost * 2


def test_negative_margin_rejected():
    with pytest.raises(InvalidQuoteInput, match="margin_pct must be >= 0"):
        calculate_costs(**_valid_kwargs(margin_pct=Decimal(-1)))


def test_negative_failure_pct_rejected():
    with pytest.raises(InvalidQuoteInput, match="failure_pct must be >= 0"):
        calculate_costs(**_valid_kwargs(failure_pct=Decimal(-1)))


def test_zero_print_hours_rejected():
    with pytest.raises(InvalidQuoteInput, match="print_hours must be > 0"):
        calculate_costs(**_valid_kwargs(print_hours=Decimal(0)))


def test_zero_expected_life_hours_rejected():
    with pytest.raises(InvalidQuoteInput, match="expected_life_hours must be > 0"):
        calculate_costs(**_valid_kwargs(printer_expected_life_hours=Decimal(0)))


def test_unknown_pricing_mode_rejected():
    with pytest.raises(InvalidQuoteInput, match="unknown pricing_mode"):
        calculate_costs(**_valid_kwargs(pricing_mode="cost_plus"))


# ── Golden vectors — shared oracle with the backend repo (Phase 6) ─────────
#
# tests/fixtures/quote_vectors.json is byte-identical in both this repo and
# 3d-printing-cost-calculator. Two independent formula implementations (this
# module and backend/costing/engine.py) must both reproduce every vector
# exactly. This is this repo's half of that guarantee; the backend's
# test_costing.py::test_engine_reproduces_every_golden_vector is the other.


@pytest.mark.parametrize("vector", _load_vectors(), ids=lambda v: v["name"])
def test_calculate_costs_reproduces_every_golden_vector(vector):
    inp = vector["input"]
    result = calculate_costs(
        grams=_dec(inp["grams"]),
        cost_per_g=_dec(inp["cost_per_g"]),
        print_hours=_dec(inp["print_hours"]),
        power_watts=_dec(inp["power_watts"]),
        electricity_tariff_per_kwh=_dec(inp["electricity_tariff_per_kwh"]),
        printer_purchase_price=_dec(inp["printer_purchase_price"]),
        printer_expected_life_hours=_dec(inp["printer_expected_life_hours"]),
        labour_minutes=_dec(inp["labour_minutes"]),
        labour_rate_per_hour=_dec(inp["labour_rate_per_hour"]),
        consumables_cost=_dec(inp["consumables_cost"]),
        overhead_cost=_dec(inp["overhead_cost"]),
        failure_pct=_dec(inp["failure_pct"]),
        margin_pct=_dec(inp["margin_pct"]),
        pricing_mode=inp["pricing_mode"],
        vat_pct=_dec(inp["vat_pct"]),
    )
    expected = vector["expected"]
    for field, want in expected.items():
        got = getattr(result, field)
        assert got == _dec(want), f"{vector['name']}: {field} = {got}, expected {want}"


# ── Property test — independent oracle, same shape as the backend's ────────


def _round2(v: Decimal) -> Decimal:
    return q_money(v)


def _decimal_strategy(min_value, max_value, places=2):
    return st.decimals(
        min_value=min_value, max_value=max_value, places=places,
        allow_nan=False, allow_infinity=False,
    )


@given(
    grams=_decimal_strategy("0", "100000"),
    cost_per_g=_decimal_strategy("0", "1000", places=4),
    print_hours=_decimal_strategy("0.01", "1000"),
    power_watts=_decimal_strategy("0", "10000"),
    tariff=_decimal_strategy("0", "100"),
    purchase_price=_decimal_strategy("0", "1000000"),
    life_hours=_decimal_strategy("0.01", "100000"),
    labour_minutes=_decimal_strategy("0", "100000"),
    labour_rate=_decimal_strategy("0", "10000"),
    consumables=_decimal_strategy("0", "10000", places=4),
    overhead=_decimal_strategy("0", "10000", places=4),
    failure_pct=_decimal_strategy("0", "100"),
    margin_pct=_decimal_strategy("0", "99"),
    pricing_mode=st.sampled_from(["margin_on_price", "markup_on_cost"]),
    vat_pct=_decimal_strategy("0", "100"),
)
@hyp_settings(max_examples=200, deadline=None)
def test_calculate_costs_matches_an_independently_written_oracle(
    grams, cost_per_g, print_hours, power_watts, tariff, purchase_price, life_hours,
    labour_minutes, labour_rate, consumables, overhead, failure_pct, margin_pct,
    pricing_mode, vat_pct,
):
    result = calculate_costs(
        grams=grams,
        cost_per_g=cost_per_g,
        print_hours=print_hours,
        power_watts=power_watts,
        electricity_tariff_per_kwh=tariff,
        printer_purchase_price=purchase_price,
        printer_expected_life_hours=life_hours,
        labour_minutes=labour_minutes,
        labour_rate_per_hour=labour_rate,
        consumables_cost=consumables,
        overhead_cost=overhead,
        failure_pct=failure_pct,
        margin_pct=margin_pct,
        pricing_mode=pricing_mode,
        vat_pct=vat_pct,
    )

    filament = _round2(grams * cost_per_g)
    electricity = _round2(print_hours * (power_watts / Decimal(1000)) * tariff)
    depreciation = _round2(print_hours * purchase_price / life_hours)
    labour = _round2((labour_minutes / Decimal(60)) * labour_rate)
    direct = (
        filament + electricity + depreciation + labour + _round2(consumables) + _round2(overhead)
    )
    failure = _round2(direct * failure_pct / Decimal(100))
    true_cost = direct + failure
    if pricing_mode == "margin_on_price":
        price_ex_vat = _round2(true_cost / (Decimal(1) - margin_pct / Decimal(100)))
    else:
        price_ex_vat = _round2(true_cost * (Decimal(1) + margin_pct / Decimal(100)))
    profit = price_ex_vat - true_cost
    vat_amount = _round2(price_ex_vat * vat_pct / Decimal(100))
    price_incl_vat = price_ex_vat + vat_amount

    assert result.filament_cost == filament
    assert result.electricity_cost == electricity
    assert result.depreciation_cost == depreciation
    assert result.labour_cost == labour
    assert result.direct_cost == direct
    assert result.failure_allowance == failure
    assert result.true_cost == true_cost
    assert result.price_ex_vat == price_ex_vat
    assert result.profit == profit
    assert result.vat_amount == vat_amount
    assert result.price_incl_vat == price_incl_vat
