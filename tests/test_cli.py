import io
import json
import sys

import pytest

from gps_sim import cli
from gps_sim import settings as s


def test_version_exits() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0


def test_main_noninteractive_uses_saved_coords(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    cfg = {
        "nasa_login": "user",
        "nasa_pass": "secret",
        "lat": 55.75,
        "lng": 37.62,
        "duration_minutes": 90,
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    cli.main(["--skip-ephemeris", "--skip-elevation"])

    out = json.loads(path.read_text(encoding="utf-8"))
    assert out["lat"] == 55.75
    assert out["lng"] == 37.62
    assert out["duration_minutes"] == 90


def test_main_saves_elevation_m(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    cfg = {
        "nasa_login": "user",
        "nasa_pass": "secret",
        "lat": 1.0,
        "lng": 2.0,
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    def fake_fetch(lat: float, lng: float, timeout: int = 15) -> float:
        assert lat == 1.0 and lng == 2.0
        return 123.45

    monkeypatch.setattr(cli, "fetch_elevation", fake_fetch)
    cli.main(["--skip-ephemeris"])

    out = json.loads(path.read_text(encoding="utf-8"))
    assert out["elevation_m"] == pytest.approx(123.45)


def test_main_cli_coords_override(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    cfg = {
        "nasa_login": "user",
        "nasa_pass": "secret",
        "lat": 55.75,
        "lng": 37.62,
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    cli.main(["59.93", "30.33", "--skip-ephemeris", "--skip-elevation"])

    out = json.loads(path.read_text(encoding="utf-8"))
    assert out["lat"] == pytest.approx(59.93)
    assert out["lng"] == pytest.approx(30.33)


def test_main_noninteractive_fails_without_creds(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    with pytest.raises(SystemExit) as exc:
        cli.main(["--skip-ephemeris", "--skip-elevation"])
    assert exc.value.code == 1


def test_lat_lng_one_arg_error() -> None:
    with pytest.raises(SystemExit):
        cli.main(["55.0"])


def test_settings_flag_shows_path_and_json(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    cfg = {"nasa_login": "u", "lat": 1.0}
    path.write_text(json.dumps(cfg), encoding="utf-8")

    cli.main(["--settings"])

    out = capsys.readouterr().out
    assert str(path) in out
    assert '"nasa_login": "u"' in out


def test_settings_flag_missing_file(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "nope.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)

    cli.main(["--settings"])

    out = capsys.readouterr().out
    assert str(path) in out
    assert "не найден" in out
