import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from gps_sim import brdc_download as brdc_download_mod
from gps_sim.brdc_download import (
    download_latest_broadcast_ephemeris,
    find_latest_brdc_gz_filename,
    gunzip_file,
    parse_ephemeris_updated_at,
    verify_earthdata_credentials,
)


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


def test_verify_earthdata_credentials_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_curl(
        _url: str,
        _netrc_file: Path,
        _cookie_file: Path,
        *,
        output_file: Path | None = None,
    ) -> str:
        assert output_file is None
        return '<a href="brdc0100.26n.gz">x</a>'

    monkeypatch.setattr(brdc_download_mod, "_run_curl", fake_run_curl)
    verify_earthdata_credentials("user", "secret", year=2026)


def test_parse_ephemeris_updated_at_ok() -> None:
    cfg = {"broadcast_ephemeris_updated_at": "2026-04-01T12:00:00+00:00"}
    dt = parse_ephemeris_updated_at(cfg)
    assert dt is not None
    assert dt.year == 2026 and dt.month == 4


def test_parse_ephemeris_updated_at_bad() -> None:
    assert parse_ephemeris_updated_at({"broadcast_ephemeris_updated_at": "not-a-date"}) is None


def test_download_skips_when_file_recent(tmp_path: Path) -> None:
    p = tmp_path / "brdc0100.26n"
    p.write_text("RINEX broadcast test\n")
    recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    cfg = {"broadcast_ephemeris_updated_at": recent}
    path, did_download = download_latest_broadcast_ephemeris(
        "u",
        "p",
        tmp_path,
        year=2026,
        force_update=False,
        last_updated_at=parse_ephemeris_updated_at(cfg),
        existing_unpacked_path=p,
        log=lambda _m: None,
    )
    assert did_download is False
    assert path == p.resolve()


def test_gunzip_roundtrip(tmp_path: Path) -> None:
    gz = tmp_path / "test.26n.gz"
    payload = b"RINEX broadcast test\n"
    with gzip.open(gz, "wb") as f:
        f.write(payload)
    out = gunzip_file(gz)
    assert out.read_bytes() == payload
    assert out.suffix == ".26n"
