import io
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from gps_sim import run_sim
from gps_sim import settings as s

_BRDC_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "brdc_minimal.n"


def test_main_fails_without_hackrf(monkeypatch) -> None:
    monkeypatch.setattr(run_sim, "_resolve_hackrf_transfer", lambda _cfg: None)

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

    monkeypatch.setattr(run_sim, "_resolve_hackrf_transfer", lambda _cfg: "/bin/hackrf_transfer")
    monkeypatch.setattr(run_sim.shutil, "which", lambda _name: None)
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
    monkeypatch.setattr(run_sim, "_resolve_hackrf_transfer", lambda _cfg: "/usr/bin/hackrf_transfer")
    monkeypatch.setattr(run_sim, "run_pipeline", lambda *_a, **_k: 0)

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

        def wait(self, timeout: float | None = None) -> int:
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

        def wait(self, timeout: float | None = None) -> int:
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

        def wait(self, timeout: float | None = None) -> int:
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

        def wait(self, timeout: float | None = None) -> int:
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


def test_merge_pipeline_exit_codes_prefers_hackrf_on_sigpipe() -> None:
    assert run_sim._merge_pipeline_exit_codes(-13, 1) == 1
    assert run_sim._merge_pipeline_exit_codes(2, -13) == 2
    assert run_sim._merge_pipeline_exit_codes(-13, 0) == -13


def test_run_pipeline_cancel_returns_130(monkeypatch) -> None:
    class _Pipe:
        def close(self) -> None:
            pass

    class P1:
        stdout = _Pipe()

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
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

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    seq = iter([P1(), P2()])

    def fake_popen(*_a: object, **_k: object) -> object:
        return next(seq)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    cancel = threading.Event()
    cancel.set()
    assert run_sim.run_pipeline(["true"], ["true"], cancel_event=cancel) == 130


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


def test_resolve_hackrf_transfer_explicit_path(tmp_path) -> None:
    fake = tmp_path / "hackrf_transfer"
    fake.write_bytes(b"#!/bin/sh\n")
    fake.chmod(0o755)
    cfg = {"hackrf_transfer_path": str(fake)}
    assert run_sim._resolve_hackrf_transfer(cfg) == str(fake.resolve())


def test_resolve_hackrf_transfer_falls_back_to_which(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        return "/opt/homebrew/bin/hackrf_transfer" if name == "hackrf_transfer" else None

    monkeypatch.setattr(run_sim.shutil, "which", fake_which)
    assert run_sim._resolve_hackrf_transfer({}) == "/opt/homebrew/bin/hackrf_transfer"


def test_resolve_hackrf_transfer_darwin_homebrew_without_path(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "hackrf_transfer"
    fake.write_bytes(b"#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(run_sim.sys, "platform", "darwin")
    monkeypatch.setattr(run_sim.shutil, "which", lambda _n: None)
    monkeypatch.setattr(
        run_sim, "_darwin_hackrf_transfer_search_paths", lambda: (fake,)
    )
    assert run_sim._resolve_hackrf_transfer({}) == str(fake.resolve())


def test_format_simulation_params_log(tmp_path) -> None:
    nav = _BRDC_FIXTURE
    fake_gps = tmp_path / "gps-sdr-sim"
    fake_gps.write_bytes(b"#!/bin/sh\n")
    fake_gps.chmod(0o755)
    cfg = {
        "lat": 55.0,
        "lng": 37.0,
        "elevation_m": 10.5,
        "duration_minutes": 60,
        "broadcast_ephemeris_path": str(nav),
        "gps_sdr_sim_path": str(fake_gps),
    }
    text = run_sim.format_simulation_params_log(cfg)
    assert str(nav) in text
    assert "55.000000" in text
    assert "37.000000" in text
    assert "10.50" in text
    assert "hackrf_transfer" in text
    assert "gps-sdr-sim" in text
    assert str(fake_gps.resolve()) in text
