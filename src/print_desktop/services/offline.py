"""Offline-quote parameter assembly — Phase 6 of the costing-engine plan.

Pure function on purpose, same reasoning as services/drift.py: this is the
sourcing logic most likely to be gotten subtly wrong (cached SKU/printer
lookup, power_watts override-vs-default), so it needs to be unit testable
without a live MainWindow/ApiClient/TOML file.
"""

from decimal import Decimal

from print_desktop.services.cost import InvalidQuoteInput, QuoteBreakdown, calculate_costs


def build_offline_quote(
    params: dict,
    cached_skus: list[dict],
    cached_printers: list[dict],
    cached_electricity_tariff_per_kwh: float,
    cached_labour_rate_per_hour: float,
    cached_pricing_mode: str,
    cached_vat_pct: float,
) -> QuoteBreakdown | None:
    """params is exactly what ManualForm._current_quote_params() produces.
    Returns None if the SKU/printer was never seen while online, or if the
    resulting inputs fail calculate_costs's own validation — either way,
    "no offline quote available" rather than a guess."""
    sku = next((s for s in cached_skus if s["id"] == params["sku_id"]), None)
    printer = next((p for p in cached_printers if p["id"] == params["printer_id"]), None)
    if sku is None or printer is None:
        return None
    power_watts = params["power_watts"] or printer["power_watts_default"]
    try:
        return calculate_costs(
            grams=Decimal(str(params["grams"])),
            cost_per_g=Decimal(str(sku["cost_per_gram"])),
            print_hours=Decimal(str(params["print_hours"])),
            power_watts=Decimal(str(power_watts)),
            electricity_tariff_per_kwh=Decimal(str(cached_electricity_tariff_per_kwh)),
            printer_purchase_price=Decimal(str(printer["purchase_price"])),
            printer_expected_life_hours=Decimal(str(printer["expected_life_hours"])),
            labour_minutes=Decimal(str(params["labour_minutes"])),
            labour_rate_per_hour=Decimal(str(cached_labour_rate_per_hour)),
            consumables_cost=Decimal(str(params["consumables_cost"])),
            overhead_cost=Decimal(str(params["overhead_cost"])),
            failure_pct=Decimal(str(params["failure_pct"])),
            margin_pct=Decimal(str(params["margin_pct"])),
            pricing_mode=cached_pricing_mode,
            vat_pct=Decimal(str(cached_vat_pct)),
        )
    except InvalidQuoteInput:
        return None
