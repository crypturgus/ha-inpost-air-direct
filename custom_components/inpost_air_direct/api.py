"""Minimal HTTP client for the unofficial InPost air-sensors endpoint.

Deliberately free of Home Assistant imports so it can be unit-tested standalone.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import API_URL, REQUEST_TIMEOUT


class InPostAirError(Exception):
    """Raised when sensor data cannot be retrieved or parsed."""


class InPostAirNotFound(InPostAirError):
    """Raised when the locker does not exist or exposes no air sensors (HTTP 404)."""


@dataclass(frozen=True)
class AirReading:
    """Normalized API response."""

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
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def is_stale(self, now: datetime, max_age: timedelta) -> bool:
        """Return True when the measurement window ended more than max_age ago."""
        if self.till_time is None:
            return False
        return now - self.till_time > max_age


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


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
        raw=payload,
    )


async def fetch_reading(session: ClientSession, code: str) -> AirReading:
    """Request one locker's current reading."""
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(
                API_URL.format(code=code), headers={"Accept": "application/json"}
            ) as response:
                if response.status == 404:
                    raise InPostAirNotFound(f"Locker {code} not found or has no air sensors")
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except InPostAirError:
        raise
    except (ClientError, TimeoutError, ValueError) as err:
        raise InPostAirError(f"Request failed for {code}: {err}") from err
    return parse_payload(payload)
