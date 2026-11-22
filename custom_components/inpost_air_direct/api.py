"""HTTP client for the unofficial InPost points / air-sensors endpoints.

Deliberately free of Home Assistant imports so it can be unit-tested standalone.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from aiohttp import ClientConnectionError, ClientError, ClientSession

from .const import (
    AIR_SENSORS_URL,
    CATALOG_FIELDS,
    CATALOG_MAX_PAGES,
    CATALOG_PAGE_SIZE,
    MAX_RETRY_DELAY,
    POINTS_URL,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF,
)

_LOGGER = logging.getLogger(__name__)
_HEADERS = {"Accept": "application/json"}


class InPostAirError(Exception):
    """Raised when data cannot be retrieved or parsed."""


class InPostAirNotFound(InPostAirError):
    """Raised when the locker does not exist or exposes no air sensors (HTTP 404)."""


class _RetryableError(Exception):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# --------------------------------------------------------------------------- readings


@dataclass(frozen=True)
class AirReading:
    """Normalized air-sensors response."""

    values: dict[str, float]
    levels: dict[str, str]
    index_value: float | None = None
    index_level: str | None = None
    index_name: str | None = None
    from_time: datetime | None = None
    till_time: datetime | None = None
    # Percent of a health standard's limit, keyed by pollutant (e.g. {"PM25": 55.4}).
    standards: dict[str, float] = field(default_factory=dict)
    standard_names: dict[str, str] = field(default_factory=dict)
    # Observed: 1 = older hardware (no PM4, sometimes NO2/O3), 2 = newer hardware.
    sensor_origin: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def temperature(self) -> float | None:
        return self.values.get("TEMPERATURE")

    def age(self, now: datetime) -> timedelta | None:
        """Time since the measurement window ended."""
        return None if self.till_time is None else now - self.till_time

    def is_stale(self, now: datetime, max_age: timedelta) -> bool:
        """Return True when the measurement window ended more than max_age ago."""
        age = self.age(now)
        return age is not None and age > max_age


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _timestamp(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp into an aware UTC datetime; None if invalid."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_payload(payload: Any) -> AirReading:
    """Validate and normalize the observed current/values response shape."""
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise InPostAirError("Unexpected API response: missing current")
    current = payload["current"]
    raw_values = current.get("values")
    if not isinstance(raw_values, list):
        raise InPostAirError("Unexpected API response: missing values")

    values: dict[str, float] = {}
    levels: dict[str, str] = {}
    for item in raw_values:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"]
        if (value := _number(item.get("value"))) is not None:
            values[name] = value
        if (level := _string(item.get("level"))) is not None:
            levels[name] = level
    if not values:
        raise InPostAirError("Unexpected API response: no numeric measurements")

    index = current.get("index")
    index = index if isinstance(index, dict) else {}

    standards: dict[str, float] = {}
    standard_names: dict[str, str] = {}
    raw_standards = current.get("standards")
    for item in raw_standards if isinstance(raw_standards, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("pollutant"), str):
            continue
        if (percent := _number(item.get("percent"))) is not None:
            standards[item["pollutant"]] = percent
            if (name := _string(item.get("name"))) is not None:
                standard_names[item["pollutant"]] = name

    origin = payload.get("sensorOrigin")
    return AirReading(
        values=values,
        levels=levels,
        index_value=_number(index.get("value")),
        index_level=_string(index.get("level")),
        index_name=_string(index.get("name")),
        from_time=_timestamp(current.get("fromDateTime")),
        till_time=_timestamp(current.get("tillDateTime")),
        standards=standards,
        standard_names=standard_names,
        sensor_origin=origin if isinstance(origin, int) and not isinstance(origin, bool) else None,
        raw=payload,
    )


# --------------------------------------------------------------------------- lockers


@dataclass(frozen=True)
class Locker:
    """A parcel locker from the points catalog."""

    code: str
    latitude: float
    longitude: float
    city: str = ""
    street: str = ""
    building_number: str = ""
    post_code: str = ""
    province: str = ""
    description: str = ""
    air_level: str | None = None

    @property
    def address(self) -> str:
        return " ".join(p for p in (self.street, self.building_number) if p)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Locker:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def parse_point(item: Any) -> Locker | None:
    """Convert one points-API item into a Locker; None if essential data is missing."""
    if not isinstance(item, dict) or not (code := _string(item.get("name"))):
        return None
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    lat, lon = _number(location.get("latitude")), _number(location.get("longitude"))
    if lat is None or lon is None:
        return None
    details = item.get("address_details") if isinstance(item.get("address_details"), dict) else {}
    return Locker(
        code=code,
        latitude=lat,
        longitude=lon,
        city=_string(details.get("city")) or "",
        street=_string(details.get("street")) or "",
        building_number=_string(details.get("building_number")) or "",
        post_code=_string(details.get("post_code")) or "",
        province=_string(details.get("province")) or "",
        description=_string(item.get("location_description")) or "",
        air_level=_string(item.get("air_index_level")),
    )


def _retry_after(value: str | None) -> float | None:
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


# --------------------------------------------------------------------------- client


class InPostAirClient:
    """Thin async client; owns no session (Home Assistant's shared one is passed in)."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _get_json(self, url: str, params: dict[str, Any] | None = None, attempts: int = 1) -> Any:
        """GET JSON; retries timeouts, connection errors, HTTP 429 and 5xx with backoff."""
        last_error: Exception | None = None
        for attempt in range(attempts):
            delay = RETRY_BACKOFF * 2**attempt
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with self._session.get(url, params=params, headers=_HEADERS) as resp:
                        if resp.status == 404:
                            raise InPostAirNotFound(f"Not found: {url}")
                        if resp.status == 429 or resp.status >= 500:
                            raise _RetryableError(
                                f"HTTP {resp.status}", _retry_after(resp.headers.get("Retry-After"))
                            )
                        resp.raise_for_status()
                        return await resp.json(content_type=None)
            except _RetryableError as err:
                last_error = err
                if err.retry_after is not None:
                    delay = err.retry_after
            except (ClientConnectionError, TimeoutError) as err:
                last_error = err
            except InPostAirError:
                raise
            except (ClientError, ValueError) as err:
                raise InPostAirError(f"Request failed for {url}: {err}") from err
            if attempt + 1 < attempts:
                _LOGGER.debug("Retrying %s in %.1fs after: %s", url, delay, last_error)
                await asyncio.sleep(min(delay, MAX_RETRY_DELAY))
        raise InPostAirError(f"Request failed for {url}: {last_error or 'unknown error'}")

    async def async_get_reading(self, code: str, attempts: int = 1) -> AirReading:
        """Current measurements of one locker."""
        try:
            payload = await self._get_json(AIR_SENSORS_URL.format(code=code), attempts=attempts)
        except InPostAirNotFound as err:
            raise InPostAirNotFound(f"Locker {code} not found or has no air sensors") from err
        return parse_payload(payload)

    async def async_get_locker(self, code: str) -> Locker | None:
        """Look up one locker's location/address (server-side exact match on code)."""
        payload = await self._get_json(
            POINTS_URL, {"name": code, "fields": CATALOG_FIELDS, "per_page": 1}, attempts=2
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        return parse_point(items[0]) if isinstance(items, list) and items else None

    async def async_get_catalog(self) -> list[Locker]:
        """All lockers that advertise air sensors.

        The server ignores air_index_level as a filter, so the whole catalog (~33k points,
        a handful of large pages) is downloaded and filtered locally.
        """
        lockers: list[Locker] = []
        page, total_pages = 1, 1
        while page <= min(total_pages, CATALOG_MAX_PAGES):
            payload = await self._get_json(
                POINTS_URL,
                {"page": page, "per_page": CATALOG_PAGE_SIZE, "fields": CATALOG_FIELDS},
                attempts=3,
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise InPostAirError("Unexpected points response")
            if isinstance(payload.get("total_pages"), int):
                total_pages = payload["total_pages"]
            for item in payload["items"]:
                if (locker := parse_point(item)) is not None and locker.air_level:
                    lockers.append(locker)
            page += 1
        if not lockers:
            raise InPostAirError("Points catalog contains no lockers with air sensors")
        return lockers
