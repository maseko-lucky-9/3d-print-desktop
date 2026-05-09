"""Pure cost math. Verbatim port of backend/calculator.py — kept identical so
backend-side validation (which recomputes total_cost and rejects mismatches >1%)
will accept what we POST."""

from typing import TypedDict


class CostBreakdown(TypedDict):
    filament_cost: float
    electricity_cost: float
    printer_usage_cost: float
    total_cost: float
    profit: float
    selling_price: float


def calculate_costs(
    filament_size: float,
    filament_price: float,
    filament_used: float,
    total_print_hours: float,
    electricity_rate: float,
    power_watts: float,
    printer_hourly_cost: float,
    profit_margin_pct: float,
) -> CostBreakdown:
    if filament_size <= 0:
        raise ValueError(f"filament_size must be positive, got {filament_size}")
    filament_cost = (filament_used / filament_size) * filament_price
    electricity_cost = total_print_hours * (power_watts / 1000) * electricity_rate
    printer_usage_cost = total_print_hours * printer_hourly_cost
    total_cost = filament_cost + electricity_cost + printer_usage_cost
    profit = total_cost * (profit_margin_pct / 100)
    selling_price = total_cost + profit
    return {
        "filament_cost": filament_cost,
        "electricity_cost": electricity_cost,
        "printer_usage_cost": printer_usage_cost,
        "total_cost": total_cost,
        "profit": profit,
        "selling_price": selling_price,
    }
