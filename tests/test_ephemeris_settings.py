from gps_sim import settings as s


def test_broadcast_ephemeris_file(tmp_path, monkeypatch) -> None:
    settings_json = tmp_path / "settings.json"
    monkeypatch.setattr(s, "settings_path", lambda: settings_json)
    ephem = tmp_path / "ephemeris"
    monkeypatch.setattr(s, "ephemeris_dir", lambda: ephem)

    assert s.broadcast_ephemeris_file({}) is None
    full = (ephem / "brdc0100.26n").resolve()
    p = s.broadcast_ephemeris_file({"broadcast_ephemeris_path": str(full)})
    assert p == full
