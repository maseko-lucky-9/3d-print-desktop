"""HTTP client for the print-calc backend.

No auth — backend is LAN-only behind a K8s NetworkPolicy (per plan §11 + SECURITY.md).
Single shared httpx.AsyncClient per process, opened at startup, closed at shutdown.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from print_desktop.models.print_request import (
    FilamentSku,
    JobPayload,
    MakerWorldImport,
    PrinterStatus,
    PrintJob,
)


class ApiClient:
    def __init__(
        self,
        base_url: str,
        ca_path: Path | None = None,
        timeout: float = 30.0,
        makerworld_session_cookie: str = "",
    ):
        import os
        import warnings

        # ponytail: dev-only escape hatch for mismatched ingress SAN;
        # never active in optimised builds.
        if __debug__ and os.getenv("PRINT_DESKTOP_SKIP_TLS_VERIFY"):
            warnings.warn(
                "PRINT_DESKTOP_SKIP_TLS_VERIFY is set — TLS verification DISABLED. "
                "Fix the backend cert SAN before deploying.",
                stacklevel=2,
            )
            verify: bool | str = False
        else:
            verify = str(ca_path) if ca_path and ca_path.exists() else True
        self._base_url = base_url.rstrip("/")
        self._verify = verify
        self._timeout = timeout
        self._mw_cookie = makerworld_session_cookie
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            verify=self._verify,
            timeout=self._timeout,
        )

    def set_makerworld_cookie(self, cookie: str) -> None:
        self._mw_cookie = cookie

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

    async def import_makerworld(self, url: str) -> MakerWorldImport:
        payload: dict = {"url": url, "session_cookie": self._mw_cookie or ""}
        r = await self._client.post("/api/makerworld/import", json=payload)
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
