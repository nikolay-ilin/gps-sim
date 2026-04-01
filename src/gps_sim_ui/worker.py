"""Фоновый запуск: эфемериды, высота, run_simulation."""

from __future__ import annotations

import contextlib
import io
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from gps_sim.brdc_download import download_latest_broadcast_ephemeris
from gps_sim.elevation import fetch_elevation
from gps_sim.run_sim import run_simulation
from gps_sim.settings import (
    DEFAULT_DURATION_MINUTES,
    ephemeris_dir,
    load_settings,
    save_settings,
)


class SimulationWorker(QThread):
    """Обновляет настройки по точке и запускает конвейер симуляции."""

    log_line = Signal(str)
    finished = Signal(int)

    def __init__(self, lat: float, lng: float) -> None:
        super().__init__()
        self._lat = lat
        self._lng = lng

    def run(self) -> None:
        try:
            cfg = load_settings()
            cfg["lat"] = self._lat
            cfg["lng"] = self._lng
            duration = int(cfg.get("duration_minutes", DEFAULT_DURATION_MINUTES))
            cfg["duration_minutes"] = duration
            save_settings(cfg)

            self.log_line.emit("Получение высоты по координатам…\n")
            elev = fetch_elevation(self._lat, self._lng)
            cfg["elevation_m"] = elev
            save_settings(cfg)
            self.log_line.emit(f"Высота: {elev:.2f} м\n")

            nasa_login = (cfg.get("nasa_login") or "").strip()
            nasa_pass = (cfg.get("nasa_pass") or "").strip()
            year = datetime.now().year
            buf_dl = io.StringIO()
            with contextlib.redirect_stdout(buf_dl), contextlib.redirect_stderr(buf_dl):
                unpacked = download_latest_broadcast_ephemeris(
                    nasa_login,
                    nasa_pass,
                    ephemeris_dir(),
                    year=year,
                )
            cfg["broadcast_ephemeris_path"] = str(unpacked.resolve())
            save_settings(cfg)
            self.log_line.emit(buf_dl.getvalue())

            self.log_line.emit("Запуск симуляции (gps-sdr-sim → HackRF)…\n")
            buf_run = io.StringIO()
            with contextlib.redirect_stdout(buf_run), contextlib.redirect_stderr(buf_run):
                rc = run_simulation(cfg, interactive=False)
            self.log_line.emit(buf_run.getvalue())
            if rc != 0:
                self.log_line.emit(f"Код выхода: {rc}\n")
            self.finished.emit(rc)
        except Exception as e:
            self.log_line.emit(f"Ошибка: {e}\n")
            self.finished.emit(1)
