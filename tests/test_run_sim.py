import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from gps_sim import run_sim
from gps_sim import settings as s

_BRDC_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "brdc_minimal.n"


def test_main_fails_without_hackrf(monkeypatch) -> None:
    monkeypatch.setattr(run_sim, "_find_hackrf_transfer", lambda: None)

    with pytest.raises(SystemExit) as exc:
        run_sim.main([])
    assert exc.value.code == 1


def test_main_fails_without_gps_noninteractive(tmp_path, monkeypatch) -> None:
    nav = tmp_path / "nav.n"
    nav.write_text("stub", encoding="utf-8")
    cfg = {
        "lat": 55.0,
        "lng": 37.0,
        "broadcast_ephemeris_path": str(nav),
    }
    monkeypatch.setattr(run_sim, "load_settings", lambda: cfg)
    monkeypatch.setattr(run_sim, "_bundled_gps_sdr_sim_path", lambda: None)

    def fake_which(name: str) -> str | None:
        if name == "hackrf_transfer":
            return "/bin/hackrf_transfer"
        return None

    monkeypatch.setattr(run_sim.shutil, "which", fake_which)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    with pytest.raises(SystemExit) as exc:
        run_sim.main([])
    assert exc.value.code == 1


def test_main_succeeds_with_mock_pipeline(tmp_path, monkeypatch) -> None:
    nav = _BRDC_FIXTURE
    fake_gps = tmp_path / "gps-sdr-sim"
    fake_gps.write_bytes(b"#!/bin/sh\n")
    fake_gps.chmod(0o755)
    cfg = {
        "lat": 55.0,
        "lng": 37.0,
        "elevation_m": 10.0,
        "duration_minutes": 60,
        "broadcast_ephemeris_path": str(nav),
        "gps_sdr_sim_path": str(fake_gps),
    }
    monkeypatch.setattr(run_sim, "load_settings", lambda: cfg)
    monkeypatch.setattr(run_sim, "_find_hackrf_transfer", lambda: "/usr/bin/hackrf_transfer")
    monkeypatch.setattr(run_sim, "run_pipeline", lambda _g, _h: 0)

    run_sim.main([])


def test_resolve_saves_path_interactive(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: settings_path)
    fake_gps = tmp_path / "gps-sdr-sim"
    fake_gps.write_bytes(b"#!/bin/sh\n")
    fake_gps.chmod(0o755)

    cfg: dict = {}
    monkeypatch.setattr(run_sim, "_bundled_gps_sdr_sim_path", lambda: None)
    monkeypatch.setattr(run_sim.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{fake_gps}\n"))

    path = run_sim._resolve_gps_sdr_sim_path(cfg, interactive=True)
    assert path == str(fake_gps.resolve())
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["gps_sdr_sim_path"] == str(fake_gps.resolve())


def test_run_pipeline_success(monkeypatch) -> None:
    class _Pipe:
        def close(self) -> None:
            pass

    class P1:
        stdout = _Pipe()

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def wait(self) -> int:
            return 0

        def poll(self) -> int | None:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    class P2:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def wait(self) -> int:
            return 0

        def poll(self) -> int | None:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    seq = iter([P1(), P2()])

    def fake_popen(*_a: object, **_k: object) -> object:
        return next(seq)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    assert run_sim.run_pipeline(["true"], ["true"]) == 0


def test_run_pipeline_nonzero_return(monkeypatch) -> None:
    class _Pipe:
        def close(self) -> None:
            pass

    class P1:
        stdout = _Pipe()

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def wait(self) -> int:
            return 1

        def poll(self) -> int | None:
            return 1

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    class P2:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def wait(self) -> int:
            return 0

        def poll(self) -> int | None:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    seq = iter([P1(), P2()])

    def fake_popen(*_a: object, **_k: object) -> object:
        return next(seq)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    assert run_sim.run_pipeline(["true"], ["true"]) == 1


def test_bundled_filename_apple_silicon(monkeypatch) -> None:
    monkeypatch.setattr(run_sim.sys, "platform", "darwin")
    monkeypatch.setattr(run_sim.platform, "machine", lambda: "arm64")
    assert run_sim._bundled_gps_sdr_sim_filename() == "gps-sdr-sim-macos-apple"


def test_bundled_filename_debian_arm64(monkeypatch) -> None:
    monkeypatch.setattr(run_sim.sys, "platform", "linux")
    monkeypatch.setattr(run_sim.platform, "machine", lambda: "aarch64")
    assert run_sim._bundled_gps_sdr_sim_filename() == "gps-sdr-sim-debian-arm64"


def test_bundled_filename_other_platform(monkeypatch) -> None:
    monkeypatch.setattr(run_sim.sys, "platform", "win32")
    assert run_sim._bundled_gps_sdr_sim_filename() is None


def test_try_resolve_bundled_saves_settings(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: settings_path)
    fake_bin = tmp_path / "gps-sdr-sim-macos-apple"
    fake_bin.write_bytes(b"x")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(run_sim, "_bundled_gps_sdr_sim_path", lambda: fake_bin)

    cfg: dict[str, object] = {}
    out = run_sim._try_resolve_bundled_gps_sdr_sim(cfg)

    assert out == str(fake_bin.resolve())
    assert cfg.get("gps_sdr_sim_path") == str(fake_bin.resolve())
    assert settings_path.is_file()
