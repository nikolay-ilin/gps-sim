"""Высота над уровнем моря по координатам (Open-Meteo Elevation API)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.open-meteo.com/v1/elevation"
USER_AGENT = "gps-sim/elevation"


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


def fetch_elevation(latitude: float, longitude: float, timeout: int = 15) -> float:
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
        }
    )
    url = f"{API_URL}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
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
