"""Settings persistence — TOML in ~/Library/Application Support/PrintDesktop/.

Per plan §16 L_2.4: schema is versioned (`schema_version` field). Bump on
breaking changes; provide migration in this module.
"""

import tomllib
from dataclasses import asdict, dataclass, field
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

    # Window state (managed by MainWindow)
    window_geometry: str = ""  # base64-encoded QByteArray

    # Onboarding
    onboarded: bool = False

    # Phase 6 of the costing-engine plan: the last-good pricing context,
    # cached here purely for offline quoting (MainWindow._try_offline_quote)
    # — never read to prefill any Settings-tab or ManualForm input, and
    # never written except right after a real GET /api/settings /
    # GET /api/printers / GET /api/filaments/skus succeeds. cached_at empty
    # means "never successfully cached" — offline quoting is refused in that
    # case rather than guessing from the dataclass's own bare defaults below.
    cached_at: str = ""  # ISO timestamp of the cache write
    cached_pricing_mode: str = ""
    cached_default_margin_pct: float = 0.0
    cached_vat_pct: float = 0.0
    cached_labour_rate_per_hour: float = 0.0
    cached_electricity_tariff_per_kwh: float = 0.0
    cached_default_failure_pct: float = 0.0
    # [{id, name, power_watts_default, purchase_price, expected_life_hours}]
    cached_printers: list = field(default_factory=list)
    # [{id, name, color, cost_per_gram}]
    cached_skus: list = field(default_factory=list)


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
    v3 (Phase 6): added cached_* fields for offline quoting. Also purely
    additive — a v2 file simply lacks these keys, and the dataclass defaults
    (all empty/zero) correctly read as "nothing cached yet."
    """
    raw.setdefault("schema_version", 1)
    # Drop unknown fields to stay forward-compatible.
    known_fields = {f.name for f in Settings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in raw.items() if k in known_fields}
    return Settings(**filtered)
