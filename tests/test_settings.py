import json

from gps_sim import settings as s


def test_settings_roundtrip(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)

    s.save_settings({"nasa_login": "a", "duration_minutes": 1440})
    assert s.load_settings() == {"nasa_login": "a", "duration_minutes": 1440}
    assert json.loads(path.read_text(encoding="utf-8"))["nasa_login"] == "a"


def test_default_duration_constant() -> None:
    assert s.DEFAULT_DURATION_MINUTES == 24 * 60
