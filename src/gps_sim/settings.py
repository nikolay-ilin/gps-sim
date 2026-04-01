"""Загрузка и сохранение пользовательских настроек между запусками."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DURATION_MINUTES = 24 * 60

# Параметры конвейера gps-sdr-sim → hackrf_transfer (можно переопределить в settings.json).
# hackrf_transfer_path — необязательный полный путь к бинарю, если его нет в PATH (например GUI без shell PATH).
DEFAULT_SIM_BITS = 8
DEFAULT_SIM_SAMPLE_RATE_HZ = 2_600_000
DEFAULT_HACKRF_FREQ_HZ = 1_575_420_000
DEFAULT_HACKRF_TX_GAIN = 47
DEFAULT_HACKRF_AMP = 1

# UI: ui_show_logs_panel — bool, показывать ли панель журнала справа (50% ширины).
# UI: ui_fullscreen — bool, запускать ли окно в полноэкранном режиме (как в последнем сеансе).
# История трансляций: файл history.json в том же каталоге, что и settings.json (см. gps_sim.history).

def settings_path() -> Path:
    """Путь к файлу настроек. Переменная GPS_SIM_SETTINGS — полный путь к JSON (для тестов)."""
    env = os.environ.get("GPS_SIM_SETTINGS")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "gps-sim" / "settings.json"
    return Path.home() / ".config" / "gps-sim" / "settings.json"


def ephemeris_dir() -> Path:
    """Каталог для распакованных broadcast-эфемерид (рядом с каталогом настроек)."""
    env = os.environ.get("GPS_SIM_EPHEMERIS_DIR")
    if env:
        return Path(env).expanduser()
    return settings_path().parent / "ephemeris"


def broadcast_ephemeris_file(cfg: dict[str, Any]) -> Path | None:
    """
    Путь к последнему распакованному BRDC, если полный путь задан в настройках.

    Связанные ключи JSON:
    - broadcast_ephemeris_path — полный путь к распакованному .yyN;
    - broadcast_ephemeris_updated_at — ISO 8601 (UTC) времени последнего успешного скачивания.
    """
    raw = cfg.get("broadcast_ephemeris_path")
    if not raw:
        return None
    return Path(str(raw)).expanduser().resolve()


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
