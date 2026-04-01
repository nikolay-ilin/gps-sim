import json

from gps_sim import history as h


def test_history_roundtrip_and_sort(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(h, "history_path", lambda: tmp_path / "history.json")

    assert h.load_history_entries() == []
    h.record_transmission(1.0, 2.0, 100.0)
    data = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert len(data["entries"]) == 1
    assert data["entries"][0]["lat"] == 1.0
    assert data["entries"][0]["lng"] == 2.0
    assert data["entries"][0]["elevation_m"] == 100.0
    assert "started_at" in data["entries"][0]


def test_same_coords_updates_time_not_duplicate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(h, "history_path", lambda: tmp_path / "history.json")

    from datetime import datetime, timezone

    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 1, 15, 30, 0, tzinfo=timezone.utc)
    h.record_transmission(55.751244, 37.618423, 150.0, started_at=t1)
    h.record_transmission(55.7512440001, 37.6184230002, 200.0, started_at=t2)
    entries = h.load_history_entries()
    assert len(entries) == 1
    assert entries[0]["elevation_m"] == 200.0
    expected_iso = t2.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    assert entries[0]["started_at"] == expected_iso


def test_sorted_newest_first(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(h, "history_path", lambda: tmp_path / "history.json")

    from datetime import datetime, timezone

    h.record_transmission(1.0, 1.0, 1.0, datetime(2020, 1, 1, tzinfo=timezone.utc))
    h.record_transmission(2.0, 2.0, 2.0, datetime(2025, 1, 1, tzinfo=timezone.utc))
    s = h.sorted_history_entries()
    assert [round(e["lat"], 1) for e in s] == [2.0, 1.0]
