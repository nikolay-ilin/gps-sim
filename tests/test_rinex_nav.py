from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from gps_sim.rinex_nav import (
    broadcast_nav_time_bounds,
    clamp_utc_start_to_nav_bounds,
    format_gps_sdr_sim_time,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "brdc_minimal.n"


def test_broadcast_nav_time_bounds_fixture() -> None:
    tmin, tmax = broadcast_nav_time_bounds(FIXTURE)
    assert tmin == datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert tmax == datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_clamp_before_tmin() -> None:
    lo = datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc)
    hi = datetime(2022, 1, 1, 14, 0, tzinfo=timezone.utc)
    want = datetime(2021, 12, 31, 12, 0, tzinfo=timezone.utc)
    out, adj = clamp_utc_start_to_nav_bounds(want, lo, hi)
    assert adj is True
    assert out == lo


def test_clamp_after_tmax() -> None:
    lo = datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc)
    hi = datetime(2022, 1, 1, 14, 0, tzinfo=timezone.utc)
    want = datetime(2022, 1, 2, 0, 0, tzinfo=timezone.utc)
    out, adj = clamp_utc_start_to_nav_bounds(want, lo, hi)
    assert adj is True
    assert out == hi


def test_format_gps_sdr_sim_time() -> None:
    dt = datetime(2026, 4, 1, 14, 0, 7, 500000, tzinfo=timezone.utc)
    assert format_gps_sdr_sim_time(dt) == "2026/04/01,14:00:07"


def test_broadcast_nav_rejects_garbage(tmp_path: Path) -> None:
    p = tmp_path / "x.n"
    p.write_text("not rinex\n", encoding="utf-8")
    with pytest.raises(ValueError, match="END OF HEADER"):
        broadcast_nav_time_bounds(p)
