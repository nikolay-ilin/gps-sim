"""Фоновое получение высоты после выбора точки на карте."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from gps_sim.elevation import (
    elevation_api_url,
    elevation_cache_valid,
    get_elevation_cached,
)
from gps_sim.settings import load_settings, save_settings


class ElevationFetchThread(QThread):
    """Обновляет lat/lng в настройках и запрашивает высоту (с кэшем)."""

    elevation_ready = Signal(float, float, float)  # lat, lng, elev_m
    failed = Signal(str)
    log_line = Signal(str)

    def __init__(self, lat: float, lng: float, seq: int) -> None:
        super().__init__()
        self._lat = lat
        self._lng = lng
        self._seq = seq

    @property
    def request_seq(self) -> int:
        return self._seq

    def run(self) -> None:
        url = elevation_api_url(self._lat, self._lng)
        self.log_line.emit(
            f"[высота #{self._seq}] точка {self._lat:.6f}, {self._lng:.6f}\n",
        )
        try:
            cfg = load_settings()
            cfg["lat"] = self._lat
            cfg["lng"] = self._lng
            save_settings(cfg)

            cached = elevation_cache_valid(cfg, self._lat, self._lng)
            if cached:
                self.log_line.emit(
                    f"[высота #{self._seq}] кэш по координатам совпадает, "
                    "HTTP-запрос не выполняется\n",
                )
            else:
                self.log_line.emit(f"[высота #{self._seq}] запрос: GET {url}\n")

            preview: list[str] = []
            elev = get_elevation_cached(
                cfg,
                self._lat,
                self._lng,
                response_body_preview=preview,
            )
            save_settings(cfg)

            if preview:
                frag = preview[0].replace("\n", " ")
                self.log_line.emit(
                    f"[высота #{self._seq}] ответ (фрагмент): {frag!r}\n",
                )
            self.log_line.emit(
                f"[высота #{self._seq}] готово: высота {elev:.2f} м\n",
            )
            self.elevation_ready.emit(self._lat, self._lng, elev)
        except Exception as e:
            self.log_line.emit(f"[высота #{self._seq}] ошибка: {e}\n")
            self.failed.emit(str(e))
