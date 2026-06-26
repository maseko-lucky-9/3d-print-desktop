# Changelog

All notable changes to this project will be documented in this file. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), Semver.

## [Unreleased]

## [0.1.0] — 2026-05-10

### Added
- Initial release. Manual grams + hours entry, filament SKU picker, live cost panel, project tabs (Printed / Calculated), MakerWorld URL import, send-to-printer.
- ReelSmith-style landing UI ported to Qt (dark zinc palette, rounded inputs, white CTA).
- Bundled homelab CA cert support, no auth (LAN-only backend).
- py2app build script + ad-hoc codesign workflow.
- Crash reporter writing tracebacks to `~/Library/Logs/PrintDesktop/`.

### Known limitations
- No in-app slicing (BambuStudio/OrcaSlicer CLI segfault on macOS ARM64 — see ADR-002; re-spike required).
- Single printer hardcoded via backend env vars.
- macOS only.
