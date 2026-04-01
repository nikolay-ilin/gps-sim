"""Запуск конвейера gps-sdr-sim → hackrf_transfer по настройкам."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gps_sim import __version__
from gps_sim.settings import (
    DEFAULT_DURATION_MINUTES,
    DEFAULT_HACKRF_AMP,
    DEFAULT_HACKRF_FREQ_HZ,
    DEFAULT_HACKRF_TX_GAIN,
    DEFAULT_SIM_BITS,
    DEFAULT_SIM_SAMPLE_RATE_HZ,
    broadcast_ephemeris_file,
    load_settings,
    save_settings,
)

HACKRF_HOST_TOOLS_DOC_URL = (
    "https://github.com/greatscottgadgets/hackrf/wiki/Getting-Started-With-HackRF"
)


def _is_executable_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if os.name == "nt":
        return True
    return os.access(path, os.X_OK)


def _coerce_int(cfg: dict[str, Any], key: str, default: int) -> int:
    raw = cfg.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _coerce_float(cfg: dict[str, Any], key: str, default: float) -> float:
    raw = cfg.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _find_hackrf_transfer() -> str | None:
    return shutil.which("hackrf_transfer")


def _resolve_gps_sdr_sim_path(cfg: dict[str, Any], *, interactive: bool) -> str:
    raw = cfg.get("gps_sdr_sim_path")
    if raw:
        p = Path(str(raw)).expanduser().resolve()
        if _is_executable_file(p):
            return str(p)

    which = shutil.which("gps-sdr-sim")
    if which:
        return which

    if not interactive:
        print(
            "Не найден исполняемый gps-sdr-sim: задайте ключ gps_sdr_sim_path в настройках "
            "или установите бинарь в PATH.",
            file=sys.stderr,
        )
        sys.exit(1)

    while True:
        line = input("Путь к исполняемому файлу gps-sdr-sim: ").strip()
        if not line:
            print("Укажите путь или прервите (Ctrl+C).")
            continue
        p = Path(line).expanduser().resolve()
        if _is_executable_file(p):
            cfg["gps_sdr_sim_path"] = str(p)
            save_settings(cfg)
            print(f"Сохранено в настройках: gps_sdr_sim_path = {p}")
            return str(p)
        print("Файл не найден или не исполняемый.")


def _require_ephemeris_path(cfg: dict[str, Any]) -> Path:
    p = broadcast_ephemeris_file(cfg)
    if p is None or not p.is_file():
        print(
            "В настройках нет пути к broadcast-эфемеридам (broadcast_ephemeris_path) "
            "или файл отсутствует. Сначала выполните gps-sim с загрузкой эфемерид.",
            file=sys.stderr,
        )
        sys.exit(1)
    return p


def _location_string(cfg: dict[str, Any]) -> str:
    lat = cfg.get("lat")
    lng = cfg.get("lng")
    if lat is None or lng is None:
        print(
            "В настройках нет lat/lng. Задайте координаты через gps-sim.",
            file=sys.stderr,
        )
        sys.exit(1)
    alt = _coerce_float(cfg, "elevation_m", 0.0)
    return f"{float(lat)},{float(lng)},{alt}"


def run_pipeline(gps_cmd: list[str], hackrf_cmd: list[str]) -> int:
    """Запускает конвейер; возвращает код выхода (0 — успех)."""
    p1: subprocess.Popen[bytes] | None = None
    p2: subprocess.Popen[bytes] | None = None
    try:
        p1 = subprocess.Popen(gps_cmd, stdout=subprocess.PIPE)
        try:
            p2 = subprocess.Popen(hackrf_cmd, stdin=p1.stdout)
        except Exception:
            if p1.poll() is None:
                p1.terminate()
                try:
                    p1.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p1.kill()
            raise
        if p1.stdout is not None:
            p1.stdout.close()
        rc2 = p2.wait()
        rc1 = p1.wait()
        if rc1 != 0 or rc2 != 0:
            return rc1 if rc1 != 0 else rc2
        return 0
    except FileNotFoundError as e:
        if p1 is not None and p1.poll() is None:
            p1.terminate()
        print(f"Ошибка запуска процесса: {e}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("\n[*] Остановка симуляции...", file=sys.stderr)
        for p in (p2, p1):
            if p is not None and p.poll() is None:
                p.terminate()
        for p in (p2, p1):
            if p is not None:
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        return 130


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gps-sim-run",
        description="Запуск симуляции GPS (gps-sdr-sim) и передачи через HackRF по настройкам.",
    )
    parser.add_argument("--version", action="version", version=f"gps-sim-run {__version__}")
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        metavar="MIN",
        help=f"длительность в минутах (по умолчанию из настроек, иначе {DEFAULT_DURATION_MINUTES})",
    )
    parser.add_argument(
        "--gain",
        type=int,
        default=None,
        metavar="DB",
        help="усиление TX HackRF -x (по умолчанию из настроек)",
    )
    return parser.parse_args(argv)


def run_simulation(
    cfg: dict[str, Any],
    *,
    duration_minutes: int | None = None,
    gain: int | None = None,
    interactive: bool = True,
) -> int:
    """Конвейер gps-sdr-sim → hackrf_transfer по настройкам; возвращает код выхода."""
    if _find_hackrf_transfer() is None:
        print(
            "Не найден hackrf_transfer в PATH. Установите host tools для HackRF и убедитесь, "
            "что каталог с бинарями в PATH.\n"
            f"Документация: {HACKRF_HOST_TOOLS_DOC_URL}",
            file=sys.stderr,
        )
        return 1

    gps_bin = _resolve_gps_sdr_sim_path(cfg, interactive=interactive)
    nav_path = _require_ephemeris_path(cfg)
    location = _location_string(cfg)

    duration_min = (
        duration_minutes
        if duration_minutes is not None
        else int(cfg.get("duration_minutes", DEFAULT_DURATION_MINUTES))
    )
    duration_sec = duration_min * 60

    gain_val = (
        gain
        if gain is not None
        else _coerce_int(cfg, "hackrf_tx_gain", DEFAULT_HACKRF_TX_GAIN)
    )
    bits = _coerce_int(cfg, "sim_bits", DEFAULT_SIM_BITS)
    sample_hz = _coerce_int(cfg, "sim_sample_rate_hz", DEFAULT_SIM_SAMPLE_RATE_HZ)
    freq_hz = _coerce_int(cfg, "hackrf_freq_hz", DEFAULT_HACKRF_FREQ_HZ)
    amp = _coerce_int(cfg, "hackrf_amp", DEFAULT_HACKRF_AMP)

    utc_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    utc_now = utc_start.strftime("%Y/%m/%d,%H:%M:%S")

    gps_cmd = [
        gps_bin,
        "-b",
        str(bits),
        "-s",
        str(sample_hz),
        "-l",
        location,
        "-e",
        str(nav_path),
        "-d",
        str(duration_sec),
        "-t",
        utc_now,
        "-o",
        "-",
    ]

    hackrf_cmd = [
        "hackrf_transfer",
        "-t",
        "-",
        "-f",
        str(freq_hz),
        "-s",
        str(sample_hz),
        "-a",
        str(amp),
        "-x",
        str(gain_val),
    ]

    print(f"[*] Команда генерации данных: {shlex.join(gps_cmd)}")
    print(f"[*] Команда трансляции: {shlex.join(hackrf_cmd)}")

    return run_pipeline(gps_cmd, hackrf_cmd)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    cfg = load_settings()
    interactive = sys.stdin.isatty()
    rc = run_simulation(
        cfg,
        duration_minutes=args.duration,
        gain=args.gain,
        interactive=interactive,
    )
    if rc != 0:
        sys.exit(rc)


if __name__ == "__main__":
    main()
