"""Config and options flow tests."""
from __future__ import annotations

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.const import (
    CONF_ADDRESS,
    CONF_CITY,
    CONF_LATITUDE,
    CONF_LOCKER_CODE,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    POINTS_URL,
)

from .conftest import CODE, DZI_LAT, DZI_LON, FRESH_NOW, URL, air_url


@pytest.fixture(autouse=True)
def _now(freezer) -> None:
    freezer.move_to(FRESH_NOW)


async def _menu(hass: HomeAssistant, choice: str):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["map", "city", "code"]
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": choice})


def _location(radius: float = 5000) -> dict:
    return {"location": {"latitude": DZI_LAT, "longitude": DZI_LON, "radius": radius}}


# ---------------------------------------------------------------- map


async def test_map_lists_only_fresh_temperature(hass: HomeAssistant, catalog_api: AiohttpClientMocker, payload, stale_payload) -> None:
    catalog_api.get(URL, json=payload)
    catalog_api.get(air_url("DZI99M"), json=stale_payload)  # stale -> hidden
    catalog_api.get(air_url("BIE01M"), status=404)  # broken -> hidden
    result = await _menu(hass, "map")
    assert result["step_id"] == "map"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _location(10_000))
    assert result["step_id"] == "pick"
    options = result["data_schema"].schema[CONF_LOCKER_CODE].config["options"]
    assert [o["value"] for o in options] == [CODE]
    assert options[0]["label"].startswith("2.4 °C · DZI11M · Dzierżoniów, Kopernika 11a · 0.0 km · 4 min")
    assert result["description_placeholders"] == {"count": "1", "hidden": "2"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "DZI11M · Dzierżoniów, Kopernika 11a"
    assert result["data"][CONF_LATITUDE] == DZI_LAT
    assert result["data"][CONF_ADDRESS] == "Kopernika 11a"
    # The catalog lookup is reused: no per-locker points request.
    assert not any("name=" in str(c[1]) for c in catalog_api.mock_calls)


async def test_map_nothing_in_radius(hass: HomeAssistant, catalog_api) -> None:
    result = await _menu(hass, "map")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": {"latitude": 54.0, "longitude": 18.0, "radius": 1000}}
    )
    assert result["errors"] == {"base": "no_lockers_found"}


async def test_map_no_working_lockers(hass: HomeAssistant, catalog_api, stale_payload) -> None:
    for code in ("DZI11M", "DZI99M", "BIE01M"):
        catalog_api.get(air_url(code), json=stale_payload)
    result = await _menu(hass, "map")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _location(10_000))
    assert result["errors"] == {"base": "no_working_lockers"}


async def test_map_catalog_unavailable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(POINTS_URL, status=503)
    result = await _menu(hass, "map")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _location())
    assert result["errors"] == {"base": "catalog_unavailable"}


# ---------------------------------------------------------------- city


async def test_city_search_without_diacritics(hass: HomeAssistant, catalog_api, payload) -> None:
    catalog_api.get(URL, json=payload)
    result = await _menu(hass, "city")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "dzierzoniow"})
    assert result["step_id"] == "pick"
    options = result["data_schema"].schema[CONF_LOCKER_CODE].config["options"]
    assert [o["value"] for o in options] == ["DZI11M", "DZI99M"]  # sorted by street; no-air locker excluded
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CITY] == "Dzierżoniów"


async def test_city_not_found(hass: HomeAssistant, catalog_api) -> None:
    result = await _menu(hass, "city")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "Gdańsk"})
    assert result["errors"] == {"query": "no_lockers_found"}


async def test_pick_stale_requires_confirmation(hass: HomeAssistant, catalog_api, stale_payload) -> None:
    catalog_api.get(air_url("DZI99M"), json=stale_payload)
    result = await _menu(hass, "city")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "Dzierżoniów"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: "DZI99M"})
    assert result["step_id"] == "stale"
    assert result["description_placeholders"]["age"] == "13 d"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LOCKER_CODE] == "DZI99M"


async def test_pick_without_temperature_rejected(hass: HomeAssistant, catalog_api) -> None:
    catalog_api.get(air_url("DZI99M"), json={"current": {"values": [{"name": "PM25", "value": 3}], "tillDateTime": "2026-11-22T17:00:00Z"}})
    result = await _menu(hass, "city")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "Dzierżoniów"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: "DZI99M"})
    assert result["step_id"] == "pick"
    assert result["errors"] == {"base": "no_temperature"}


# ---------------------------------------------------------------- code


async def test_code_normalized_and_location_looked_up(hass: HomeAssistant, catalog_api, payload) -> None:
    catalog_api.get(URL, json=payload)
    result = await _menu(hass, "code")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: " dzi11m "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == CODE
    assert result["data"][CONF_LATITUDE] == DZI_LAT


async def test_code_without_location_lookup(hass: HomeAssistant, api, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(POINTS_URL, status=500)  # location lookup fails -> still created
    result = await _menu(hass, "code")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_LOCKER_CODE: CODE}
    assert result["title"] == f"InPost Air {CODE}"


@pytest.mark.parametrize(
    ("kwargs", "errors"),
    [
        ({"status": 404}, {CONF_LOCKER_CODE: "not_found"}),
        ({"status": 503}, {"base": "cannot_connect"}),
    ],
)
async def test_code_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, kwargs, errors) -> None:
    aioclient_mock.get(URL, **kwargs)
    result = await _menu(hass, "code")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE})
    assert result["errors"] == errors


async def test_code_invalid(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    result = await _menu(hass, "code")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: "ab/../x"})
    assert result["errors"] == {CONF_LOCKER_CODE: "invalid_code"}
    assert aioclient_mock.call_count == 0


async def test_duplicate_aborts(hass: HomeAssistant, entry, api) -> None:
    result = await _menu(hass, "code")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE.lower()})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------- options


async def test_options_change_interval_reloads(hass: HomeAssistant, entry, api) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 15})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 15}
    assert entry.runtime_data.update_interval.total_seconds() == 15 * 60
