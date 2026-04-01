"""Разбор broadcast RINEX NAV для согласования времени старта с gps-sdr-sim."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Как в gpssim.h (gps-sdr-sim)
SECONDS_IN_HOUR = 3600.0
SECONDS_IN_WEEK = 604800.0
MAX_SAT = 32


@dataclass(frozen=True)
class _GpsTime:
    week: int
    sec: float

    def sub(self, other: _GpsTime) -> float:
        return (
            self.sec
            - other.sec
            + float(self.week - other.week) * SECONDS_IN_WEEK
        )


def _date2gps(dt: datetime) -> _GpsTime:
    """Эквивалент date2gps() из gpssim.c (UTC)."""
    t = dt.astimezone(timezone.utc)
    y, m, d = t.year, t.month, t.day
    hh = t.hour
    mm = t.minute
    sec = float(t.second) + t.microsecond * 1e-6

    doy = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    ye = y - 1980
    lpdays = ye // 4 + 1
    if (ye % 4) == 0 and m <= 2:
        lpdays -= 1
    de = ye * 365 + doy[m - 1] + d + lpdays - 6
    week = de // 7
    s = (de % 7) * 86400.0 + hh * 3600.0 + mm * 60.0 + sec
    return _GpsTime(week=week, sec=s)


def _replace_exp_designator(s: str) -> str:
    return s.replace("D", "E").replace("d", "e")


def _parse_rinex2_epoch_line(line: str) -> tuple[int, datetime] | None:
    """Первая строка блока эфемерид RINEX 2 (как readRinexNavAll)."""
    if len(line) < 22:
        return None
    try:
        prn = int(line[0:2])
    except ValueError:
        return None
    if not (1 <= prn <= MAX_SAT):
        return None
    yy = int(line[3:5]) + 2000
    mo = int(line[6:8])
    day = int(line[9:11])
    hh = int(line[12:14])
    mm = int(line[15:17])
    sec_s = line[18:22]
    sec = float(_replace_exp_designator(sec_s.strip()))
    dt = datetime(yy, mo, day, hh, mm, int(sec), tzinfo=timezone.utc)
    if sec % 1:
        dt = dt.replace(microsecond=int(round((sec % 1) * 1e6)))
    return prn - 1, dt


def _parse_rinex3_gps_epoch_line(line: str) -> tuple[int, datetime] | None:
    """Первая строка блока GPS в RINEX 3: 'G01  2022 01 10 00 00 00.00000000'."""
    if len(line) < 23 or line[0] != "G":
        return None
    m = re.match(
        r"^G(\d{2})\s+(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d+\.?\d*)",
        line.strip(),
    )
    if not m:
        return None
    prn = int(m.group(1))
    if not (1 <= prn <= MAX_SAT):
        return None
    yy, mo, day, hh, mm = (int(m.group(i)) for i in range(2, 7))
    sec = float(m.group(8))
    dt = datetime(yy, mo, day, hh, mm, int(sec), tzinfo=timezone.utc)
    if sec % 1:
        dt = dt.replace(microsecond=int(round((sec % 1) * 1e6)))
    return prn - 1, dt


def _rinex_version_from_header(header_lines: list[str]) -> float | None:
    if not header_lines:
        return None
    first = header_lines[0]
    parts = first.split()
    if not parts:
        return None
    try:
        return float(parts[0])
    except ValueError:
        return None


def broadcast_nav_time_bounds(path: Path) -> tuple[datetime, datetime]:
    """
    Возвращает [tmin, tmax] в UTC — допустимый диапазон старта для gps-sdr-sim
    (как gmin/gmax после readRinexNavAll).

    Поддерживается RINEX 2 (как в upstream gps-sdr-sim) и RINEX 3 (только GPS G01–G32).
    """
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header: list[str] = []
    body_start = 0
    for line in text:
        header.append(line)
        if "END OF HEADER" in line:
            body_start = len(header)
            break
    else:
        msg = "В RINEX NAV нет END OF HEADER."
        raise ValueError(msg)

    ver = _rinex_version_from_header(header)
    rinex3 = ver is not None and ver >= 3.0

    # eph[ieph][sv] -> datetime epoch (только валидные записи)
    eph: list[list[datetime | None]] = []
    ieph = 0
    g0: _GpsTime | None = None

    line_idx = body_start
    while line_idx < len(text):
        line = text[line_idx]
        if rinex3:
            parsed = _parse_rinex3_gps_epoch_line(line)
        else:
            parsed = _parse_rinex2_epoch_line(line)

        if parsed is None:
            line_idx += 1
            continue

        sv, dt = parsed
        g = _date2gps(dt)

        if g0 is None:
            g0 = g
            eph.append([None] * MAX_SAT)
        else:
            dt_sub = g.sub(g0)
            if dt_sub > SECONDS_IN_HOUR:
                g0 = g
                ieph += 1
                eph.append([None] * MAX_SAT)

        eph[ieph][sv] = dt

        line_idx += 8

    if not eph or g0 is None:
        msg = "В файле нет GPS broadcast-эфемерид (RINEX 2 или GPS в RINEX 3)."
        raise ValueError(msg)

    neph = len(eph)

    tmin: datetime | None = None
    for sv in range(MAX_SAT):
        t = eph[0][sv]
        if t is not None:
            tmin = t
            break
    if tmin is None:
        msg = "Не найдена ни одна валидная эфемерида в первом наборе (как в gps-sdr-sim)."
        raise ValueError(msg)

    tmax: datetime | None = None
    for sv in range(MAX_SAT):
        t = eph[neph - 1][sv]
        if t is not None:
            tmax = t
            break
    if tmax is None:
        msg = "Не найдена ни одна валидная эфемерида в последнем наборе."
        raise ValueError(msg)

    return (tmin, tmax)


def clamp_utc_start_to_nav_bounds(
    desired: datetime,
    tmin: datetime,
    tmax: datetime,
) -> tuple[datetime, bool]:
    """
    Ограничивает момент старта [tmin, tmax] по правилам gps-sdr-sim (g0 между gmin и gmax).

    Возвращает (скорректированное_utc, было_ли_изменение).
    """
    if desired.tzinfo is None:
        desired = desired.replace(tzinfo=timezone.utc)
    d = desired.astimezone(timezone.utc)
    lo = tmin if tmin.tzinfo else tmin.replace(tzinfo=timezone.utc)
    hi = tmax if tmax.tzinfo else tmax.replace(tzinfo=timezone.utc)
    lo = lo.astimezone(timezone.utc)
    hi = hi.astimezone(timezone.utc)

    gd = _date2gps(d)
    gmin = _date2gps(lo)
    gmax = _date2gps(hi)

    if gd.sub(gmin) < 0.0:
        return lo, True
    if gmax.sub(gd) < 0.0:
        return hi, True
    return d, False


def format_gps_sdr_sim_time(dt: datetime) -> str:
    """Строка для ключа -t: YYYY/MM/DD,hh:mm:ss (секунды целые, как sscanf в gpssim)."""
    u = dt.astimezone(timezone.utc)
    return f"{u.year:04d}/{u.month:02d}/{u.day:02d},{u.hour:02d}:{u.minute:02d}:{int(u.second):02d}"
