"""Фоновая загрузка broadcast-эфемерид BRDC (CDDIS)."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QThread, Signal

from gps_sim.brdc_download import download_latest_broadcast_ephemeris, parse_ephemeris_updated_at
from gps_sim.settings import broadcast_ephemeris_file, ephemeris_dir, load_settings, save_settings


class BrdcFetchThread(QThread):
    """Скачивает BRDC при наличии nasa_login / nasa_pass в настройках."""

    log_line = Signal(str)
    succeeded = Signal(object, bool)
    failed = Signal(str)

    def __init__(self, force_update: bool) -> None:
        super().__init__()
        self._force_update = force_update

    def run(self) -> None:
        cfg = load_settings()
        login = (cfg.get("nasa_login") or "").strip()
        password = (cfg.get("nasa_pass") or "").strip()
        if not login or not password:
            self.log_line.emit(
                "[BRDC] Запрос пропущен: нет логина/пароля NASA Earthdata в настройках.\n",
            )
            return

        try:
            year = datetime.now().year

            def emit_log(msg: str) -> None:
                self.log_line.emit(msg + "\n")

            path, did_download = download_latest_broadcast_ephemeris(
                login,
                password,
                ephemeris_dir(),
                year=year,
                force_update=self._force_update,
                last_updated_at=parse_ephemeris_updated_at(cfg),
                existing_unpacked_path=broadcast_ephemeris_file(cfg),
                log=emit_log,
            )
            cfg = load_settings()
            cfg["broadcast_ephemeris_path"] = str(path.resolve())
            if did_download:
                cfg["broadcast_ephemeris_updated_at"] = datetime.now(timezone.utc).isoformat()
            save_settings(cfg)
            self.succeeded.emit(path, did_download)
        except Exception as e:
            self.failed.emit(str(e))
