"""Точка входа CLI."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any

from gps_sim import __version__
from gps_sim import settings as settings_mod
from gps_sim.brdc_download import download_latest_broadcast_ephemeris
from gps_sim.settings import (
    DEFAULT_DURATION_MINUTES,
    ephemeris_dir,
    load_settings,
    save_settings,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gps-sim",
        description="GPS/GNSS: настройки и параметры симуляции.",
    )
    parser.add_argument("--version", action="version", version=f"gps-sim {__version__}")
    parser.add_argument(
        "--settings",
        action="store_true",
        help="показать путь к файлу настроек и его содержимое и выйти",
    )
    parser.add_argument(
        "lat",
        nargs="?",
        type=float,
        default=None,
        metavar="LAT",
        help="широта (градусы); вместе с долготой имеет приоритет над вводом и файлом",
    )
    parser.add_argument(
        "lng",
        nargs="?",
        type=float,
        default=None,
        metavar="LNG",
        help="долгота (градусы)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        metavar="MIN",
        help=f"длительность симуляции в минутах (по умолчанию {DEFAULT_DURATION_MINUTES})",
    )
    parser.add_argument(
        "--skip-ephemeris",
        action="store_true",
        help="не загружать broadcast-эфемериды с CDDIS после сохранения настроек",
    )
    parser.add_argument(
        "--brdc-year",
        type=int,
        default=None,
        metavar="YEAR",
        help="год для каталога CDDIS daily/.../brdc (по умолчанию — текущий календарный год)",
    )
    ns = parser.parse_args(argv)
    if (ns.lat is None) ^ (ns.lng is None):
        parser.error("Укажите оба аргумента: широта и долгота, либо ни одного.")
    return ns


def _validate_lat(value: float) -> float:
    if not -90.0 <= value <= 90.0:
        msg = "Широта должна быть в диапазоне [-90, 90]."
        raise ValueError(msg)
    return value


def _validate_lng(value: float) -> float:
    if not -180.0 <= value <= 180.0:
        msg = "Долгота должна быть в диапазоне [-180, 180]."
        raise ValueError(msg)
    return value


def _parse_float_line(line: str) -> float:
    return float(line.strip().replace(",", "."))


def _resolve_coordinate(
    label: str,
    *,
    from_arg: float | None,
    stored: float | None,
    validate: Callable[[float], float],
    interactive: bool,
) -> float:
    if from_arg is not None:
        return validate(from_arg)
    if not interactive:
        if stored is not None:
            return validate(float(stored))
        msg = f"Нет значения {label} в настройках."
        raise RuntimeError(msg)
    hint = f" (Enter — из настроек: {stored})" if stored is not None else ""
    while True:
        raw = input(f"{label}{hint}: ").strip()
        if not raw:
            if stored is not None:
                return validate(float(stored))
            print("Введите число или задайте значение в настройках.")
            continue
        try:
            return validate(_parse_float_line(raw))
        except ValueError as e:
            print(e)


def _prompt_required_str(label: str, stored: str | None, *, secret: bool = False) -> str:
    if stored:
        return stored
    while True:
        if secret:
            line = getpass.getpass(f"{label}: ").strip()
        else:
            line = input(f"{label}: ").strip()
        if line:
            return line
        print("Значение обязательно.")


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _print_settings_info() -> None:
    path = settings_mod.settings_path()
    print(f"Путь: {path}")
    if not path.is_file():
        print("(файл не найден)")
        return
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        print("(пустой файл)")
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(raw.rstrip())
        return
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.settings:
        _print_settings_info()
        return
    cfg: dict[str, Any] = load_settings()
    interactive = sys.stdin.isatty()

    if not interactive:
        missing: list[str] = []
        if not (cfg.get("nasa_login") or "").strip():
            missing.append("nasa_login")
        if not (cfg.get("nasa_pass") or "").strip():
            missing.append("nasa_pass")
        if missing:
            print(
                "Нет интерактивного ввода и в файле настроек отсутствуют: "
                + ", ".join(missing),
                file=sys.stderr,
            )
            sys.exit(1)
        if args.lat is None and (
            _float_or_none(cfg.get("lat")) is None or _float_or_none(cfg.get("lng")) is None
        ):
            print(
                "Нет интерактивного ввода: задайте широту и долготу аргументами "
                "или сохраните lat/lng в файле настроек.",
                file=sys.stderr,
            )
            sys.exit(1)

    nasa_login = _prompt_required_str("NASA login (nasa_login)", cfg.get("nasa_login"))
    nasa_pass = _prompt_required_str("NASA password (nasa_pass)", cfg.get("nasa_pass"), secret=True)

    lat = _resolve_coordinate(
        "Широта (lat)",
        from_arg=args.lat,
        stored=_float_or_none(cfg.get("lat")),
        validate=_validate_lat,
        interactive=interactive,
    )
    lng = _resolve_coordinate(
        "Долгота (lng)",
        from_arg=args.lng,
        stored=_float_or_none(cfg.get("lng")),
        validate=_validate_lng,
        interactive=interactive,
    )

    duration_minutes = args.duration
    if duration_minutes is None:
        duration_minutes = int(cfg.get("duration_minutes", DEFAULT_DURATION_MINUTES))

    cfg.update(
        {
            "nasa_login": nasa_login,
            "nasa_pass": nasa_pass,
            "lat": lat,
            "lng": lng,
            "duration_minutes": duration_minutes,
        }
    )
    save_settings(cfg)

    if not args.skip_ephemeris:
        try:
            year = args.brdc_year if args.brdc_year is not None else datetime.now().year
            unpacked = download_latest_broadcast_ephemeris(
                nasa_login,
                nasa_pass,
                ephemeris_dir(),
                year=year,
            )
            cfg["broadcast_ephemeris_filename"] = unpacked.name
            save_settings(cfg)
        except Exception as e:
            print(f"Ошибка обновления эфемерид: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
