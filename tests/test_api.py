"""Parser and HTTP client tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL as YURL

from custom_components.inpost_air_direct.api import (
    InPostAirClient,
    InPostAirError,
    InPostAirNotFound,
    parse_payload,
    parse_point,
)
from custom_components.inpost_air_direct.const import POINTS_URL

from .conftest import CODE, URL


def test_parse_real_payload(payload) -> None:
    r = parse_payload(payload)
    assert r.temperature == pytest.approx(2.4228, abs=1e-3)
    assert set(r.values) == {"PM1", "PM25", "PM4", "PM10", "TEMPERATURE", "HUMIDITY", "PRESSURE"}
    assert r.levels == {"PM25": "GOOD", "PM10": "VERY_GOOD"}  # null levels dropped
    assert r.index_name == "PIJP" and r.index_level == "GOOD"
    assert r.standards["PM25"] == pytest.approx(55.41, abs=0.01)
    assert r.standard_names == {"PM25": "WHO", "PM10": "WHO"}
    assert r.till_time == datetime(2026, 11, 22, 17, 0, 55, 738000, tzinfo=timezone.utc)
    assert r.sensor_origin == 2
    assert r.raw is payload


def test_parse_gen1_with_gases() -> None:
    r = parse_payload({"sensorOrigin": 1, "current": {
        "values": [{"name": "NO2", "value": 32.5, "level": "VERY_GOOD"}, {"name": "TEMPERATURE", "value": 3}],
        "standards": [{"name": "WHO", "pollutant": "NO2", "limit": 25.0, "percent": 130.2}],
    }})
    assert r.sensor_origin == 1 and r.values["NO2"] == 32.5 and r.standards == {"NO2": 130.2}


def test_parse_tolerates_junk() -> None:
    r = parse_payload({"sensorOrigin": True, "current": {
        "values": [{"name": "PM25", "value": True}, "x", {"value": 1}, {"name": "PM10", "value": 3}],
        "index": "nope", "standards": [{"pollutant": "PM10"}], "tillDateTime": "garbage",
    }})
    assert r.values == {"PM10": 3.0} and r.temperature is None
    assert r.index_value is None and r.standards == {} and r.till_time is None and r.sensor_origin is None


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


def test_parse_point(points_page) -> None:
    lockers = [parse_point(i) for i in points_page["items"]]
    assert lockers[-1] is None  # no coordinates
    dzi = lockers[0]
    assert (dzi.code, dzi.city, dzi.address, dzi.air_level) == ("DZI11M", "Dzierżoniów", "Kopernika 11a", "GOOD")
    assert dzi.from_dict(dzi.as_dict()) == dzi
    assert lockers[1].air_level is None


async def test_reading_ok(hass: HomeAssistant, api: AiohttpClientMocker) -> None:
    r = await InPostAirClient(async_get_clientsession(hass)).async_get_reading(CODE)
    assert "PM25" in r.values


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 404}, InPostAirNotFound),
        ({"status": 500}, InPostAirError),
        ({"status": 403}, InPostAirError),
        ({"exc": TimeoutError()}, InPostAirError),
        ({"text": "<html>"}, InPostAirError),
    ],
)
async def test_reading_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, kwargs, error) -> None:
    aioclient_mock.get(URL, **kwargs)
    with pytest.raises(error):
        await InPostAirClient(async_get_clientsession(hass)).async_get_reading(CODE)
    assert aioclient_mock.call_count == 1  # no retries by default


async def test_retry_honors_retry_after(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, payload, no_retry_sleep) -> None:
    responses = iter([
        AiohttpClientMockResponse("get", YURL(URL), status=429, headers={"Retry-After": "7"}),
        AiohttpClientMockResponse("get", YURL(URL), status=503),
        AiohttpClientMockResponse("get", YURL(URL), json=payload),
    ])

    async def side_effect(method, url, data):
        return next(responses)

    aioclient_mock.get(URL, side_effect=side_effect)
    r = await InPostAirClient(async_get_clientsession(hass)).async_get_reading(CODE, attempts=3)
    assert r.temperature is not None
    assert no_retry_sleep == [7.0, 2.0]  # Retry-After, then exponential backoff


async def test_retry_gives_up(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_retry_sleep) -> None:
    aioclient_mock.get(URL, status=502)
    with pytest.raises(InPostAirError, match="502"):
        await InPostAirClient(async_get_clientsession(hass)).async_get_reading(CODE, attempts=3)
    assert aioclient_mock.call_count == 3 and no_retry_sleep == [1.0, 2.0]


async def test_catalog_paginates_and_filters(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, points_page) -> None:
    page2 = {"total_pages": 2, "items": [{"name": "ZZZ01M", "location": {"latitude": 1, "longitude": 2}, "air_index_level": "BAD"}]}
    aioclient_mock.get(f"{POINTS_URL}?page=1", json=points_page | {"total_pages": 2})
    aioclient_mock.get(f"{POINTS_URL}?page=2", json=page2)
    lockers = await InPostAirClient(async_get_clientsession(hass)).async_get_catalog()
    assert [l.code for l in lockers] == ["DZI11M", "DZI99M", "BIE01M", "WAW01M", "ZZZ01M"]
    sent = str(aioclient_mock.mock_calls[0][1])
    assert "per_page=5000" in sent and "fields=" in sent


async def test_catalog_empty_is_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{POINTS_URL}?page=1", json={"total_pages": 1, "items": []})
    with pytest.raises(InPostAirError):
        await InPostAirClient(async_get_clientsession(hass)).async_get_catalog()


async def test_get_locker(hass: HomeAssistant, catalog_api) -> None:
    locker = await InPostAirClient(async_get_clientsession(hass)).async_get_locker(CODE)
    assert locker.city == "Dzierżoniów"
