"""Загрузка последнего broadcast-файла BRDC с CDDIS (Earthdata)."""

from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

EARTHDATA_LOGIN_HOST = "urs.earthdata.nasa.gov"
CDDIS_BRDC_CATALOG = "https://cddis.nasa.gov/archive/gnss/data/daily/{year}/brdc/"
CURL_TIMEOUT_SEC = 300
BRDC_MIN_INTERVAL = timedelta(hours=1)


def brdc_catalog_url(year: int) -> str:
    return CDDIS_BRDC_CATALOG.format(year=year)


def brdc_gz_pattern(year: int) -> re.Pattern[str]:
    yy = year % 100
    return re.compile(rf"brdc(\d{{4}})\.{yy:02d}n\.gz\b", re.IGNORECASE)


def find_latest_brdc_gz_filename(html: str, year: int) -> str:
    """Из HTML каталога выбирает имя brdc*.yyN.gz с максимальным 4-значным суффиксом."""
    pat = brdc_gz_pattern(year)
    matches = pat.findall(html)
    if not matches:
        msg = (
            "Не удалось найти ни одного подходящего brdc*.yyN.gz. "
            "Возможна ошибка аутентификации или изменилась вёрстка каталога."
        )
        raise RuntimeError(msg)
    latest_suffix = max(matches, key=lambda x: int(x))
    yy = year % 100
    return f"brdc{latest_suffix}.{yy:02d}n.gz"


def parse_ephemeris_updated_at(cfg: dict[str, Any]) -> datetime | None:
    """Разбирает broadcast_ephemeris_updated_at (ISO 8601) в UTC или None."""
    raw = cfg.get("broadcast_ephemeris_updated_at")
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _which_curl() -> str:
    path = shutil.which("curl")
    if not path:
        msg = "Не найден исполняемый файл «curl». Установите curl или добавьте его в PATH."
        raise RuntimeError(msg)
    return path


def _run_curl(
    url: str,
    netrc_file: Path,
    cookie_file: Path,
    *,
    output_file: Path | None = None,
) -> str:
    curl = _which_curl()
    cmd = [
        curl,
        "-L",
        "--fail",
        "--silent",
        "--show-error",
        "--netrc-file",
        str(netrc_file),
        "-c",
        str(cookie_file),
        "-b",
        str(cookie_file),
        url,
    ]
    if output_file is not None:
        cmd.extend(["-o", str(output_file)])

    result = subprocess.run(
        cmd,
        capture_output=output_file is None,
        text=output_file is None,
        check=False,
        timeout=CURL_TIMEOUT_SEC,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "unknown curl error"
        msg = f"curl завершился с ошибкой для {url}: {stderr}"
        raise RuntimeError(msg)
    return result.stdout if output_file is None else ""


def _write_netrc(tmpdir: Path, login: str, password: str) -> Path:
    netrc_path = tmpdir / ".netrc"
    netrc_path.write_text(
        f"machine {EARTHDATA_LOGIN_HOST} login {login} password {password}\n",
        encoding="utf-8",
    )
    os.chmod(netrc_path, 0o600)
    return netrc_path


def verify_earthdata_credentials(
    login: str,
    password: str,
    *,
    year: int | None = None,
) -> None:
    """
    Проверяет логин/пароль Earthdata: запрос каталога CDDIS и разбор списка brdc*.yyN.gz.
    Полный файл не скачивается.
    """
    y = year if year is not None else datetime.now().year
    base_url = brdc_catalog_url(y)
    with tempfile.TemporaryDirectory(prefix="gps_sim_earthdata_") as tmp:
        tmpdir = Path(tmp)
        netrc_file = _write_netrc(tmpdir, login, password)
        cookie_file = tmpdir / "cookies.txt"
        html = _run_curl(base_url, netrc_file, cookie_file)
        find_latest_brdc_gz_filename(html, y)


def gunzip_file(gz_path: Path) -> Path:
    if gz_path.suffix != ".gz":
        msg = f"Ожидался .gz файл, получено: {gz_path}"
        raise ValueError(msg)
    out_path = gz_path.with_suffix("")
    with gzip.open(gz_path, "rb") as f_in, open(out_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return out_path


def _log_line(
    log: Callable[[str], None] | None,
    msg: str,
) -> None:
    if log is not None:
        log(msg)
    else:
        print(msg)


def download_latest_broadcast_ephemeris(
    login: str,
    password: str,
    output_dir: Path,
    *,
    year: int,
    force_update: bool = False,
    last_updated_at: datetime | None = None,
    existing_unpacked_path: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[Path, bool]:
    """
    Скачивает последний по имени brdc*.yyN.gz из каталога CDDIS за указанный год,
    распаковывает в output_dir и удаляет .gz. Возвращает (путь к .yyN, был_ли_реальный_скачивание).

    Если не force_update, локальный файл есть и last_updated_at новее чем BRDC_MIN_INTERVAL назад —
    загрузка пропускается, возвращается existing_unpacked_path и False.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    _log_line(log, f"[BRDC] Каталог назначения: {output_dir.resolve()}")
    _log_line(log, f"[BRDC] Год каталога CDDIS: {year}")

    if not force_update:
        if existing_unpacked_path is None or not existing_unpacked_path.is_file():
            _log_line(
                log,
                "[BRDC] Локальный распакованный файл не найден или путь не задан — загрузка нужна.",
            )
        elif last_updated_at is None:
            _log_line(
                log,
                "[BRDC] В настройках нет времени последнего успешного обновления — загрузка.",
            )
        else:
            age = now - last_updated_at.astimezone(timezone.utc)
            _log_line(
                log,
                f"[BRDC] Последнее успешное обновление (UTC): {last_updated_at.isoformat()}",
            )
            _log_line(log, f"[BRDC] Возраст данных: {age}")
            if age < BRDC_MIN_INTERVAL:
                _log_line(
                    log,
                    f"[BRDC] Пропуск загрузки: прошло менее {BRDC_MIN_INTERVAL} "
                    f"и файл на диске есть ({existing_unpacked_path.name}).",
                )
                _log_line(
                    log,
                    f"[BRDC] Используется существующий файл: {existing_unpacked_path.resolve()}",
                )
                return existing_unpacked_path.resolve(), False
            _log_line(log, "[BRDC] Интервал истёк — выполняется загрузка с CDDIS.")
    else:
        _log_line(log, "[BRDC] Принудительное обновление: проверка по времени отключена.")

    base_url = brdc_catalog_url(year)
    _log_line(log, f"[BRDC] URL каталога: {base_url}")

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="gps_sim_earthdata_") as tmp:
        tmpdir = Path(tmp)
        netrc_file = _write_netrc(tmpdir, login, password)
        _log_line(log, f"[BRDC] Временный netrc для {EARTHDATA_LOGIN_HOST}: {netrc_file}")
        cookie_file = tmpdir / "cookies.txt"

        _log_line(log, "[BRDC] Запрос HTML каталога (curl)...")
        html = _run_curl(base_url, netrc_file, cookie_file)
        t_cat = time.perf_counter() - t0
        _log_line(log, f"[BRDC] Каталог получен за {t_cat:.2f} с, размер HTML: {len(html)} байт")

        latest_name = find_latest_brdc_gz_filename(html, year)
        file_url = urljoin(base_url, latest_name)
        gz_path = output_dir / latest_name

        _log_line(log, f"[BRDC] Выбран последний по имени файл: {latest_name}")
        _log_line(log, f"[BRDC] URL файла: {file_url}")

        t_dl = time.perf_counter()
        _log_line(log, "[BRDC] Скачивание .gz (curl -o)...")
        _run_curl(file_url, netrc_file, cookie_file, output_file=gz_path)
        dt_dl = time.perf_counter() - t_dl
        sz = gz_path.stat().st_size if gz_path.is_file() else 0
        _log_line(log, f"[BRDC] Скачивание завершено за {dt_dl:.2f} с, размер .gz: {sz} байт")

        if not gz_path.is_file() or gz_path.stat().st_size == 0:
            msg = f"Файл отсутствует или пустой после загрузки: {gz_path}"
            raise RuntimeError(msg)

        _log_line(log, f"[BRDC] Распаковка gzip → {gz_path.with_suffix('').name}")
        unpacked = gunzip_file(gz_path)
        gz_path.unlink(missing_ok=True)

    total = time.perf_counter() - t0
    _log_line(log, f"[BRDC] Готово: {unpacked.resolve()} (всего {total:.2f} с)")
    return unpacked.resolve(), True
