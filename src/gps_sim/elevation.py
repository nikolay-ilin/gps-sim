"""Высота над уровнем моря по координатам (Open-Meteo Elevation API)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_URL = "https://api.open-meteo.com/v1/elevation"
USER_AGENT = "gps-sim/elevation"

# ~0.1 м по экватору; достаточно для «та же точка на карте»
_GEO_EPS = 1e-6


def parse_coordinates(raw: str) -> tuple[float, float]:
    if not raw or "," not in raw:
        raise ValueError('Ожидается строка формата: "53.4462, -113.4209"')

    parts = raw.split(",", 1)
    lat_str = parts[0].strip()
    lon_str = parts[1].strip()
    if "," in lon_str:
        raise ValueError("Долгота должна быть одним числом; уберите лишние запятые.")

    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except ValueError as exc:
        raise ValueError("Широта и долгота должны быть числами.") from exc

    if not (-90 <= lat <= 90):
        raise ValueError("Широта должна быть в диапазоне от -90 до 90.")
    if not (-180 <= lon <= 180):
        raise ValueError("Долгота должна быть в диапазоне от -180 до 180.")

    return lat, lon


def _same_geo(lat1: float, lng1: float, lat2: float, lng2: float) -> bool:
    return abs(lat1 - lat2) < _GEO_EPS and abs(lng1 - lng2) < _GEO_EPS


def elevation_cache_valid(cfg: dict[str, Any], lat: float, lng: float) -> bool:
    """True, если в cfg уже есть высота для тех же координат (см. elevation_cache_lat/lng)."""
    em = cfg.get("elevation_m")
    if em is None:
        return False
    try:
        float(em)
    except (TypeError, ValueError):
        return False
    clat = cfg.get("elevation_cache_lat")
    clng = cfg.get("elevation_cache_lng")
    if clat is None or clng is None:
        return False
    try:
        return _same_geo(float(clat), float(clng), lat, lng)
    except (TypeError, ValueError):
        return False


def elevation_api_url(latitude: float, longitude: float) -> str:
    """Полный URL запроса к Open-Meteo Elevation API (для логов и отладки)."""
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
        }
    )
    return f"{API_URL}?{query}"


def get_elevation_cached(
    cfg: dict[str, Any],
    lat: float,
    lng: float,
    *,
    timeout: int = 15,
    response_body_preview: list[str] | None = None,
) -> float:
    """
    Возвращает высоту для (lat, lng): из кэша в cfg при совпадении геопозиции, иначе запрос API.
    При сетевом запросе обновляет elevation_m и elevation_cache_lat / elevation_cache_lng.
    """
    if elevation_cache_valid(cfg, lat, lng):
        return float(cfg["elevation_m"])
    elev = fetch_elevation(
        lat,
        lng,
        timeout=timeout,
        response_body_preview=response_body_preview,
    )
    cfg["elevation_m"] = elev
    cfg["elevation_cache_lat"] = lat
    cfg["elevation_cache_lng"] = lng
    return elev


def fetch_elevation(
    latitude: float,
    longitude: float,
    timeout: int = 15,
    *,
    response_body_preview: list[str] | None = None,
) -> float:
    url = elevation_api_url(latitude, longitude)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            if response_body_preview is not None:
                response_body_preview.append(body[:500])
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
            detail = raw.decode("utf-8", errors="replace") if raw else ""
        except OSError:
            detail = ""
        msg = f"HTTP {exc.code} {exc.reason}"
        if detail.strip():
            msg += f": {detail.strip()[:500]}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Сетевая ошибка при запросе высоты: {exc.reason}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ответ сервера не является корректным JSON.") from exc

    if "elevation" not in data:
        raise RuntimeError(f"Неожиданный ответ API: {data}")

    elevation = data["elevation"]

    if isinstance(elevation, (int, float)):
        return float(elevation)

    if isinstance(elevation, list):
        if not elevation:
            raise RuntimeError("API вернул пустой список elevation.")
        if not isinstance(elevation[0], (int, float)):
            raise RuntimeError(f"Некорректное значение elevation[0]: {elevation[0]!r}")
        return float(elevation[0])

    raise RuntimeError(f"Некорректное значение elevation: {elevation!r}")
