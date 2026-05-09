"""Cost math tests — same shape as backend's tests/test_calculator.py plus
property tests per plan §18 T3 (no negative results from non-negative inputs)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from print_desktop.services.cost import calculate_costs


def test_known_breakdown():
    r = calculate_costs(
        filament_size=1000,  # 1 kg spool
        filament_price=300.0,  # R 300 per kg
        filament_used=50.0,  # 50 g
        total_print_hours=2.0,
        electricity_rate=2.5,  # R 2.50 per kWh
        power_watts=200,
        printer_hourly_cost=5.0,
        profit_margin_pct=50.0,
    )
    assert r["filament_cost"] == pytest.approx(15.0)  # 50/1000 * 300
    assert r["electricity_cost"] == pytest.approx(1.0)  # 2 * 0.2 * 2.5
    assert r["printer_usage_cost"] == pytest.approx(10.0)  # 2 * 5
    assert r["total_cost"] == pytest.approx(26.0)
    assert r["profit"] == pytest.approx(13.0)
    assert r["selling_price"] == pytest.approx(39.0)


def test_filament_size_must_be_positive():
    with pytest.raises(ValueError, match="filament_size must be positive"):
        calculate_costs(
            filament_size=0,
            filament_price=300,
            filament_used=50,
            total_print_hours=1,
            electricity_rate=2.5,
            power_watts=200,
            printer_hourly_cost=5,
            profit_margin_pct=50,
        )


def test_zero_margin_means_selling_equals_total():
    r = calculate_costs(
        filament_size=1000,
        filament_price=300,
        filament_used=50,
        total_print_hours=2,
        electricity_rate=2.5,
        power_watts=200,
        printer_hourly_cost=5,
        profit_margin_pct=0,
    )
    assert r["selling_price"] == pytest.approx(r["total_cost"])
    assert r["profit"] == 0


@given(
    filament_size=st.floats(min_value=0.01, max_value=10_000, allow_nan=False),
    filament_price=st.floats(min_value=0, max_value=10_000, allow_nan=False),
    filament_used=st.floats(min_value=0, max_value=10_000, allow_nan=False),
    total_print_hours=st.floats(min_value=0, max_value=1000, allow_nan=False),
    electricity_rate=st.floats(min_value=0, max_value=100, allow_nan=False),
    power_watts=st.floats(min_value=0, max_value=10_000, allow_nan=False),
    printer_hourly_cost=st.floats(min_value=0, max_value=1000, allow_nan=False),
    profit_margin_pct=st.floats(min_value=0, max_value=1000, allow_nan=False),
)
@settings(max_examples=200, deadline=None)
def test_non_negative_inputs_produce_non_negative_costs(
    filament_size,
    filament_price,
    filament_used,
    total_print_hours,
    electricity_rate,
    power_watts,
    printer_hourly_cost,
    profit_margin_pct,
):
    r = calculate_costs(
        filament_size=filament_size,
        filament_price=filament_price,
        filament_used=filament_used,
        total_print_hours=total_print_hours,
        electricity_rate=electricity_rate,
        power_watts=power_watts,
        printer_hourly_cost=printer_hourly_cost,
        profit_margin_pct=profit_margin_pct,
    )
    for k, v in r.items():
        assert v >= 0, f"{k} went negative: {v}"
    # total_cost is sum of components — sanity invariant
    assert r["total_cost"] == pytest.approx(
        r["filament_cost"] + r["electricity_cost"] + r["printer_usage_cost"]
    )
    # selling = total + profit
    assert r["selling_price"] == pytest.approx(r["total_cost"] + r["profit"])
