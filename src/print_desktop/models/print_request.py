"""Pydantic models for what we POST to the backend.

Mirrors the backend's `POST /api/jobs` schema (Stream A reshaped this — the new
schema accepts cost columns directly instead of a calculation_id reference).
We hand-mirror it here for now; once Stream A is merged, regenerate from the
backend's openapi.json via datamodel-code-generator (per plan §16 C2)."""


from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class FilamentSku(BaseModel):
    """A filament SKU as `GET /api/filaments/skus` actually returns it.

    THIS MODEL DID NOT MATCH THE API AND NEVER HAS. It required `name`,
    `grams_remaining` and `cost_per_gram`; the backend returns `display_name`,
    `available_grams` and `current_avg_cost_per_g`. `model_validate` raised
    ValidationError on every response, and `MainWindow._refresh_async` catches
    Exception broadly and only logs — so the SKU dropdown was silently empty and
    every job went out with `filament_sku_id=0` via the `or 0` fallback in
    ManualCostForm. Nothing surfaced it because nothing asserted it.

    Fixed with validation aliases rather than by renaming the attributes: the
    widgets read `sku.name` / `sku.color` / `sku.cost_per_gram`, and the point of
    this change is to make the picker work, not to churn the UI.

    Defaults on the numeric fields because they are derived server-side and a
    SKU with no lots legitimately reports nothing.

    The long-term fix is still the one the module docstring describes —
    generate this from the backend's openapi.json — which is what would have
    caught the mismatch the day it appeared.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: int
    # "brand material colour", assembled by the backend so both clients agree.
    name: str = Field(validation_alias=AliasChoices("display_name", "name"))
    color: str | None = Field(default=None, validation_alias=AliasChoices("colour", "color"))
    # On-hand minus outstanding reservations — what this spool can actually be
    # promised for, not merely what is physically wound on it.
    grams_remaining: float = Field(
        default=0.0, validation_alias=AliasChoices("available_grams", "grams_remaining")
    )
    cost_per_gram: float = Field(
        default=0.0, validation_alias=AliasChoices("current_avg_cost_per_g", "cost_per_gram")
    )


class JobPayload(BaseModel):
    """What we POST to /api/jobs (url-encoded form; cost columns are form fields).

    Option E (ADR-002): we don't upload a sliced_file — the user slices in
    BambuStudio GUI and sends to printer separately. We're recording the cost
    intent against a filament SKU, not registering a sliced artifact.

    Phase 5 of the costing-engine plan: every cost field below is a frozen
    value taken verbatim from the last `POST /api/quote` response (plus
    labour_rate/vat_pct/pricing_mode from GET /api/settings, which the quote
    response doesn't echo) — never recomputed locally. The legacy
    filament_size/electricity_rate/printer_hourly_cost/profit_margin_pct
    fields are gone: the server-side engine prices off a real printer row
    and the SKU's FIFO/weighted-average cost, not a client-guessed rate, so
    there is nothing left for those four to carry. power_watts survives —
    it's still a live input to electricity_cost server-side, and the quote
    response already echoes back the exact wattage it was resolved to
    (either the form's override or the printer's own default).
    """

    filament_sku_id: int
    printer_id: int | None = None
    model_id: int | None = None
    slicer_grams: float = Field(..., ge=0)
    slicer_seconds: int = Field(..., ge=0)

    power_watts: float | None = Field(default=None, ge=0)
    filament_price: float | None = Field(default=None, ge=0)
    filament_cost: float | None = Field(default=None, ge=0)
    electricity_cost: float | None = Field(default=None, ge=0)
    printer_usage_cost: float | None = Field(default=None, ge=0)
    labour_minutes: float | None = Field(default=None, ge=0)
    labour_rate: float | None = Field(default=None, ge=0)
    consumables_cost: float | None = Field(default=None, ge=0)
    overhead_cost: float | None = Field(default=None, ge=0)
    failure_pct: float | None = Field(default=None, ge=0)
    direct_cost: float | None = Field(default=None, ge=0)
    total_cost: float | None = Field(default=None, ge=0)
    profit: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    vat_pct: float | None = Field(default=None, ge=0)
    price_incl_vat: float | None = Field(default=None, ge=0)
    pricing_mode: str | None = None

    notes: str | None = None


class AppSettings(BaseModel):
    """GET/PUT /api/settings — shop-wide pricing policy, not per-client."""

    id: int
    electricity_tariff_per_kwh: float
    vat_pct: float
    labour_rate_per_hour: float
    pricing_mode: str
    default_margin_pct: float
    default_failure_pct: float
    currency: str
    updated_at: str | None = None


class Printer(BaseModel):
    """GET/POST/PATCH /api/printers."""

    id: int
    name: str
    power_watts_default: float
    purchase_price: float
    expected_life_hours: float
    depreciation_per_hour: float
    status: str
    created_at: str | None = None


class QuoteMaterialLine(BaseModel):
    sku_id: int
    grams: float
    cost_per_g: float
    line_cost: float


class QuoteResult(BaseModel):
    """POST /api/quote response — every derived cost/price line."""

    material_lines: list[QuoteMaterialLine]
    filament_cost: float
    electricity_cost: float
    depreciation_cost: float
    labour_cost: float
    direct_cost: float
    failure_allowance: float
    true_cost: float
    price_ex_vat: float
    profit: float
    margin_pct_actual: float
    vat_amount: float
    price_incl_vat: float
    pricing_mode: str
    margin_pct: float
    failure_pct: float
    vat_pct: float
    power_watts: float


class PrintJob(BaseModel):
    """What the backend returns. Subset of fields we render in project cards."""

    id: int
    state: str  # sliced | queued | printing | done | failed | cancelled
    filament_sku_id: int | None = None
    model_id: int | None = None
    slicer_grams: float | None = None
    slicer_seconds: int | None = None
    total_cost: float | None = None
    selling_price: float | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    # The backend has always returned this; the model just never declared it,
    # so pydantic's default extra="ignore" dropped it and ProjectCard._title_for
    # raised AttributeError on every card render. Cards are the home grid, so
    # the whole Projects view came up empty in the packaged app.
    notes: str | None = None


class PrinterStatus(BaseModel):
    online: bool = False
    gcode_state: str = "UNKNOWN"
    percentage: float | None = None
    remaining_time: int | None = None
    nozzle_temp: float | None = None
    bed_temp: float | None = None
    current_layer: int | None = None
    total_layers: int | None = None


class MakerWorldImport(BaseModel):
    id: int
    url: str
    status: str  # pending | success | failed
    model_id: int | None = None
    error_message: str | None = None
