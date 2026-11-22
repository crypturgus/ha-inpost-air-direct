"""Catalog cache tests."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.api import InPostAirClient, InPostAirError
from custom_components.inpost_air_direct.catalog import STORAGE_KEY, async_get_catalog
from custom_components.inpost_air_direct.const import DOMAIN

from .conftest import FRESH_NOW


async def test_fetch_store_and_reuse(hass: HomeAssistant, catalog_api: AiohttpClientMocker, hass_storage: dict[str, Any], freezer) -> None:
    freezer.move_to(FRESH_NOW)
    client = InPostAirClient(async_get_clientsession(hass))
    first = await async_get_catalog(hass, client)
    assert len(first) == 4
    assert len(hass_storage[STORAGE_KEY]["data"]["lockers"]) == 4
    calls = catalog_api.call_count

    assert await async_get_catalog(hass, client) == first
    hass.data[DOMAIN].pop("catalog")  # simulate restart: load from storage, no HTTP
    assert await async_get_catalog(hass, client) == first
    assert catalog_api.call_count == calls


async def test_refresh_after_ttl_and_fallback(hass: HomeAssistant, catalog_api: AiohttpClientMocker, freezer, caplog) -> None:
    freezer.move_to(FRESH_NOW)
    client = InPostAirClient(async_get_clientsession(hass))
    first = await async_get_catalog(hass, client)

    freezer.tick(timedelta(days=8))
    catalog_api.clear_requests()
    catalog_api.get("https://api-shipx-pl.easypack24.net/v1/points", status=500)
    assert await async_get_catalog(hass, client) == first  # stale copy used
    assert "Catalog refresh failed" in caplog.text


async def test_no_cache_and_api_down(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get("https://api-shipx-pl.easypack24.net/v1/points", status=500)
    with pytest.raises(InPostAirError):
        await async_get_catalog(hass, InPostAirClient(async_get_clientsession(hass)))
