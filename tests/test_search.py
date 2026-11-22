"""Pure search helpers."""
from __future__ import annotations

import pytest

from custom_components.inpost_air_direct.api import Locker
from custom_components.inpost_air_direct.search import by_city, distance_m, nearby, normalize


def L(code: str, city: str, lat: float = 50.0, lon: float = 16.0, province: str = "", street: str = "") -> Locker:
    return Locker(code=code, latitude=lat, longitude=lon, city=city, province=province, street=street)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Dzierżoniów", "dzierzoniow"), ("ŁÓDŹ", "lodz"), ("  Bielsko-Biała ", "bielsko biala"), ("Zielona  Góra", "zielona gora")],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected


def test_distance() -> None:
    # Warsaw -> Kraków is ~252 km
    assert distance_m(52.2297, 21.0122, 50.0647, 19.9450) == pytest.approx(252_000, rel=0.01)


def test_nearby_sorted_and_bounded() -> None:
    a, b, c = L("A", "x", 50.0, 16.0), L("B", "x", 50.01, 16.0), L("C", "x", 51.0, 16.0)
    result = nearby([c, b, a], 50.0, 16.0, 5000)
    assert [l.code for l, _ in result] == ["A", "B"]
    assert result[1][1] == pytest.approx(1112, abs=5)


def test_by_city_exact_beats_prefix() -> None:
    lockers = [L("1", "Nowa Wieś", province="b"), L("2", "Nowa Wieś Wielka"), L("3", "nowa wies", province="a")]
    assert [l.code for l in by_city(lockers, "NOWA WIES", 10)] == ["3", "1"]
    assert [l.code for l in by_city(lockers, "nowa wieś w", 10)] == ["2"]
    assert [l.code for l in by_city(lockers, "wielka", 10)] == ["2"]
    assert by_city(lockers, "   ", 10) == []
    assert len(by_city(lockers, "nowa", 1)) == 1
