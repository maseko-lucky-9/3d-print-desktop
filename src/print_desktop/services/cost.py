"""Pure cost math — Decimal, mirroring backend/costing/engine.py exactly.

Phase 6 of the costing-engine plan: this is the offline/drift-detection twin
of the server's engine, not the pre-Phase-5 local calculator (that formula
computed something markup-shaped with no VAT/labour/failure/consumables/
overhead terms, and is gone). Every rounding point here mirrors the server's
exactly — one q_money() per named subtotal, at the same point the spec names
it, never an extra intermediate one — because a different rounding order
would silently drift from the server on inputs that don't happen to round
cleanly. That exact bug (an extra intermediate round on printer depreciation)
was caught in the backend engine's own adversarial review; this file must
not reintroduce it independently.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

HUNDRED = Decimal("100")
SIXTY = Decimal("60")
THOUSAND = Decimal("1000")


def q_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class InvalidQuoteInput(ValueError):  # noqa: N818 — name matches backend.costing.engine's exactly
    """Mirrors backend.costing.engine.InvalidQuoteInput."""


@dataclass(frozen=True)
class QuoteBreakdown:
    filament_cost: Decimal
    electricity_cost: Decimal
    depreciation_cost: Decimal
    labour_cost: Decimal
    direct_cost: Decimal
    failure_allowance: Decimal
    true_cost: Decimal
    price_ex_vat: Decimal
    profit: Decimal
    margin_pct_actual: Decimal
    vat_amount: Decimal
    price_incl_vat: Decimal


def calculate_costs(
    *,
    grams: Decimal,
    cost_per_g: Decimal,
    print_hours: Decimal,
    power_watts: Decimal,
    electricity_tariff_per_kwh: Decimal,
    printer_purchase_price: Decimal,
    printer_expected_life_hours: Decimal,
    labour_minutes: Decimal,
    labour_rate_per_hour: Decimal,
    consumables_cost: Decimal,
    overhead_cost: Decimal,
    failure_pct: Decimal,
    margin_pct: Decimal,
    pricing_mode: str,
    vat_pct: Decimal,
) -> QuoteBreakdown:
    if pricing_mode not in ("margin_on_price", "markup_on_cost"):
        raise InvalidQuoteInput(f"unknown pricing_mode {pricing_mode!r}")
    if pricing_mode == "margin_on_price" and margin_pct >= HUNDRED:
        raise InvalidQuoteInput(
            "margin_pct must be < 100 when pricing_mode is margin_on_price "
            "(1 - M/100 must not reach zero)"
        )
    if margin_pct < 0:
        raise InvalidQuoteInput("margin_pct must be >= 0")
    if failure_pct < 0:
        raise InvalidQuoteInput("failure_pct must be >= 0")
    if print_hours <= 0:
        raise InvalidQuoteInput("print_hours must be > 0")
    if printer_expected_life_hours <= 0:
        raise InvalidQuoteInput("printer's expected_life_hours must be > 0")

    filament_cost = q_money(grams * cost_per_g)
    electricity_cost = q_money(
        print_hours * (power_watts / THOUSAND) * electricity_tariff_per_kwh
    )
    # round2(H x (P/L)) is ONE expression — see the backend engine's own
    # comment on this exact line for why an intermediate round on P/L alone
    # silently disagrees whenever P/L doesn't terminate within a few places.
    depreciation_cost = q_money(
        print_hours * printer_purchase_price / printer_expected_life_hours
    )
    labour_cost = q_money((labour_minutes / SIXTY) * labour_rate_per_hour)
    consumables = q_money(consumables_cost)
    overhead = q_money(overhead_cost)

    direct_cost = (
        filament_cost + electricity_cost + depreciation_cost + labour_cost + consumables + overhead
    )
    failure_allowance = q_money(direct_cost * failure_pct / HUNDRED)
    true_cost = direct_cost + failure_allowance

    if pricing_mode == "margin_on_price":
        price_ex_vat = q_money(true_cost / (Decimal(1) - margin_pct / HUNDRED))
    else:
        price_ex_vat = q_money(true_cost * (Decimal(1) + margin_pct / HUNDRED))

    profit = price_ex_vat - true_cost
    margin_pct_actual = (
        q_money(profit / price_ex_vat * HUNDRED) if price_ex_vat != 0 else Decimal("0")
    )
    vat_amount = q_money(price_ex_vat * vat_pct / HUNDRED)
    price_incl_vat = price_ex_vat + vat_amount

    return QuoteBreakdown(
        filament_cost=filament_cost,
        electricity_cost=electricity_cost,
        depreciation_cost=depreciation_cost,
        labour_cost=labour_cost,
        direct_cost=direct_cost,
        failure_allowance=failure_allowance,
        true_cost=true_cost,
        price_ex_vat=price_ex_vat,
        profit=profit,
        margin_pct_actual=margin_pct_actual,
        vat_amount=vat_amount,
        price_incl_vat=price_incl_vat,
    )
