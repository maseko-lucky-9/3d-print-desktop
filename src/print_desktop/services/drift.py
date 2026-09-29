"""Runtime drift detector — Phase 6 of the costing-engine plan.

Compares a server-computed QuoteResult against a locally-computed
QuoteBreakdown (services/cost.py, given the same resolved inputs — see
MainWindow._detect_drift for how those inputs are assembled) and reports the
first field that disagrees. This — not the committed golden vectors — is the
actual guarantee behind "the offline calculator won't silently drift from
the server": it runs on every live quote, against real inputs, not just a
handful of committed cases.

A pure function on purpose: the two money formulas are the highest-risk part
of this plan, so the comparator that watches them needs to be testable
without any Qt/network machinery, not just exercised incidentally through a
live app.
"""

from decimal import Decimal

from print_desktop.models.print_request import Printer, QuoteResult
from print_desktop.services.cost import InvalidQuoteInput, QuoteBreakdown, calculate_costs

# Every field name below is identical on both QuoteResult and QuoteBreakdown
# (depreciation_cost only becomes printer_usage_cost once it lands on a
# PrintJob/JobPayload — the two quote-shaped objects compared here agree).
_FIELDS = [
    "filament_cost",
    "electricity_cost",
    "depreciation_cost",
    "labour_cost",
    "direct_cost",
    "failure_allowance",
    "true_cost",
    "price_ex_vat",
    "profit",
    "vat_amount",
    "price_incl_vat",
]

# Tolerance for float (server, JSON-decoded) vs float(Decimal) (local)
# comparison — well under a cent, so this only absorbs binary-float noise,
# never a genuine cent-level disagreement.
_TOLERANCE = 0.005


def find_drift(server: QuoteResult, local: QuoteBreakdown) -> str | None:
    """Returns a short description of the first field that disagrees, or
    None if every field matches to the cent."""
    for field in _FIELDS:
        server_value = getattr(server, field)
        local_value = float(getattr(local, field))
        if abs(server_value - local_value) > _TOLERANCE:
            return f"{field}: server={server_value:.2f} local={local_value:.2f}"
    return None


def build_local_recompute(
    result: QuoteResult,
    params: dict,
    printer: Printer,
    electricity_tariff_per_kwh: float,
    labour_rate_per_hour: float,
) -> QuoteBreakdown | None:
    """Recomputes the same quote locally for comparison against `result`.

    Deliberately mixes three different sources, and getting this wrong is
    the easiest way for this whole phase to become useless:
      - cost_per_g and grams come from `result.material_lines[0]` — the
        server-resolved FIFO/weighted-average rate, which the client can
        never independently know, so using anything else here would make
        every quote "drift" by construction.
      - power_watts/margin_pct/failure_pct/vat_pct/pricing_mode come from
        `result`'s own echo, not `params` — the server may have defaulted
        any of these from settings when the request omitted them, and
        comparing against the raw (possibly-omitted) request value would
        produce false drift on every quote that relied on a server default.
      - print_hours/labour_minutes/consumables_cost/overhead_cost come from
        `params` — pure pass-through values the server never resolves or
        defaults, so the original request value IS what the server used.
      - printer purchase_price/expected_life_hours and the tariff/labour
        rate come from the caller's own cached/known values — genuinely not
        present anywhere in the response.
    """
    material = result.material_lines[0]
    try:
        return calculate_costs(
            grams=Decimal(str(material.grams)),
            cost_per_g=Decimal(str(material.cost_per_g)),
            print_hours=Decimal(str(params["print_hours"])),
            power_watts=Decimal(str(result.power_watts)),
            electricity_tariff_per_kwh=Decimal(str(electricity_tariff_per_kwh)),
            printer_purchase_price=Decimal(str(printer.purchase_price)),
            printer_expected_life_hours=Decimal(str(printer.expected_life_hours)),
            labour_minutes=Decimal(str(params["labour_minutes"])),
            labour_rate_per_hour=Decimal(str(labour_rate_per_hour)),
            consumables_cost=Decimal(str(params["consumables_cost"])),
            overhead_cost=Decimal(str(params["overhead_cost"])),
            failure_pct=Decimal(str(result.failure_pct)),
            margin_pct=Decimal(str(result.margin_pct)),
            pricing_mode=result.pricing_mode,
            vat_pct=Decimal(str(result.vat_pct)),
        )
    except InvalidQuoteInput:
        return None
