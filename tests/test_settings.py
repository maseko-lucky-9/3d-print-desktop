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
    assert s.electricity_rate == 2.50
    assert s.onboarded is False
    assert s.schema_version == 1


def test_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    s = Settings(backend_url="https://test.local", electricity_rate=3.5, onboarded=True)
    save(s)
    loaded = load()
    assert loaded.backend_url == "https://test.local"
    assert loaded.electricity_rate == 3.5
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


def test_corrupt_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", tmp_path / "settings.toml")
    (tmp_path / "settings.toml").write_text("not valid toml @@@\n", encoding="utf-8")
    s = load()
    assert s.backend_url == "https://print-calc.homelab"  # default


def test_save_creates_directory(tmp_path, monkeypatch):
    target_dir = tmp_path / "nested" / "PrintDesktop"
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", target_dir)
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", target_dir / "settings.toml")
    save(Settings())
    assert (target_dir / "settings.toml").exists()
    with (target_dir / "settings.toml").open("rb") as f:
        raw = tomllib.load(f)
    assert raw["schema_version"] == 1
