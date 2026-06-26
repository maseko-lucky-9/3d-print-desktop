# 3D Print Desktop — CLAUDE.md

## Problem statement
Cost-attribute every 3D print job tied to a real filament SKU + printer hourly + electricity
rate, save it to the `print-calc` backend, and avoid retyping the same numbers in a browser.

## Stack
- **Language:** Python 3.11–3.12
- **UI:** PySide6 (Qt 6) + qasync (Qt ↔ asyncio bridge)
- **HTTP:** httpx.AsyncClient (single shared instance per process)
- **Models:** Pydantic v2
- **Build:** py2app + ad-hoc codesign (`codesign --sign -`)
- **Package manager:** uv (`uv sync --all-extras`)

## Entry points
- `src/print_desktop/__main__.py` — app entry (`uv run python -m print_desktop`)
- `src/print_desktop/ui/main_window.py` — top-level `QMainWindow`
- `src/print_desktop/services/api_client.py` — all backend HTTP calls

## Build & run
```bash
uv sync --all-extras           # install deps
uv run python -m print_desktop # run dev

uv run pytest                  # tests

uv run python setup.py py2app  # build .app
codesign --force --deep --sign - "dist/3D Print Desktop.app"
```

## Backend
Companion repo: `git@github.com:maseko-lucky-9/3d-printing-cost-calculator-app.git`
Default URL: `https://print-calc.homelab` (Tailscale-only, no auth — see ADR-003)

## Architecture decisions
All ADRs live in `docs/decisions/`. Key decisions:
- **ADR-001** PySide6 + qasync (not Tkinter/Electron)
- **ADR-002** No in-app slicing (ARM64 segfault in BambuStudio CLI)
- **ADR-003** No app-layer auth (LAN-only, Tailscale + K8s NetworkPolicy)
- **ADR-004** Single shared httpx.AsyncClient per process
- **ADR-005** py2app + ad-hoc codesign for distribution
- **ADR-006** Backend-delegated MQTT for "Send to Printer"

## Constraints
- Python ≥ 3.11 < 3.13 (PySide6 requirement)
- All network calls must run on the Qt/asyncio event loop — never block the main thread
- No secrets in source or git — credentials live on the backend only
- macOS ARM64 only (no Windows/Linux target)
