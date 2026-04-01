import io
import json
from unittest.mock import patch

import pytest

from gps_sim import elevation as el


def test_parse_coordinates_ok() -> None:
    assert el.parse_coordinates("53.4462, -113.4209") == (53.4462, -113.4209)


def test_parse_coordinates_extra_comma() -> None:
    with pytest.raises(ValueError, match="лишние запятые"):
        el.parse_coordinates("53, 44, -113")


def test_parse_coordinates_invalid_lat_range() -> None:
    with pytest.raises(ValueError, match="Широта"):
        el.parse_coordinates("91, 0")


def test_fetch_elevation_scalar_json() -> None:
    body = json.dumps({"elevation": 42.5}).encode("utf-8")
    mock_resp = io.BytesIO(body)
    mock_resp.status = 200

    class _CM:
        def __enter__(self):
            return mock_resp

        def __exit__(self, *args):
            return None

    with patch("urllib.request.urlopen", return_value=_CM()):
        assert el.fetch_elevation(1.0, 2.0) == 42.5


def test_fetch_elevation_list_json() -> None:
    body = json.dumps({"elevation": [100.0]}).encode("utf-8")
    mock_resp = io.BytesIO(body)
    mock_resp.status = 200

    class _CM:
        def __enter__(self):
            return mock_resp

        def __exit__(self, *args):
            return None

    with patch("urllib.request.urlopen", return_value=_CM()):
        assert el.fetch_elevation(0.0, 0.0) == 100.0


def test_get_elevation_cached_hit_no_fetch(monkeypatch) -> None:
    def _no_fetch(*_a: object, **_k: object) -> float:
        raise AssertionError("fetch_elevation should not be called")

    monkeypatch.setattr(el, "fetch_elevation", _no_fetch)
    cfg = {
        "elevation_m": 100.0,
        "elevation_cache_lat": 55.0,
        "elevation_cache_lng": 37.0,
    }
    assert el.get_elevation_cached(cfg, 55.0, 37.0) == 100.0


def test_get_elevation_cached_miss_fetches_and_stores(monkeypatch) -> None:
    monkeypatch.setattr(
        el,
        "fetch_elevation",
        lambda la, ln, timeout=15, response_body_preview=None: 42.0,
    )
    cfg: dict = {}
    assert el.get_elevation_cached(cfg, 1.0, 2.0) == 42.0
    assert cfg["elevation_m"] == 42.0
    assert cfg["elevation_cache_lat"] == 1.0
    assert cfg["elevation_cache_lng"] == 2.0


def test_fetch_elevation_invalid_json() -> None:
    class _CM:
        def __enter__(self):
            return io.BytesIO(b"not json")

        def __exit__(self, *args):
            return None

    with patch("urllib.request.urlopen", return_value=_CM()):
        with pytest.raises(RuntimeError, match="JSON"):
            el.fetch_elevation(0.0, 0.0)
