"""Shared fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.const import API_URL, CONF_LOCKER_CODE, DOMAIN

CODE = "DZI11M"
URL = API_URL.format(code=CODE)
# Shortly after the fixture's tillDateTime (2026-11-22T17:00:55Z), i.e. fresh data.
FRESH_NOW = "2026-11-22T17:05:00+00:00"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom_components in every test."""


@pytest.fixture
def payload() -> dict[str, Any]:
    """A real API response captured from the endpoint."""
    return json.loads((Path(__file__).parent / "fixtures" / "air_sensors.json").read_text())


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=CODE, title=f"InPost Air {CODE}", data={CONF_LOCKER_CODE: CODE}
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def api(aioclient_mock: AiohttpClientMocker, payload: dict[str, Any]) -> AiohttpClientMocker:
    aioclient_mock.get(URL, json=payload)
    return aioclient_mock
