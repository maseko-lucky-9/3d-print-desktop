# ADR-001: PySide6 + qasync for the UI layer

**Date:** 2026-06-26  
**Status:** Accepted

## Context

The app needs a native macOS GUI that can issue async HTTP calls to the backend without
blocking the event loop. Options considered: Tkinter, wxPython, PyQt5, PySide6, Electron.

## Decision

Use **PySide6** (Qt 6 for Python, LGPL) with **qasync** to bridge the Qt and asyncio event
loops. All async work (`httpx`, polling) runs on the shared Qt loop via `asyncio.ensure_future`.

## Rationale

- Qt 6 renders natively on macOS (correct fonts, scrollbars, dark-mode) out of the box.
- PySide6 is the official Qt binding (LGPL) — no commercial-license risk vs PyQt5 (GPL).
- qasync is the de-facto bridge: single event loop, no thread overhead for I/O.
- Tkinter/wxPython lack polished macOS theming without heavy custom work.
- Electron was ruled out — no need to ship a full browser + Node runtime for a LAN tool.

## Consequences

- Requires Python ≥ 3.11 (PySide6 ≥ 6.6 constraint).
- py2app bundle size is larger than a pure-stdlib app (~150 MB with Qt frameworks).
- UI code must never block the Qt main thread; all network calls go through async slots.
