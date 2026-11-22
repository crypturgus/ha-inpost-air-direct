<img src="custom_components/inpost_air_direct/brand/icon.png" alt="" width="96" align="right">

# InPost Air Direct — Home Assistant

[Polski](README.pl.md) | English

Custom integration for **temperature** and air-quality readings from sensors mounted on InPost parcel lockers (Paczkomat) in Poland — about 4,000 lockers have them.

> **Unofficial.** Not affiliated with or endorsed by InPost. Uses undocumented endpoints that may change or disappear at any time.

## Features

- **Find a locker on a map** (Home Assistant's built-in map: drag the pin, set the radius). The nearest lockers are checked live and only those reporting a **fresh temperature** are listed, with the current temperature, distance and measurement age.
- Or search **by city** (letter case and Polish characters don't matter: `lodz` finds Łódź) or enter the **locker code**.
- A locker must report a temperature before it is added; lockers whose last data is old require confirmation.
- Sensors: temperature, humidity, pressure, PM1, PM2.5, PM4, PM10, NO2, O3 (only what the locker reports), air quality index, % of WHO limits, measurement window end.
- A **weather entity** per locker (temperature, humidity, pressure) for weather cards.
- **Stale-data detection:** when the last measurement window ended more than 2 hours ago, measurement entities become unavailable (some lockers keep serving data that is days old).
- Lockers can be shown on a Map card (the temperature sensor carries `latitude`/`longitude`).
- UI configuration, multiple lockers, adjustable polling interval (default 5 min), diagnostics download.

## Requirements

Home Assistant **2025.10** or newer.

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/crypturgus/ha-inpost-air-direct`, category **Integration**.
2. Install **InPost Air Direct** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **InPost Air Direct**.
4. Choose **On a map**, **By city** or **By locker code**, then pick a locker. Repeat for more lockers.

Manual installation: copy `custom_components/inpost_air_direct` into `/config/custom_components/` and restart.

## Entities

Entity IDs below are for locker `DZI11M`; only values the locker reports are created.

| Entity | Example ID | Notes |
|---|---|---|
| Weather | `weather.inpost_air_dzi11m` | temperature, humidity, pressure; no forecast/condition |
| Temperature | `sensor.inpost_air_dzi11m_temperature` | °C; attributes `latitude`, `longitude`, `address` |
| Humidity, Pressure | `..._humidity`, `..._atmospheric_pressure` | %, hPa |
| PM1, PM2.5, PM4, PM10, NO2, O3 | `..._pm2_5`, ... | μg/m³; attribute `level` (e.g. `GOOD`) |
| Air quality index | `..._air_quality_index` | attributes `level`, `index`, `sensor_generation` |
| % of WHO limit | `..._pm2_5_of_who_limit`, ... | |
| Measurement window end | `..._measurement_window_end` | diagnostic; stays available when data is stale |

## Example configuration

Configuration is done in the UI. Dashboard and automation examples: [`examples/dashboard.yaml`](examples/dashboard.yaml), [`examples/automations.yaml`](examples/automations.yaml).

```yaml
type: history-graph
title: Temperature
hours_to_show: 48
entities:
  - entity: sensor.inpost_air_dzi11m_temperature
```

## Good to know

- Values are **averages over a rolling window of about 60–75 minutes**, not instantaneous readings.
- Temperatures of neighbouring lockers can differ by a few °C (placement, sun, wall).
- There are two sensor hardware generations (see the device model). They report different values (gen. 1: no PM4, sometimes NO2/O3) and use **different scales for the air quality index** and different WHO limits — don't compare the index between lockers.
- InPost's catalog flag for air sensors does not guarantee they work; that is why lockers are checked live.

## How it talks to the API

| Purpose | Endpoint | When |
|---|---|---|
| Measurements | `GET api-pl-points.easypack24.net/v1/points/{code}/air-sensors` | every polling interval, one request per locker |
| Locker catalog | `GET api-shipx-pl.easypack24.net/v1/points` (paged, reduced fields) | only while adding a locker, at most once a week (cached in HA storage) |
| Locker location | same endpoint, `name={code}` | once when a locker is added by code |

The server cannot filter by air sensors and its city filter needs the exact spelling, so the catalog of lockers with air sensors is cached and searched locally. Catalog requests are retried with exponential backoff and honour `Retry-After`; measurement errors simply mark entities unavailable until the next successful poll. No scraping, browser emulation or extra containers.

## Coexistence

Domain `inpost_air_direct` can run side by side with the CyberDeer `inpost_air` integration. Entity history is not migrated.

## Development

```sh
python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest -q
```

Tests use the Home Assistant test harness with captured API responses. CI runs `hassfest`, HACS validation and the tests (also weekly). Releases: bump `version` in `manifest.json`, add a `CHANGELOG.md` section, push a `vX.Y.Z` tag — the release workflow creates the GitHub release.
