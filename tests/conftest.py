"""Shared fixtures."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.const import (
    AIR_SENSORS_URL,
    CONF_ADDRESS,
    CONF_CITY,
    CONF_LATITUDE,
    CONF_LOCKER_CODE,
    CONF_LONGITUDE,
    DOMAIN,
    POINTS_URL,
)

FIXTURES = Path(__file__).parent / "fixtures"
CODE = "DZI11M"
URL = AIR_SENSORS_URL.format(code=CODE)
# Shortly after the fixture's tillDateTime (2026-11-22T17:00:55Z), i.e. fresh data.
FRESH_NOW = "2026-11-22T17:05:00+00:00"
DZI_LAT, DZI_LON = 50.72455, 16.64585


def air_url(code: str) -> str:
    return AIR_SENSORS_URL.format(code=code)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom_components in every test."""


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Retries must not slow tests down; recorded delays can be asserted."""
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("custom_components.inpost_air_direct.api.asyncio.sleep", fake_sleep)
    return delays


@pytest.fixture
def payload() -> dict[str, Any]:
    """A real air-sensors response captured from the endpoint (gen. 2 hardware)."""
    return json.loads((FIXTURES / "air_sensors.json").read_text())


@pytest.fixture
def stale_payload(payload: dict[str, Any]) -> dict[str, Any]:
    stale = copy.deepcopy(payload)
    stale["current"]["fromDateTime"] = "2026-11-09T11:21:10.350Z"
    stale["current"]["tillDateTime"] = "2026-11-09T12:21:10.350Z"
    return stale


@pytest.fixture
def points_page() -> dict[str, Any]:
    return json.loads((FIXTURES / "points_page.json").read_text())


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=CODE,
        title=f"InPost Air {CODE}",
        data={
            CONF_LOCKER_CODE: CODE,
            CONF_LATITUDE: DZI_LAT,
            CONF_LONGITUDE: DZI_LON,
            CONF_CITY: "Dzierżoniów",
            CONF_ADDRESS: "Kopernika 11a",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def api(aioclient_mock: AiohttpClientMocker, payload: dict[str, Any]) -> AiohttpClientMocker:
    aioclient_mock.get(URL, json=payload)
    return aioclient_mock


@pytest.fixture
def catalog_api(aioclient_mock: AiohttpClientMocker, points_page: dict[str, Any]) -> AiohttpClientMocker:
    """Points catalog (single page) and single-locker lookup."""
    dzi = next(i for i in points_page["items"] if i["name"] == CODE)
    aioclient_mock.get(f"{POINTS_URL}?name={CODE}", json={"items": [dzi], "total_pages": 1})
    aioclient_mock.get(f"{POINTS_URL}?page=1", json=points_page)
    return aioclient_mock
