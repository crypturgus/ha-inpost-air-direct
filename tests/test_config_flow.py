"""Config and options flow tests."""
from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.const import CONF_LOCKER_CODE, CONF_SCAN_INTERVAL, DOMAIN

from .conftest import CODE, URL


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_create_entry_normalizes_code(hass: HomeAssistant, api) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: " dzi11m "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_LOCKER_CODE: CODE}
    assert result["result"].unique_id == CODE


async def test_invalid_code(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: "ab/../x"})
    assert result["errors"] == {CONF_LOCKER_CODE: "invalid_code"}
    assert aioclient_mock.call_count == 0


async def test_not_found_then_recover(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, payload) -> None:
    aioclient_mock.get(URL, status=404)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE})
    assert result["errors"] == {CONF_LOCKER_CODE: "not_found"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_cannot_connect(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(URL, status=503)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_aborts(hass: HomeAssistant, entry, api) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LOCKER_CODE: CODE.lower()})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_change_interval_reloads(hass: HomeAssistant, entry, api, freezer) -> None:
    freezer.move_to("2026-11-22T17:05:00+00:00")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 15})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 15}
    assert entry.runtime_data.update_interval.total_seconds() == 15 * 60
