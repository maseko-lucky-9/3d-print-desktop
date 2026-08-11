"""Settings persistence — TOML in ~/Library/Application Support/PrintDesktop/.

Per plan §16 L_2.4: schema is versioned (`schema_version` field). Bump on
breaking changes; provide migration in this module.
"""

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import tomli_w

CURRENT_SCHEMA_VERSION = 2
SETTINGS_DIR = Path.home() / "Library" / "Application Support" / "PrintDesktop"
SETTINGS_PATH = SETTINGS_DIR / "settings.toml"


@dataclass
class Settings:
    schema_version: int = CURRENT_SCHEMA_VERSION

    # Backend
    backend_url: str = "https://print-calc.homelab"
    ca_cert_path: str = ""  # bundled with .app; resolved at runtime

    # Window state (managed by MainWindow)
    window_geometry: str = ""  # base64-encoded QByteArray

    # Onboarding
    onboarded: bool = False


def load() -> Settings:
    """Load settings, returning defaults if file missing or unreadable."""
    if not SETTINGS_PATH.exists():
        return Settings()
    try:
        with SETTINGS_PATH.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return Settings()
    return _migrate_and_construct(raw)


def save(s: Settings) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    s.schema_version = CURRENT_SCHEMA_VERSION
    with SETTINGS_PATH.open("wb") as f:
        tomli_w.dump(asdict(s), f)


def _migrate_and_construct(raw: dict) -> Settings:
    """Apply schema migrations then construct a Settings object.

    v1: initial schema.
    v2 (Phase 5 of the costing-engine plan): dropped electricity_rate,
    power_watts, printer_hourly_cost, profit_margin_pct, filament_size_g and
    filament_price. Those rates now live server-side (GET/PUT /api/settings,
    the printers API) so every client quotes off the same numbers — see the
    module docstring. No explicit migration code is needed for the removal
    itself: the existing known-fields filter below already drops any key
    that isn't a current dataclass field, which is exactly what a v1 TOML
    file full of now-obsolete rate keys needs to happen to it.
    """
    raw.setdefault("schema_version", 1)
    # Drop unknown fields to stay forward-compatible.
    known_fields = {f.name for f in Settings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in raw.items() if k in known_fields}
    return Settings(**filtered)
