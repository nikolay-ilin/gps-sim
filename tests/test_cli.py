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

    cli.main(["--skip-ephemeris", "--skip-elevation", "--skip-run"])

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

    def fake_cached(cfg: dict, lat: float, lng: float, *, timeout: int = 15) -> float:
        assert lat == 1.0 and lng == 2.0
        cfg["elevation_m"] = 123.45
        cfg["elevation_cache_lat"] = lat
        cfg["elevation_cache_lng"] = lng
        return 123.45

    monkeypatch.setattr(cli, "get_elevation_cached", fake_cached)
    cli.main(["--skip-ephemeris", "--skip-run"])

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

    cli.main(["59.93", "30.33", "--skip-ephemeris", "--skip-elevation", "--skip-run"])

    out = json.loads(path.read_text(encoding="utf-8"))
    assert out["lat"] == pytest.approx(59.93)
    assert out["lng"] == pytest.approx(30.33)


def test_main_noninteractive_fails_without_creds(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    with pytest.raises(SystemExit) as exc:
        cli.main(["--skip-ephemeris", "--skip-elevation", "--skip-run"])
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


def test_main_runs_simulation_after_prepare(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    nav = tmp_path / "nav.n"
    nav.write_text("stub", encoding="utf-8")
    cfg = {
        "nasa_login": "user",
        "nasa_pass": "secret",
        "lat": 55.75,
        "lng": 37.62,
        "duration_minutes": 90,
        "broadcast_ephemeris_path": str(nav),
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    calls: list[int] = []

    def fake_run_simulation(*args: object, **kwargs: object) -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(cli, "run_simulation", fake_run_simulation)

    cli.main(["--skip-ephemeris", "--skip-elevation"])

    assert calls == [1]


def test_skip_run_skips_simulation(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: path)
    nav = tmp_path / "nav.n"
    nav.write_text("stub", encoding="utf-8")
    cfg = {
        "nasa_login": "user",
        "nasa_pass": "secret",
        "lat": 55.75,
        "lng": 37.62,
        "duration_minutes": 90,
        "broadcast_ephemeris_path": str(nav),
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    calls: list[int] = []

    def fake_run_simulation(*args: object, **kwargs: object) -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(cli, "run_simulation", fake_run_simulation)

    cli.main(["--skip-ephemeris", "--skip-elevation", "--skip-run"])

    assert calls == []
