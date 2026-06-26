# ADR-005: py2app + ad-hoc codesign for macOS distribution

**Date:** 2026-06-26  
**Status:** Accepted

## Context

The app needs to ship as a macOS `.app` bundle. Options: py2app, PyInstaller, Briefcase,
Nuitka, or a plain script launcher.

## Decision

Use **py2app** to build the bundle; sign with `codesign --sign -` (ad-hoc, no Apple
Developer ID). Distribute via GitHub Releases as a `.dmg` / zipped `.app`.

## Rationale

- py2app is the most mature Python → macOS `.app` tool with known PySide6 support.
- Ad-hoc signing (`-` identity) satisfies Gatekeeper's basic requirement on the local machine
  without a paid Apple Developer account ($99/yr not justified for a single-user tool).
- PyInstaller produces a single-file binary but has worse Qt-framework support on ARM64.
- Briefcase is higher-level and adds abstraction cost for a project that already has
  `pyproject.toml`-driven build config.

## Consequences

- Users who download from GitHub Releases must right-click → Open to bypass Gatekeeper
  the first time (ad-hoc apps are not notarized).
- If distribution widens beyond the home lab, a proper Developer ID + notarization is the
  upgrade path — replace `--sign -` with the team ID and add `xcrun notarytool`.
- Bundle size is ~150 MB due to Qt frameworks; acceptable for a desktop tool.
