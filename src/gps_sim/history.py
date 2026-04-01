"""История успешных запусков трансляции (history.json рядом с settings.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gps_sim.settings import settings_path


def history_path() -> Path:
    return settings_path().parent / "history.json"


def load_history_entries() -> list[dict[str, Any]]:
    p = history_path()
    if not p.is_file():
        return []
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        entries = data["entries"]
    elif isinstance(data, list):
        entries = data
    else:
        return []
    return [e for e in entries if isinstance(e, dict)]


def save_history_entries(entries: list[dict[str, Any]]) -> None:
    p = history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"entries": entries}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _coord_key(lat: float, lng: float) -> tuple[float, float]:
    return round(lat, 6), round(lng, 6)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def record_transmission(
    lat: float,
    lng: float,
    elevation_m: float,
    started_at: datetime | None = None,
) -> None:
    """
    Записывает запуск трансляции. Те же координаты (до 6 знаков) — только обновление времени
    и высоты, без новой записи.
    """
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    iso = _iso_utc(started_at)
    entries = load_history_entries()
    key = _coord_key(lat, lng)
    for e in entries:
        elat = _as_float(e.get("lat"))
        elng = _as_float(e.get("lng"))
        if elat is None or elng is None:
            continue
        if _coord_key(elat, elng) == key:
            e["started_at"] = iso
            e["lat"] = lat
            e["lng"] = lng
            e["elevation_m"] = float(elevation_m)
            save_history_entries(entries)
            return
    entries.append(
        {
            "started_at": iso,
            "lat": lat,
            "lng": lng,
            "elevation_m": float(elevation_m),
        },
    )
    save_history_entries(entries)


def remove_history_entry_at_coords(lat: float, lng: float) -> bool:
    """
    Удаляет из истории все записи с тем же ключом координат, что и у record_transmission (6 знаков).
    Возвращает True, если что-то удалено.
    """
    key = _coord_key(lat, lng)
    entries = load_history_entries()
    kept: list[dict[str, Any]] = []
    removed = False
    for e in entries:
        elat = _as_float(e.get("lat"))
        elng = _as_float(e.get("lng"))
        if elat is None or elng is None:
            kept.append(e)
            continue
        if _coord_key(elat, elng) == key:
            removed = True
            continue
        kept.append(e)
    if removed:
        save_history_entries(kept)
    return removed


def sorted_history_entries(entries: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """По убыванию времени запуска (новые сверху)."""
    if entries is None:
        entries = load_history_entries()

    def sort_key(e: dict[str, Any]) -> str:
        return str(e.get("started_at") or "")

    return sorted(entries, key=sort_key, reverse=True)


def format_history_entry_label(entry: dict[str, Any]) -> str:
    """Текст строки списка: дата/время (локально), координаты, высота."""
    raw = entry.get("started_at", "")
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        local = dt.astimezone()
        dt_s = local.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        dt_s = str(raw)
    lat = _as_float(entry.get("lat")) or 0.0
    lng = _as_float(entry.get("lng")) or 0.0
    elev = _as_float(entry.get("elevation_m")) or 0.0
    return f"{dt_s}\n{lat:.6f}, {lng:.6f}\nвысота: {elev:.2f} м"
