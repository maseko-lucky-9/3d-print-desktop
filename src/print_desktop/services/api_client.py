"""HTTP client for the print-calc backend.

No auth — backend is LAN-only behind a K8s NetworkPolicy (per plan §11 + SECURITY.md).
Single shared httpx.AsyncClient per process, opened at startup, closed at shutdown.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from print_desktop.models.print_request import (
    AppSettings,
    FilamentSku,
    JobPayload,
    MakerWorldImport,
    Printer,
    PrinterStatus,
    PrintJob,
    QuoteResult,
)


class ApiClient:
    def __init__(self, base_url: str, ca_path: Path | None = None, timeout: float = 30.0):
        verify: bool | str = str(ca_path) if ca_path and ca_path.exists() else True
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            verify=verify,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_filament_skus(self) -> list[FilamentSku]:
        r = await self._client.get("/api/filaments/skus")
        r.raise_for_status()
        return [FilamentSku.model_validate(x) for x in r.json()]

    async def list_jobs(self, limit: int = 200) -> list[PrintJob]:
        r = await self._client.get("/api/jobs", params={"limit": limit})
        r.raise_for_status()
        return [PrintJob.model_validate(x) for x in r.json()]

    async def list_history(
        self, limit: int = 200, cursor: int | None = None
    ) -> list[PrintJob]:
        params: dict[str, int] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        r = await self._client.get("/api/jobs/history", params=params)
        r.raise_for_status()
        return [PrintJob.model_validate(x) for x in r.json()]

    async def get_job_thumbnail(self, job_id: int) -> bytes | None:
        r = await self._client.get(f"/api/jobs/{job_id}/thumbnail")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    async def create_job(self, payload: JobPayload) -> PrintJob:
        # Multipart even though no file — backend's create_job is a multipart
        # endpoint. Send all fields as form parts.
        data = {k: str(v) for k, v in payload.model_dump(exclude_none=True).items()}
        r = await self._client.post("/api/jobs", data=data)
        r.raise_for_status()
        return PrintJob.model_validate(r.json())

    async def send_to_printer(self, job_id: int) -> PrintJob:
        r = await self._client.post(f"/api/jobs/{job_id}/send-to-printer")
        r.raise_for_status()
        return PrintJob.model_validate(r.json())

    async def cancel_job(self, job_id: int) -> PrintJob:
        r = await self._client.post(f"/api/jobs/{job_id}/cancel")
        r.raise_for_status()
        return PrintJob.model_validate(r.json())

    async def get_printer_status(self) -> PrinterStatus:
        r = await self._client.get("/api/printer/status")
        r.raise_for_status()
        return PrinterStatus.model_validate(r.json())

    async def get_settings(self) -> AppSettings:
        r = await self._client.get("/api/settings")
        r.raise_for_status()
        return AppSettings.model_validate(r.json())

    async def update_settings(
        self,
        *,
        electricity_tariff_per_kwh: float,
        vat_pct: float,
        labour_rate_per_hour: float,
        pricing_mode: str,
        default_margin_pct: float,
        default_failure_pct: float,
        currency: str,
    ) -> AppSettings:
        # PUT is a full replace — every field is required server-side, so
        # there is no partial-update variant to offer here.
        r = await self._client.put(
            "/api/settings",
            json={
                "electricity_tariff_per_kwh": electricity_tariff_per_kwh,
                "vat_pct": vat_pct,
                "labour_rate_per_hour": labour_rate_per_hour,
                "pricing_mode": pricing_mode,
                "default_margin_pct": default_margin_pct,
                "default_failure_pct": default_failure_pct,
                "currency": currency,
            },
        )
        r.raise_for_status()
        return AppSettings.model_validate(r.json())

    async def list_printers(self, status: str | None = None) -> list[Printer]:
        params = {"status": status} if status is not None else None
        r = await self._client.get("/api/printers", params=params)
        r.raise_for_status()
        return [Printer.model_validate(x) for x in r.json()]

    async def update_printer(
        self,
        printer_id: int,
        *,
        purchase_price: float | None = None,
        expected_life_hours: float | None = None,
    ) -> Printer:
        body = {}
        if purchase_price is not None:
            body["purchase_price"] = purchase_price
        if expected_life_hours is not None:
            body["expected_life_hours"] = expected_life_hours
        r = await self._client.patch(f"/api/printers/{printer_id}", json=body)
        r.raise_for_status()
        return Printer.model_validate(r.json())

    async def quote(
        self,
        *,
        sku_id: int,
        grams: float,
        printer_id: int,
        print_hours: float,
        power_watts: float | None = None,
        labour_minutes: float = 0,
        consumables_cost: float = 0,
        overhead_cost: float = 0,
        failure_pct: float | None = None,
        margin_pct: float | None = None,
    ) -> QuoteResult:
        body: dict = {
            "materials": [{"sku_id": sku_id, "grams": grams}],
            "printer_id": printer_id,
            "print_hours": print_hours,
            "labour_minutes": labour_minutes,
            "consumables_cost": consumables_cost,
            "overhead_cost": overhead_cost,
        }
        if power_watts is not None:
            body["power_watts"] = power_watts
        if failure_pct is not None:
            body["failure_pct"] = failure_pct
        if margin_pct is not None:
            body["margin_pct"] = margin_pct
        r = await self._client.post("/api/quote", json=body)
        r.raise_for_status()
        return QuoteResult.model_validate(r.json())

    async def import_makerworld(self, url: str) -> MakerWorldImport:
        r = await self._client.post("/api/makerworld/import", json={"url": url})
        r.raise_for_status()
        return MakerWorldImport.model_validate(r.json())

    async def poll_makerworld_import(self, import_id: int) -> MakerWorldImport:
        r = await self._client.get(f"/api/makerworld/import/{import_id}")
        r.raise_for_status()
        return MakerWorldImport.model_validate(r.json())


async def wait_for_makerworld(
    client: ApiClient,
    import_id: int,
    on_status: Callable[[str], Awaitable[None]] | None = None,
    timeout_seconds: int = 60,
    poll_interval_seconds: float = 2.0,
) -> MakerWorldImport:
    """Poll an in-flight makerworld import until success/failed or timeout."""
    import asyncio

    elapsed = 0.0
    while elapsed < timeout_seconds:
        result = await client.poll_makerworld_import(import_id)
        if on_status:
            await on_status(result.status)
        if result.status in ("success", "failed"):
            return result
        await asyncio.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds
    raise TimeoutError(f"MakerWorld import {import_id} did not finish in {timeout_seconds}s")
