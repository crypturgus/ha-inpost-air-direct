"""Integration setup, sensor, weather and diagnostics tests."""
from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.inpost_air_direct.const import CONF_LATITUDE, CONF_LOCKER_CODE, DOMAIN
from custom_components.inpost_air_direct.diagnostics import async_get_config_entry_diagnostics

from .conftest import CODE, DZI_LAT, FRESH_NOW, URL


def _state(hass: HomeAssistant, key: str, domain: str = "sensor"):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{CODE}_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


def _device(hass: HomeAssistant, entry) -> dr.DeviceEntry:
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device


async def _setup(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensors(hass: HomeAssistant, entry, api, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    temp = _state(hass, "temperature")
    assert float(temp.state) == pytest.approx(2.423, abs=1e-3)
    assert temp.attributes["unit_of_measurement"] == "°C"
    assert temp.attributes["latitude"] == DZI_LAT  # shows up on a Map card
    assert temp.attributes["address"] == "Dzierżoniów, Kopernika 11a"

    pm25 = _state(hass, "pm25")
    assert pm25.attributes["unit_of_measurement"] == "μg/m³"  # HA's (Greek mu) constant
    assert pm25.attributes["level"] == "GOOD"
    assert "latitude" not in pm25.attributes

    assert _state(hass, "pm4").attributes["device_class"] == "pm4"
    assert _state(hass, "pressure").attributes["unit_of_measurement"] == "hPa"
    assert {"index": "PIJP", "level": "GOOD", "sensor_generation": 2}.items() <= _state(hass, "air_index").attributes.items()
    assert round(float(_state(hass, "pm25_who").state)) == 55
    assert _state(hass, "measurement_end").state == "2026-11-22T17:00:55+00:00"
    assert _state(hass, "air_index").name == "InPost Air DZI11M Air quality index"

    reg = er.async_get(hass).async_get(temp.entity_id)
    assert reg.options["sensor"]["suggested_display_precision"] == 1
    keys = {e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert f"{CODE}_no2" not in keys  # gen. 2 hardware has no NO2

    assert _device(hass, entry).model == "Air sensor (gen. 2)"


async def test_weather(hass: HomeAssistant, entry, api, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    await _setup(hass, entry)
    weather = _state(hass, "weather", "weather")
    assert weather.entity_id == "weather.inpost_air_dzi11m"
    assert weather.attributes["temperature"] == pytest.approx(2.4)
    assert weather.attributes["humidity"] == 100
    assert weather.attributes["pressure"] == pytest.approx(979.9, abs=0.1)


async def test_gen1_with_gases(hass: HomeAssistant, entry, aioclient_mock: AiohttpClientMocker, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    aioclient_mock.get(URL, json={"sensorOrigin": 1, "current": {
        "tillDateTime": "2026-11-22T17:00:00Z",
        "values": [{"name": "TEMPERATURE", "value": 3.07}, {"name": "NO2", "value": 32.56}, {"name": "O3", "value": 0.32}],
        "standards": [{"name": "WHO", "pollutant": "NO2", "limit": 25.0, "percent": 130.26}],
    }})
    await _setup(hass, entry)
    assert _state(hass, "no2").attributes["device_class"] == "nitrogen_dioxide"
    assert _state(hass, "o3").attributes["device_class"] == "ozone"
    assert round(float(_state(hass, "no2_who").state)) == 130
    keys = {e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert f"{CODE}_pm4" not in keys
    assert _device(hass, entry).model == "Air sensor (gen. 1)"


async def test_no_temperature_no_weather(hass: HomeAssistant, entry, aioclient_mock: AiohttpClientMocker, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    aioclient_mock.get(URL, json={"current": {"values": [{"name": "PM25", "value": 10}], "tillDateTime": "2026-11-22T17:00:00Z"}})
    await _setup(hass, entry)
    keys = {e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert keys == {f"{CODE}_pm25", f"{CODE}_measurement_end"}


async def test_stale_data(hass: HomeAssistant, entry, api, freezer) -> None:
    freezer.move_to("2026-11-22T20:00:00+00:00")  # 3 h after window end
    await _setup(hass, entry)
    assert _state(hass, "temperature").state == STATE_UNAVAILABLE
    assert _state(hass, "weather", "weather").state == STATE_UNAVAILABLE
    assert _state(hass, "measurement_end").state == "2026-11-22T17:00:55+00:00"


async def test_update_failure_and_recovery(hass: HomeAssistant, entry, aioclient_mock: AiohttpClientMocker, payload, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    aioclient_mock.get(URL, json=payload)
    await _setup(hass, entry)
    assert _state(hass, "temperature").state != STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=500)
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "temperature").state == STATE_UNAVAILABLE
    assert _state(hass, "measurement_end").state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=payload)
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "temperature").state != STATE_UNAVAILABLE


async def test_old_entry_location_backfilled(hass: HomeAssistant, catalog_api, payload, freezer) -> None:
    freezer.move_to(FRESH_NOW)
    catalog_api.get(URL, json=payload)
    old = MockConfigEntry(domain=DOMAIN, unique_id=CODE, data={CONF_LOCKER_CODE: CODE})  # 0.2.x entry
    old.add_to_hass(hass)
    await _setup(hass, old)
    assert old.data[CONF_LATITUDE] == DZI_LAT
    assert _state(hass, "temperature").attributes["latitude"] == DZI_LAT


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
    assert diag["entry"]["data"][CONF_LOCKER_CODE] == CODE
