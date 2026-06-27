"""Settings persistence — TOML in ~/Library/Application Support/PrintDesktop/.

Per plan §16 L_2.4: schema is versioned (`schema_version` field). Bump on
breaking changes; provide migration in this module.
"""

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import tomli_w

CURRENT_SCHEMA_VERSION = 3
SETTINGS_DIR = Path.home() / "Library" / "Application Support" / "PrintDesktop"
SETTINGS_PATH = SETTINGS_DIR / "settings.toml"


@dataclass
class Settings:
    schema_version: int = CURRENT_SCHEMA_VERSION

    # Backend
    backend_url: str = "https://print-calc.homelab"
    ca_cert_path: str = ""  # bundled with .app; resolved at runtime
    makerworld_session_cookie: str = ""  # MakerWorld browser session cookie for model imports

    # Cost defaults (user can override per job in the Workflow form)
    electricity_rate: float = 2.50  # R per kWh
    power_watts: float = 200.0
    printer_hourly_cost: float = 5.00  # depreciation per hour
    profit_margin_pct: float = 50.0

    # Filament defaults (also overridable per job)
    filament_size_g: float = 1000.0  # standard 1 kg spool
    filament_price: float = 300.0  # default cost per spool

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

    v1: initial schema (this version). No migrations yet.
    """
    raw.setdefault("schema_version", 1)
    # v1 -> v2: api_token existed briefly; unknown-field filtering now drops it.
    if raw["schema_version"] < 2:
        raw["schema_version"] = 2
    # v2 -> v3: makerworld_session_cookie added
    if raw["schema_version"] < 3:
        raw.setdefault("makerworld_session_cookie", "")
        raw["schema_version"] = 3
    # Drop unknown fields to stay forward-compatible.
    known_fields = {f.name for f in Settings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in raw.items() if k in known_fields}
    return Settings(**filtered)
