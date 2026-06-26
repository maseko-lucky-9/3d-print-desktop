# ADR-002: No in-app slicing — use BambuStudio GUI for slice preview

**Date:** 2026-06-26  
**Status:** Accepted

## Context

The ideal flow would be: import model → slice in-process → read filament/time estimates
automatically → populate cost fields. Both BambuStudio CLI and OrcaSlicer (stable + nightly)
were spiked for this purpose.

## Decision

**No in-app slicing.** The user reads grams and hours from the BambuStudio GUI preview and
types them into the app manually.

## Rationale

BambuStudio CLI and OrcaSlicer segfault on macOS ARM64 when slicing with P1S profiles.
The crash is a known upstream bug across the entire BambuStudio fork lineage. The spike is
recorded in `~/.claude/plans/i-want-to-change-golden-pine.md §21`. No workaround exists
short of running a remote slicer or waiting for upstream fixes.

## Consequences

- User types two numbers (grams, hours) per job — acceptable for the current print volume.
- If the upstream ARM64 segfault is resolved, slicing can be added as an optional layer;
  the manual-entry fields remain as the fallback.
- No dependency on BambuStudio/OrcaSlicer binaries in the app bundle.
