import gzip
from pathlib import Path

import pytest

from gps_sim.brdc_download import find_latest_brdc_gz_filename, gunzip_file


def test_find_latest_brdc_gz_filename_2026() -> None:
    html = """
    <a href="brdc0090.26n.gz">x</a>
    <a href="brdc0100.26n.gz">y</a>
    """
    assert find_latest_brdc_gz_filename(html, 2026) == "brdc0100.26n.gz"


def test_find_latest_brdc_gz_filename_2025() -> None:
    html = 'href="brdc0200.25n.gz" brdc0300.25n.gz'
    assert find_latest_brdc_gz_filename(html, 2025) == "brdc0300.25n.gz"


def test_find_latest_empty_raises() -> None:
    with pytest.raises(RuntimeError, match="Не удалось найти"):
        find_latest_brdc_gz_filename("<html></html>", 2026)


def test_gunzip_roundtrip(tmp_path: Path) -> None:
    gz = tmp_path / "test.26n.gz"
    payload = b"RINEX broadcast test\n"
    with gzip.open(gz, "wb") as f:
        f.write(payload)
    out = gunzip_file(gz)
    assert out.read_bytes() == payload
    assert out.suffix == ".26n"
