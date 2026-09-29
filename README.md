# 3D Print Desktop

**Problem:** Cost-attribute every 3D print job tied to a real filament SKU + printer hourly + electricity rate, save it to the headless backend's print history, and avoid retyping the same numbers in a browser. Native macOS app, paired with the `print-calc` backend.

## What it does

- Type filament grams + print hours from the BambuStudio GUI preview.
- Pick a filament SKU (FIFO inventory pulled from backend).
- See cost breakdown + suggested selling price live as you type.
- Save → backend creates a `PrintJob` with the cost columns populated.
- "Send to Printer" → backend MQTT-routes to the Bambu P1S.
- View All projects (Printed) + Projects (Calculated) tabs.
- Optional: paste a MakerWorld URL → backend downloads the STL into the model catalogue.

## Why no in-app slicing?

BambuStudio CLI (stable + nightly) segfaults on macOS ARM64 when slicing with P1S profiles. The original spike record no longer exists; a re-spike is needed before this can be resolved. See `docs/decisions/002-no-in-app-slicing.md` for the decision and the re-spike requirements. Until then, slicing happens in the BambuStudio GUI and this app is the cost-calculation + history layer.

## Stack

- PySide6 (Qt for Python) + qasync for async I/O on the Qt event loop
- httpx for the backend API (no auth — backend is LAN-only behind NetworkPolicy)
- pydantic for typed data models
- py2app for the macOS .app bundle
- ad-hoc codesigned for distribution via GitHub Releases

## Setup

```bash
uv sync --all-extras
uv run python -m print_desktop
```

## Test

```bash
uv run pytest
```

## Build .app

```bash
uv run python setup.py py2app
codesign --force --deep --sign - dist/PrintDesktop.app
open dist/PrintDesktop.app
```

## Backend

Companion repo: `git@github.com:maseko-lucky-9/3d-printing-cost-calculator-app.git`.
Default backend URL: `https://print-calc.homelab` (Tailscale only).
