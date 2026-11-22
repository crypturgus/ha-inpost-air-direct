"""Integration setup, sensor and diagnostics tests."""
from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.diagnostics import async_get_config_entry_diagnostics

from .conftest import FRESH_NOW, URL


def _state(hass: HomeAssistant, key: str):
    entity_id = er.async_get(hass).async_get_entity_id("sensor", "inpost_air_direct", f"DZI11M_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


async def _setup(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensors(hass: HomeAssistant, entry, api, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    pm25 = _state(hass, "pm25")
    assert float(pm25.state) == pytest.approx(13.853, abs=1e-3)
    assert pm25.attributes["unit_of_measurement"] == "μg/m³"  # HA's (Greek mu) constant
    assert pm25.attributes["device_class"] == "pm25"
    assert pm25.attributes["level"] == "GOOD"
    assert "period_from" not in pm25.attributes

    assert _state(hass, "pm4").attributes["device_class"] == "pm4"
    assert _state(hass, "temperature").attributes["unit_of_measurement"] == "°C"
    assert _state(hass, "pressure").attributes["unit_of_measurement"] == "hPa"
    assert {"index": "PIJP", "level": "GOOD"}.items() <= _state(hass, "air_index").attributes.items()
    assert round(float(_state(hass, "pm25_who").state)) == 55
    assert _state(hass, "measurement_end").state == "2026-11-22T17:00:55+00:00"

    # Translated names and display precision are applied.
    assert _state(hass, "air_index").name == "InPost Air DZI11M Air quality index"
    reg = er.async_get(hass).async_get(_state(hass, "temperature").entity_id)
    assert reg.options["sensor"]["suggested_display_precision"] == 1


async def test_only_reported_sensors_created(hass: HomeAssistant, entry, aioclient_mock: AiohttpClientMocker, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    aioclient_mock.get(URL, json={"current": {"values": [{"name": "PM25", "value": 10}], "tillDateTime": "2026-11-22T17:00:00Z"}})
    await _setup(hass, entry)
    keys = {e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert keys == {"DZI11M_pm25", "DZI11M_measurement_end"}


async def test_stale_data_marks_measurements_unavailable(hass: HomeAssistant, entry, api, freezer) -> None:
    freezer.move_to("2026-11-22T20:00:00+00:00")  # 3 h after window end
    await _setup(hass, entry)
    assert _state(hass, "pm25").state == STATE_UNAVAILABLE
    assert _state(hass, "measurement_end").state == "2026-11-22T17:00:55+00:00"


async def test_update_failure_and_recovery(hass: HomeAssistant, entry, aioclient_mock: AiohttpClientMocker, payload, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    aioclient_mock.get(URL, json=payload)
    await _setup(hass, entry)
    assert _state(hass, "pm25").state != STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=500)
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "pm25").state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=payload)
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "pm25").state != STATE_UNAVAILABLE


async def test_setup_retries_when_api_down(hass: HomeAssistant, entry, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(URL, status=500)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass: HomeAssistant, entry, api, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics(hass: HomeAssistant, entry, api, payload, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    await _setup(hass, entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["last_payload"] == payload
    assert diag["is_stale"] is False
    assert diag["entry"]["data"] == {"locker_code": "DZI11M"}
