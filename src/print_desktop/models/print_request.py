"""Pydantic models for what we POST to the backend.

Mirrors the backend's `POST /api/jobs` schema (Stream A reshaped this — the new
schema accepts cost columns directly instead of a calculation_id reference).
We hand-mirror it here for now; once Stream A is merged, regenerate from the
backend's openapi.json via datamodel-code-generator (per plan §16 C2)."""


from pydantic import BaseModel, Field


class FilamentSku(BaseModel):
    id: int
    name: str
    color: str | None = None
    grams_remaining: float
    cost_per_gram: float


class JobPayload(BaseModel):
    """What we POST to /api/jobs (multipart-encoded; cost columns are form fields).

    Option E (ADR-002): we don't upload a sliced_file — the user slices in
    BambuStudio GUI and sends to printer separately. We're recording the cost
    intent against a filament SKU, not registering a sliced artifact.
    """

    filament_sku_id: int
    model_id: int | None = None
    slicer_grams: float = Field(..., ge=0)
    slicer_seconds: int = Field(..., ge=0)

    # Cost inputs (echoed for traceability — backend recomputes for validation)
    filament_size: float = Field(..., gt=0)
    filament_price: float = Field(..., ge=0)
    electricity_rate: float = Field(..., ge=0)
    power_watts: float = Field(..., ge=0)
    printer_hourly_cost: float = Field(..., ge=0)
    profit_margin_pct: float = Field(..., ge=0)

    # Cost outputs (computed locally via services.cost.calculate_costs)
    filament_cost: float = Field(..., ge=0)
    electricity_cost: float = Field(..., ge=0)
    printer_usage_cost: float = Field(..., ge=0)
    total_cost: float = Field(..., ge=0)
    profit: float = Field(..., ge=0)
    selling_price: float = Field(..., ge=0)

    notes: str | None = None


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
