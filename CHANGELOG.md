# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.4.0] - 2026-11-22

### Added
- Integration logo (`brand/icon.png`), shown by Home Assistant versions that load brand images from custom integrations.

### Removed
- The `weather` entity. The InPost API has no sky condition, and in Home Assistant the condition is the
  weather entity's state, so it always showed "Unknown". Use the temperature sensor (e.g. a Tile card) instead.
  The entity is removed from the entity registry automatically on upgrade.

## [0.3.0] - 2026-11-22

### Added
- Locker discovery in the setup dialog: **on a map** (native Home Assistant map with pin and radius),
  **by city** (case- and Polish-diacritics-insensitive) or **by code**.
- Map search checks the nearest lockers live and lists only those reporting a fresh temperature,
  showing the current temperature, distance and measurement age.
- Before a locker is added it must report a temperature; lockers with stale data require confirmation.
- `weather` entity per locker (temperature, humidity, pressure; no forecast or condition).
- NO2 and O3 sensors and their WHO-limit percentages (older "gen. 1" hardware).
- Locker location and address stored with the entry; the temperature sensor exposes
  `latitude`/`longitude` so lockers can be shown on a Map card. Existing entries are backfilled once.
- Weekly cached catalog of lockers with air sensors (Home Assistant storage), downloaded only while adding a locker.
- Retries with exponential backoff and `Retry-After` support for catalog requests.
- Device model shows the sensor hardware generation.
- Polish README, changelog, examples, release workflow.

### Changed
- µg/m³ unit uses `UnitOfDensity` on Home Assistant versions that have it (old constant is deprecated).

## [0.2.0] - 2026-11-22

### Added
- Stale-data detection, measurement-window sensor, WHO-limit sensors, options flow (polling interval),
  diagnostics, Polish entity names, Home Assistant test harness and CI (hassfest, HACS, pytest).

### Fixed
- Coordinator receives its config entry explicitly; Home Assistant unit constants and device classes;
  display precision; only reported sensors are created.

## [0.1.0]

- Initial version.

[0.4.0]: https://github.com/crypturgus/ha-inpost-air-direct/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/crypturgus/ha-inpost-air-direct/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/crypturgus/ha-inpost-air-direct/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/crypturgus/ha-inpost-air-direct/releases/tag/v0.1.0
