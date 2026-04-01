"""Загрузка последнего broadcast-файла BRDC с CDDIS (Earthdata)."""

from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

EARTHDATA_LOGIN_HOST = "urs.earthdata.nasa.gov"
CDDIS_BRDC_CATALOG = "https://cddis.nasa.gov/archive/gnss/data/daily/{year}/brdc/"
CURL_TIMEOUT_SEC = 300


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


def download_latest_broadcast_ephemeris(
    login: str,
    password: str,
    output_dir: Path,
    *,
    year: int,
) -> Path:
    """
    Скачивает последний по имени brdc*.yyN.gz из каталога CDDIS за указанный год,
    распаковывает в output_dir и удаляет .gz. Возвращает путь к распакованному .yyN файлу.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    base_url = brdc_catalog_url(year)

    with tempfile.TemporaryDirectory(prefix="gps_sim_earthdata_") as tmp:
        tmpdir = Path(tmp)
        netrc_file = _write_netrc(tmpdir, login, password)
        cookie_file = tmpdir / "cookies.txt"

        print(f"Обновление эфемерид broadcast: {base_url}")
        html = _run_curl(base_url, netrc_file, cookie_file)

        latest_name = find_latest_brdc_gz_filename(html, year)
        file_url = urljoin(base_url, latest_name)
        gz_path = output_dir / latest_name

        print(f"Актуальный файл: {latest_name}")
        _run_curl(file_url, netrc_file, cookie_file, output_file=gz_path)

        if not gz_path.is_file() or gz_path.stat().st_size == 0:
            msg = f"Файл отсутствует или пустой после загрузки: {gz_path}"
            raise RuntimeError(msg)

        unpacked = gunzip_file(gz_path)
        gz_path.unlink(missing_ok=True)

    print(f"{unpacked}")
    return unpacked
