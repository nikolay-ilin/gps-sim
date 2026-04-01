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


def test_fetch_elevation_invalid_json() -> None:
    class _CM:
        def __enter__(self):
            return io.BytesIO(b"not json")

        def __exit__(self, *args):
            return None

    with patch("urllib.request.urlopen", return_value=_CM()):
        with pytest.raises(RuntimeError, match="JSON"):
            el.fetch_elevation(0.0, 0.0)
