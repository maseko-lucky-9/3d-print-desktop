"""Settings round-trip + migration tests."""

import tomllib
from pathlib import Path

from print_desktop.storage import settings as settings_module
from print_desktop.storage.settings import Settings, load, save


def test_defaults_load_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    s = load()
    assert s.backend_url == "https://print-calc.homelab"
    assert s.onboarded is False
    assert s.schema_version == 3


def test_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    s = Settings(backend_url="https://test.local", onboarded=True)
    save(s)
    loaded = load()
    assert loaded.backend_url == "https://test.local"
    assert loaded.onboarded is True


def test_unknown_fields_in_toml_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    p: Path = tmp_path / "settings.toml"
    p.write_text(
        'schema_version = 1\nbackend_url = "x"\nfuture_field = "tolerated"\n', encoding="utf-8"
    )
    s = load()  # must not raise on unknown future_field
    assert s.backend_url == "x"


def test_v1_toml_with_removed_rate_fields_loads_and_drops_them(tmp_path, monkeypatch):
    """Phase 5 (costing-engine plan) dropped electricity_rate/power_watts/
    printer_hourly_cost/profit_margin_pct/filament_size_g/filament_price from
    the local schema — an existing v1 file written by a pre-Phase-5 build
    still has them on disk. Loading it must not raise, and the now-obsolete
    values must simply not resurface on the constructed Settings object."""
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    p: Path = tmp_path / "settings.toml"
    p.write_text(
        "schema_version = 1\n"
        'backend_url = "https://print-calc.homelab"\n'
        "electricity_rate = 2.50\n"
        "power_watts = 200.0\n"
        "printer_hourly_cost = 5.00\n"
        "profit_margin_pct = 50.0\n"
        "filament_size_g = 1000.0\n"
        "filament_price = 300.0\n",
        encoding="utf-8",
    )
    s = load()  # must not raise TypeError on the now-unknown kwargs
    assert not hasattr(s, "electricity_rate")
    assert not hasattr(s, "profit_margin_pct")
    assert s.backend_url == "https://print-calc.homelab"


def test_corrupt_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    (tmp_path / "settings.toml").write_text("not valid toml @@@\n", encoding="utf-8")
    s = load()
    assert s.backend_url == "https://print-calc.homelab"  # default


def test_cached_pricing_context_round_trips(tmp_path, monkeypatch):
    """Phase 6: the offline-quoting cache includes nested list-of-dict
    fields (cached_printers/cached_skus) — TOML's array-of-tables support
    makes this work, but it's new to this dataclass and worth a dedicated
    proof rather than trusting it by inspection."""
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    s = Settings(
        cached_at="2026-08-11T00:00:00",
        cached_pricing_mode="margin_on_price",
        cached_default_margin_pct=55.0,
        cached_vat_pct=15.0,
        cached_labour_rate_per_hour=150.0,
        cached_electricity_tariff_per_kwh=2.85,
        cached_default_failure_pct=10.0,
        cached_printers=[
            {
                "id": 1, "name": "Primary", "power_watts_default": 200.0,
                "purchase_price": 12000.0, "expected_life_hours": 4000.0,
            }
        ],
        cached_skus=[{"id": 1, "name": "PETG Red", "color": "Red", "cost_per_gram": 2.0}],
    )
    save(s)
    loaded = load()
    assert loaded.cached_at == "2026-08-11T00:00:00"
    assert loaded.cached_pricing_mode == "margin_on_price"
    assert loaded.cached_default_margin_pct == 55.0
    assert loaded.cached_printers == s.cached_printers
    assert loaded.cached_skus == s.cached_skus


def test_v2_toml_without_cache_fields_loads_with_empty_cache(tmp_path, monkeypatch):
    """A v2 file (Phase 5, pre-offline-cache) has none of the cached_* keys
    — loading it must not raise, and cached_at must read as empty (never
    successfully cached), not some accidentally-truthy default."""
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    p: Path = tmp_path / "settings.toml"
    p.write_text(
        'schema_version = 2\nbackend_url = "https://print-calc.homelab"\n',
        encoding="utf-8",
    )
    s = load()
    assert s.cached_at == ""
    assert s.cached_printers == []
    assert s.cached_skus == []


def test_save_creates_directory(tmp_path, monkeypatch):
    target_dir = tmp_path / "nested" / "PrintDesktop"
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", target_dir)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", target_dir / "settings.toml")
    save(Settings())
    assert (target_dir / "settings.toml").exists()
    with (target_dir / "settings.toml").open("rb") as f:
        raw = tomllib.load(f)
    assert raw["schema_version"] == 3
