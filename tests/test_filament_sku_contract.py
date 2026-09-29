"""The SKU picker's contract with the backend.

This file exists because nothing asserted it, and as a result the picker never
worked. `FilamentSku` required `name`, `grams_remaining` and `cost_per_gram`
while `GET /api/filaments/skus` returns `display_name`, `available_grams` and
`current_avg_cost_per_g`, so `model_validate` raised on every response. The
exception was caught by a broad `except Exception` in MainWindow._refresh_async
that only logs, so the dropdown was silently empty and every job was saved with
`filament_sku_id=0`.

The payloads below are copied from real backend responses rather than written
from the model, which is the only way a test like this can catch drift — a
fixture derived from the model would agree with the model by construction.
"""

import pytest
from pydantic import ValidationError

from print_desktop.models.print_request import FilamentSku

# Verbatim from GET /api/filaments/skus against the deployed backend.
BACKEND_SKU = {
    "id": 1,
    "material": "PLA",
    "colour": "Black",
    "brand": "Bambu",
    "current_avg_cost_per_g": 0.45,
    "colour_hex": "#1a1a1a",
    "diameter_mm": 1.75,
    "density_g_cm3": 1.24,
    "spool_net_weight_g": 1000.0,
    "supplier": "Filament Warehouse",
    "status": "active",
    "display_name": "Bambu PLA Black",
    "on_hand_grams": 1000.0,
    "available_grams": 872.0,
}


def test_a_real_backend_response_parses():
    sku = FilamentSku.model_validate(BACKEND_SKU)
    assert sku.id == 1
    assert sku.name == "Bambu PLA Black"
    assert sku.color == "Black"
    assert sku.cost_per_gram == 0.45


def test_the_picker_shows_what_can_be_promised_not_what_is_wound_on():
    """grams_remaining maps to available_grams, not on_hand_grams.

    128 g of this spool is reserved for a queued job. Offering the full 1000 g
    would let the operator plan a print against filament that is already spoken
    for.
    """
    sku = FilamentSku.model_validate(BACKEND_SKU)
    assert sku.grams_remaining == 872.0


def test_a_sku_with_no_lots_is_usable():
    """Availability is derived, so a SKU with no stock reports zero rather than
    failing to parse — it should still be selectable."""
    sku = FilamentSku.model_validate(
        {"id": 2, "display_name": "eSun PETG Red", "colour": "Red",
         "current_avg_cost_per_g": 0.0}
    )
    assert sku.name == "eSun PETG Red"
    assert sku.grams_remaining == 0.0
    assert sku.cost_per_gram == 0.0


def test_extra_backend_fields_are_ignored():
    """The backend may add fields; that must never break the client."""
    payload = {**BACKEND_SKU, "something_added_next_release": {"nested": True}}
    assert FilamentSku.model_validate(payload).id == 1


def test_a_response_without_an_id_is_rejected():
    """The one field with no sensible default — it is the picker's userData."""
    payload = {k: v for k, v in BACKEND_SKU.items() if k != "id"}
    with pytest.raises(ValidationError):
        FilamentSku.model_validate(payload)


def test_the_internal_names_still_work():
    """populate_by_name keeps hand-built fixtures and any older payload valid."""
    sku = FilamentSku.model_validate(
        {"id": 3, "name": "Local", "color": "Blue", "grams_remaining": 12.5,
         "cost_per_gram": 0.3}
    )
    assert (sku.name, sku.color, sku.grams_remaining) == ("Local", "Blue", 12.5)
