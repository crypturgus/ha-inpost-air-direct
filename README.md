# InPost Air Direct — Home Assistant

Independent custom integration for readings from InPost parcel locker (Paczkomat) air sensors.

> **Unofficial / experimental.** Not affiliated with or endorsed by InPost. Uses an undocumented endpoint that may change or disappear.

## Data source

`GET https://api-pl-points.easypack24.net/v1/points/{LOCKER_CODE}/air-sensors`

Values are returned as published by the API: an aggregate over a rolling window (observed ≈75 minutes), **not instantaneous readings**.

## Entities

One device per locker. Only sensors the locker actually reports are created.

| Entity | Unit | Notes |
|---|---|---|
| Temperature, Humidity, Atmospheric pressure | °C, %, hPa | |
| PM1, PM2.5, PM4, PM10 | μg/m³ | attribute `level` (e.g. `GOOD`, `VERY_GOOD`) when the API provides it |
| Air quality index | — | attributes `level`, `index` (index name, e.g. `PIJP`) |
| PM2.5 / PM10 of WHO limit | % | percent of the WHO limit; attribute `standard` |
| Measurement window end | timestamp | diagnostic; attribute `period_from` |

**Stale data:** if the measurement window ended more than 2 hours ago (the API keeps serving the last aggregate when a locker stops reporting), measurement entities become unavailable and a warning is logged. *Measurement window end* stays available so you can see when the last data arrived.

## Requirements

Home Assistant **2025.10** or newer.

## Installation using HACS (custom repository)

1. In HACS, add `https://github.com/crypturgus/ha-inpost-air-direct` as a **custom repository**, category **Integration**.
2. Install **InPost Air Direct** and restart Home Assistant.
3. Settings → Devices & services → Add integration → **InPost Air Direct**.
4. Enter a locker code such as `DZI11M`. Repeat to add other lockers.

For local testing, copy `custom_components/inpost_air_direct` into HA's `/config/custom_components/` and restart HA.

## Options

Settings → Devices & services → InPost Air Direct → **Configure**: polling interval (1–60 min, default 5).

## Behavior

- One configuration entry per locker; duplicates are rejected.
- Setup distinguishes a non-existent locker / locker without air sensors (HTTP 404) from connection errors.
- If the API is down at startup, Home Assistant retries setup automatically; failed updates mark entities unavailable until recovery.
- Diagnostics download (device page → ⋮ → Download diagnostics) includes the last raw API response.
- No extra dependencies, scraping or Docker containers; no attempts to bypass rate limits or access restrictions.

## Coexistence

Uses domain `inpost_air_direct`, so it can coexist with the CyberDeer `inpost_air` integration. Entity IDs/history **are not migrated**. Disable or remove the old integration only after checking the new one.

## Development

```sh
python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest -q
```

Tests run against a real Home Assistant test harness (`pytest-homeassistant-custom-component`) using a captured API response. CI additionally runs `hassfest` and the HACS validation action.
