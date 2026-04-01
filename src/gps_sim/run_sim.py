"""Запуск конвейера gps-sdr-sim → hackrf_transfer по настройкам."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gps_sim import __version__
from gps_sim.rinex_nav import (
    broadcast_nav_time_bounds,
    clamp_utc_start_to_nav_bounds,
    format_gps_sdr_sim_time,
)
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


def _darwin_hackrf_transfer_search_paths() -> tuple[Path, ...]:
    """Типичные пути Homebrew; GUI на macOS часто не видит их в PATH."""
    return (
        Path("/opt/homebrew/bin/hackrf_transfer"),
        Path("/usr/local/bin/hackrf_transfer"),
    )


def _resolve_hackrf_transfer(cfg: dict[str, Any]) -> str | None:
    raw = cfg.get("hackrf_transfer_path")
    if raw:
        p = Path(str(raw)).expanduser().resolve()
        if _is_executable_file(p):
            return str(p)
    w = shutil.which("hackrf_transfer")
    if w:
        return w
    if sys.platform == "darwin":
        for p in _darwin_hackrf_transfer_search_paths():
            if _is_executable_file(p):
                return str(p.resolve())
    return None


def _bundled_gps_sdr_sim_filename() -> str | None:
    """Имя встроенного бинарника для текущей ОС/архитектуры или None (остальные платформы)."""
    machine = platform.machine().lower()
    if sys.platform == "darwin" and machine in ("arm64", "aarch64"):
        return "gps-sdr-sim-macos-apple"
    if sys.platform == "linux" and machine in ("aarch64", "arm64"):
        return "gps-sdr-sim-debian-arm64"
    return None


def _bundled_gps_sdr_sim_path() -> Path | None:
    """Путь к встроенному бинарнику в пакете, если он есть и исполняемый."""
    name = _bundled_gps_sdr_sim_filename()
    if name is None:
        return None
    p = Path(__file__).resolve().parent / "bin" / name
    if _is_executable_file(p):
        return p
    return None


def _try_resolve_bundled_gps_sdr_sim(cfg: dict[str, Any]) -> str | None:
    """Подставляет встроенный gps-sdr-sim и при необходимости сохраняет путь в настройки."""
    p = _bundled_gps_sdr_sim_path()
    if p is None:
        return None
    resolved = str(p.resolve())
    if cfg.get("gps_sdr_sim_path") != resolved:
        cfg["gps_sdr_sim_path"] = resolved
        save_settings(cfg)
        print(f"В настройки сохранён путь к встроенному gps-sdr-sim: {resolved}")
    return resolved


def _resolve_gps_sdr_sim_path(cfg: dict[str, Any], *, interactive: bool) -> str:
    raw = cfg.get("gps_sdr_sim_path")
    if raw:
        p = Path(str(raw)).expanduser().resolve()
        if _is_executable_file(p):
            return str(p)

    bundled = _try_resolve_bundled_gps_sdr_sim(cfg)
    if bundled is not None:
        return bundled

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


def _terminate_pipeline_processes(
    p1: subprocess.Popen[bytes] | None,
    p2: subprocess.Popen[bytes] | None,
) -> None:
    for p in (p2, p1):
        if p is not None and p.poll() is None:
            p.terminate()
    for p in (p2, p1):
        if p is not None:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


def _merge_pipeline_exit_codes(rc1: int, rc2: int) -> int:
    """
    Сводит коды gps-sdr-sim (p1) и hackrf_transfer (p2).

    SIGPIPE (-13) у отправителя часто следует за ошибкой приёмника: тогда важнее код hackrf.
    """
    if rc1 == -13 and rc2 != 0:
        return rc2
    if rc2 == -13 and rc1 != 0:
        return rc1
    if rc1 != 0 or rc2 != 0:
        return rc1 if rc1 != 0 else rc2
    return 0


def _warn_sigpipe_if_needed(rc1: int, rc2: int) -> None:
    if rc1 != -13 and rc2 != -13:
        return
    print(
        "Примечание: SIGPIPE (-13) — разрыв потока между gps-sdr-sim и hackrf_transfer. "
        "Часто hackrf_transfer уже вышел с ошибкой (устройство, USB, права). "
        "Смотрите вывод hackrf_transfer выше; проверьте HackRF и кабель.",
        file=sys.stderr,
    )


def _wait_process_or_cancel(
    proc: subprocess.Popen[bytes],
    cancel_event: threading.Event,
) -> int | None:
    """Ждёт завершения процесса; при cancel_event возвращает None."""
    while proc.poll() is None:
        if cancel_event.is_set():
            return None
        try:
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue
    rc = proc.returncode
    return 0 if rc is None else rc


def run_pipeline(
    gps_cmd: list[str],
    hackrf_cmd: list[str],
    *,
    cancel_event: threading.Event | None = None,
) -> int:
    """Запускает конвейер; возвращает код выхода (0 — успех, 130 — остановка)."""
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
        if cancel_event is None:
            rc2 = p2.wait()
            rc1 = p1.wait()
        else:
            r2 = _wait_process_or_cancel(p2, cancel_event)
            if r2 is None:
                print("\n[*] Остановка симуляции...", file=sys.stderr)
                _terminate_pipeline_processes(p1, p2)
                return 130
            r1 = _wait_process_or_cancel(p1, cancel_event)
            if r1 is None:
                print("\n[*] Остановка симуляции...", file=sys.stderr)
                _terminate_pipeline_processes(p1, p2)
                return 130
            rc2, rc1 = r2, r1
        merged = _merge_pipeline_exit_codes(rc1, rc2)
        if merged != 0:
            _warn_sigpipe_if_needed(rc1, rc2)
        return merged
    except FileNotFoundError as e:
        if p1 is not None and p1.poll() is None:
            p1.terminate()
        print(f"Ошибка запуска процесса: {e}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("\n[*] Остановка симуляции...", file=sys.stderr)
        _terminate_pipeline_processes(p1, p2)
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


def _gps_sdr_sim_path_for_log(cfg: dict[str, Any]) -> str:
    """Путь к gps-sdr-sim для лога без sys.exit (как при неинтерактивном запуске)."""
    raw = cfg.get("gps_sdr_sim_path")
    if raw:
        return str(Path(str(raw)).expanduser().resolve())
    bundled = _bundled_gps_sdr_sim_path()
    if bundled is not None:
        return str(bundled.resolve())
    which = shutil.which("gps-sdr-sim")
    if which:
        return which
    return "не найден"


def format_simulation_params_log(cfg: dict[str, Any]) -> str:
    """
    Многострочное описание параметров симуляции для UI-лога.
    Согласовано с тем, что передаётся в gps-sdr-sim и hackrf_transfer в run_simulation.
    """
    lines: list[str] = []
    nav = broadcast_ephemeris_file(cfg)
    if nav is not None and nav.is_file():
        lines.append(f"Эфемериды: {nav}")
    else:
        lines.append("Эфемериды: не заданы или файл отсутствует")

    try:
        lat = float(cfg["lat"])
        lng = float(cfg["lng"])
    except (KeyError, TypeError, ValueError):
        lat, lng = 0.0, 0.0
    alt = _coerce_float(cfg, "elevation_m", 0.0)
    lines.append(f"Позиция: {lat:.6f}, {lng:.6f}; высота {alt:.2f} м")

    duration_min = int(cfg.get("duration_minutes", DEFAULT_DURATION_MINUTES))
    duration_sec = duration_min * 60
    gain_val = _coerce_int(cfg, "hackrf_tx_gain", DEFAULT_HACKRF_TX_GAIN)
    bits = _coerce_int(cfg, "sim_bits", DEFAULT_SIM_BITS)
    sample_hz = _coerce_int(cfg, "sim_sample_rate_hz", DEFAULT_SIM_SAMPLE_RATE_HZ)
    freq_hz = _coerce_int(cfg, "hackrf_freq_hz", DEFAULT_HACKRF_FREQ_HZ)
    amp = _coerce_int(cfg, "hackrf_amp", DEFAULT_HACKRF_AMP)

    utc_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    utc_label = format_gps_sdr_sim_time(utc_start)
    if nav is not None and nav.is_file():
        try:
            tmin, tmax = broadcast_nav_time_bounds(nav)
            utc_start, _ = clamp_utc_start_to_nav_bounds(utc_start, tmin, tmax)
            utc_label = format_gps_sdr_sim_time(utc_start)
        except ValueError:
            pass

    lines.append(f"Длительность: {duration_min} мин ({duration_sec} с)")
    lines.append(f"Время GPS для gps-sdr-sim (-t): {utc_label}")
    lines.append(
        f"gps-sdr-sim: -b {bits} -s {sample_hz} -d {duration_sec} -t {utc_label} "
        f"(позиция -l как lat,lng,alt)"
    )
    lines.append(
        f"hackrf_transfer: -f {freq_hz} -s {sample_hz} -a {amp} -x {gain_val}"
    )
    lines.append(f"Исполняемый файл gps-sdr-sim: {_gps_sdr_sim_path_for_log(cfg)}")
    hackrf_w = _resolve_hackrf_transfer(cfg)
    lines.append(f"hackrf_transfer: {hackrf_w or 'не найден в PATH'}")

    return "\n".join(lines) + "\n"


def run_simulation(
    cfg: dict[str, Any],
    *,
    duration_minutes: int | None = None,
    gain: int | None = None,
    interactive: bool = True,
    cancel_event: threading.Event | None = None,
) -> int:
    """Конвейер gps-sdr-sim → hackrf_transfer по настройкам; возвращает код выхода."""
    hackrf_bin = _resolve_hackrf_transfer(cfg)
    if hackrf_bin is None:
        print(
            "Не найден hackrf_transfer (ни в PATH, ни исполняемый файл по hackrf_transfer_path в настройках). "
            "Установите host tools для HackRF (macOS: brew install hackrf) или укажите полный путь в "
            "settings.json → hackrf_transfer_path.\n"
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
    try:
        tmin, tmax = broadcast_nav_time_bounds(nav_path)
        utc_start, clamped = clamp_utc_start_to_nav_bounds(utc_start, tmin, tmax)
        if clamped:
            a = format_gps_sdr_sim_time(utc_start)
            lo = format_gps_sdr_sim_time(tmin)
            hi = format_gps_sdr_sim_time(tmax)
            print(
                "Время старта вне окна эфемерид; используется ближайшее допустимое UTC: "
                f"{a} (допустимо {lo} … {hi}).",
                file=sys.stderr,
            )
    except ValueError as exc:
        print(
            f"Предупреждение: не удалось прочитать границы эфемерид ({exc}); "
            "время старта не подгонялось.",
            file=sys.stderr,
        )

    utc_now = format_gps_sdr_sim_time(utc_start)

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
        hackrf_bin,
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
    return run_pipeline(gps_cmd, hackrf_cmd, cancel_event=cancel_event)


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
