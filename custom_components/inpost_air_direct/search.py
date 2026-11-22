"""Pure search helpers over the locker catalog (no I/O, no Home Assistant)."""
from __future__ import annotations

from collections.abc import Iterable
from math import asin, cos, radians, sin, sqrt
import unicodedata

from .api import Locker

_EARTH_RADIUS_M = 6_371_000


def normalize(text: str) -> str:
    """Case-, diacritic- and separator-insensitive form ("Dzierżoniów" -> "dzierzoniow")."""
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.casefold().replace("-", " ").split())


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * asin(sqrt(a))


def nearby(
    lockers: Iterable[Locker], latitude: float, longitude: float, radius_m: float
) -> list[tuple[Locker, float]]:
    """Lockers within radius, nearest first, with their distance."""
    found = (
        (locker, distance_m(latitude, longitude, locker.latitude, locker.longitude))
        for locker in lockers
    )
    return sorted(((l, d) for l, d in found if d <= radius_m), key=lambda x: x[1])


def by_city(lockers: Iterable[Locker], query: str, limit: int) -> list[Locker]:
    """Exact (normalized) city matches; falls back to prefix, then substring matches."""
    q = normalize(query)
    if not q:
        return []
    lockers = list(lockers)
    for match in (
        lambda c: c == q,
        lambda c: c.startswith(q),
        lambda c: q in c,
    ):
        hits = [l for l in lockers if match(normalize(l.city))]
        if hits:
            hits.sort(key=lambda l: (normalize(l.city), l.province, normalize(l.street), l.building_number, l.code))
            return hits[:limit]
    return []
