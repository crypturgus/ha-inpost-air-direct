"""Parser and HTTP client tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.api import (
    InPostAirError,
    InPostAirNotFound,
    fetch_reading,
    parse_payload,
)

from .conftest import CODE, URL


def test_parse_real_payload(payload) -> None:
    r = parse_payload(payload)
    assert r.values["TEMPERATURE"] == pytest.approx(2.4228, abs=1e-3)
    assert set(r.values) == {"PM1", "PM25", "PM4", "PM10", "TEMPERATURE", "HUMIDITY", "PRESSURE"}
    assert r.levels == {"PM25": "GOOD", "PM10": "VERY_GOOD"}  # null levels dropped
    assert r.index_name == "PIJP" and r.index_level == "GOOD"
    assert r.standards["PM25"] == pytest.approx(55.41, abs=0.01)
    assert r.standard_names == {"PM25": "WHO", "PM10": "WHO"}
    assert r.till_time == datetime(2026, 11, 22, 17, 0, 55, 738000, tzinfo=timezone.utc)
    assert r.raw is payload


def test_parse_tolerates_junk() -> None:
    r = parse_payload({"current": {
        "values": [{"name": "PM25", "value": True}, "x", {"value": 1}, {"name": "PM10", "value": 3}],
        "index": "nope", "standards": [{"pollutant": "PM10"}], "tillDateTime": "garbage",
    }})
    assert r.values == {"PM10": 3.0}
    assert r.index_value is None and r.standards == {} and r.till_time is None


@pytest.mark.parametrize("payload", [None, {}, {"current": {}}, {"current": {"values": []}}])
def test_parse_rejects_invalid(payload) -> None:
    with pytest.raises(InPostAirError):
        parse_payload(payload)


def test_is_stale(payload) -> None:
    r = parse_payload(payload)
    end = r.till_time
    assert not r.is_stale(end + timedelta(hours=1), timedelta(hours=2))
    assert r.is_stale(end + timedelta(hours=3), timedelta(hours=2))
    assert not parse_payload({"current": {"values": [{"name": "X", "value": 1}]}}).is_stale(
        end + timedelta(days=9), timedelta(hours=2)
    )


async def test_fetch_ok(hass: HomeAssistant, api: AiohttpClientMocker) -> None:
    r = await fetch_reading(async_get_clientsession(hass), CODE)
    assert "PM25" in r.values


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 404}, InPostAirNotFound),
        ({"status": 500}, InPostAirError),
        ({"exc": TimeoutError()}, InPostAirError),
        ({"text": "<html>"}, InPostAirError),
    ],
)
async def test_fetch_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, kwargs, error) -> None:
    aioclient_mock.get(URL, **kwargs)
    with pytest.raises(error):
        await fetch_reading(async_get_clientsession(hass), CODE)
