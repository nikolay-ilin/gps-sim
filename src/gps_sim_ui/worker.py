"""Фоновый запуск: эфемериды, run_simulation."""

from __future__ import annotations

import io
import threading
from datetime import datetime, timezone

from PySide6.QtCore import QThread, Signal

from gps_sim.brdc_download import download_latest_broadcast_ephemeris, parse_ephemeris_updated_at
from gps_sim.elevation import elevation_cache_valid, get_elevation_cached
from gps_sim.run_sim import run_simulation
from gps_sim.settings import (
    DEFAULT_DURATION_MINUTES,
    broadcast_ephemeris_file,
    ephemeris_dir,
    load_settings,
    save_settings,
)


class SimulationWorker(QThread):
    """Обновляет настройки по точке и запускает конвейер симуляции."""

    log_line = Signal(str)
    # Не называть finished — это переопределяет QThread.finished и ломает завершение потока в Qt.
    run_finished = Signal(int)
    # Сразу перед run_simulation (конвейер gps-sdr-sim → hackrf).
    transmission_started = Signal()

    def __init__(self, lat: float, lng: float) -> None:
        super().__init__()
        self._lat = lat
        self._lng = lng
        self._cancel = threading.Event()

    def request_stop(self) -> None:
        """Остановка подготовки или передачи (gps-sdr-sim → HackRF)."""
        self._cancel.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            cfg = load_settings()
            cfg["lat"] = self._lat
            cfg["lng"] = self._lng
            duration = int(cfg.get("duration_minutes", DEFAULT_DURATION_MINUTES))
            cfg["duration_minutes"] = duration
            save_settings(cfg)

            if self._cancel.is_set():
                self.log_line.emit("Остановлено до начала подготовки.\n")
                self.run_finished.emit(130)
                return

            if not elevation_cache_valid(cfg, self._lat, self._lng):
                get_elevation_cached(cfg, self._lat, self._lng)
                save_settings(cfg)

            if self._cancel.is_set():
                self.log_line.emit("Остановлено до загрузки эфемерид.\n")
                self.run_finished.emit(130)
                return

            nasa_login = (cfg.get("nasa_login") or "").strip()
            nasa_pass = (cfg.get("nasa_pass") or "").strip()
            year = datetime.now().year
            buf_dl = io.StringIO()

            def brdc_log(msg: str) -> None:
                buf_dl.write(msg + "\n")

            unpacked, did_download = download_latest_broadcast_ephemeris(
                nasa_login,
                nasa_pass,
                ephemeris_dir(),
                year=year,
                force_update=False,
                last_updated_at=parse_ephemeris_updated_at(cfg),
                existing_unpacked_path=broadcast_ephemeris_file(cfg),
                log=brdc_log,
            )
            cfg["broadcast_ephemeris_path"] = str(unpacked.resolve())
            if did_download:
                cfg["broadcast_ephemeris_updated_at"] = datetime.now(timezone.utc).isoformat()
            save_settings(cfg)
            self.log_line.emit(buf_dl.getvalue())

            if self._cancel.is_set():
                self.log_line.emit("Остановлено до запуска передачи.\n")
                self.run_finished.emit(130)
                return

            self.log_line.emit("Начало трансляции.\n")
            self.transmission_started.emit()
            rc = run_simulation(cfg, interactive=False, cancel_event=self._cancel)
            if rc == 0:
                self.log_line.emit("Конец трансляции: успех.\n")
            elif rc == 130:
                self.log_line.emit("Конец трансляции: остановка.\n")
            else:
                self.log_line.emit(f"Конец трансляции: код выхода {rc}.\n")
            self.run_finished.emit(rc)
        except Exception as e:
            self.log_line.emit(f"Ошибка: {e}\n")
            self.run_finished.emit(1)
