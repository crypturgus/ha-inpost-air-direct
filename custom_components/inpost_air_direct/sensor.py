"""InPost Air Direct sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AirReading
from .const import DOMAIN
from .coordinator import InPostAirConfigEntry, InPostAirCoordinator

ATTRIBUTION = "Data from InPost (unofficial API)"


@dataclass(frozen=True, kw_only=True)
class AirSensorDescription(SensorEntityDescription):
    """Sensor description with value/attribute extractors."""

    value_fn: Callable[[AirReading], float | datetime | None]
    attrs_fn: Callable[[AirReading], dict[str, Any]] | None = None
    # Measurement entities go unavailable when the API serves stale data.
    honors_staleness: bool = True


def _measurement(
    key: str,
    api_name: str,
    unit: str,
    precision: int,
    device_class: SensorDeviceClass,
) -> AirSensorDescription:
    # Entity name comes from the (translated) device class name.
    return AirSensorDescription(
        key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
        value_fn=lambda r: r.values.get(api_name),
        attrs_fn=lambda r: {"level": r.levels.get(api_name)},
    )


def _standard(key: str, pollutant: str) -> AirSensorDescription:
    return AirSensorDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda r: r.standards.get(pollutant),
        attrs_fn=lambda r: {"standard": r.standard_names.get(pollutant)},
    )


# Unique IDs are f"{code}_{key}"; keep existing keys stable to preserve history.
SENSORS: tuple[AirSensorDescription, ...] = (
    _measurement("temperature", "TEMPERATURE", UnitOfTemperature.CELSIUS, 1, SensorDeviceClass.TEMPERATURE),
    _measurement("humidity", "HUMIDITY", PERCENTAGE, 0, SensorDeviceClass.HUMIDITY),
    _measurement("pressure", "PRESSURE", UnitOfPressure.HPA, 0, SensorDeviceClass.ATMOSPHERIC_PRESSURE),
    _measurement("pm1", "PM1", CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, 1, SensorDeviceClass.PM1),
    _measurement("pm25", "PM25", CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, 1, SensorDeviceClass.PM25),
    _measurement("pm4", "PM4", CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, 1, SensorDeviceClass.PM4),
    _measurement("pm10", "PM10", CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, 1, SensorDeviceClass.PM10),
    AirSensorDescription(
        key="air_index",
        translation_key="air_index",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda r: r.index_value,
        attrs_fn=lambda r: {"level": r.index_level, "index": r.index_name},
    ),
    _standard("pm25_who", "PM25"),
    _standard("pm10_who", "PM10"),
    AirSensorDescription(
        key="measurement_end",
        translation_key="measurement_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda r: r.till_time,
        attrs_fn=lambda r: {"period_from": r.from_time.isoformat() if r.from_time else None},
        honors_staleness=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InPostAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register entities for the sensors this locker actually reports."""
    coordinator = entry.runtime_data
    reading = coordinator.data
    async_add_entities(
        InPostAirSensor(coordinator, description)
        for description in SENSORS
        if description.value_fn(reading) is not None
    )


class InPostAirSensor(CoordinatorEntity[InPostAirCoordinator], SensorEntity):
    """One value reported by a Paczkomat."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    entity_description: AirSensorDescription

    def __init__(self, coordinator: InPostAirCoordinator, description: AirSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        code = coordinator.code
        self._attr_unique_id = f"{code}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, code)},
            name=f"InPost Air {code}",
            manufacturer="InPost",
            model="Paczkomat air sensors",
            serial_number=code,
        )

    @property
    def available(self) -> bool:
        """Unavailable on failed update, missing value or (for measurements) stale data."""
        if not super().available or self.native_value is None:
            return False
        return not (self.entity_description.honors_staleness and self.coordinator.is_stale)

    @property
    def native_value(self) -> float | datetime | None:
        """Return the current value, or None if the locker did not report it."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose qualitative level / standard name from the API."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
