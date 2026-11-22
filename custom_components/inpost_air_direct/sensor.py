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
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    PERCENTAGE,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import AirReading
from .const import CONF_ADDRESS, CONF_CITY, CONF_LATITUDE, CONF_LONGITUDE
from .coordinator import InPostAirConfigEntry, InPostAirCoordinator
from .entity import InPostAirEntity


@dataclass(frozen=True, kw_only=True)
class AirSensorDescription(SensorEntityDescription):
    """Sensor description with value/attribute extractors."""

    value_fn: Callable[[AirReading], float | datetime | None]
    attrs_fn: Callable[[AirReading], dict[str, Any]] | None = None
    # Measurement entities go unavailable when the API serves stale data.
    honors_staleness: bool = True
    # Carries the locker's coordinates so it can be shown on a Map card.
    with_location: bool = False


def _measurement(
    key: str,
    api_name: str,
    unit: str,
    precision: int,
    device_class: SensorDeviceClass,
    with_location: bool = False,
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
        with_location=with_location,
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


try:  # HA 2026.x+; the old constant is deprecated (removal planned for 2027.8)
    from homeassistant.const import UnitOfDensity

    _UG: str = UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
except ImportError:  # older HA
    from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER as _UG

# Unique IDs are f"{code}_{key}"; keep existing keys stable to preserve history.
SENSORS: tuple[AirSensorDescription, ...] = (
    _measurement("temperature", "TEMPERATURE", UnitOfTemperature.CELSIUS, 1, SensorDeviceClass.TEMPERATURE, True),
    _measurement("humidity", "HUMIDITY", PERCENTAGE, 0, SensorDeviceClass.HUMIDITY),
    _measurement("pressure", "PRESSURE", UnitOfPressure.HPA, 0, SensorDeviceClass.ATMOSPHERIC_PRESSURE),
    _measurement("pm1", "PM1", _UG, 1, SensorDeviceClass.PM1),
    _measurement("pm25", "PM25", _UG, 1, SensorDeviceClass.PM25),
    _measurement("pm4", "PM4", _UG, 1, SensorDeviceClass.PM4),
    _measurement("pm10", "PM10", _UG, 1, SensorDeviceClass.PM10),
    _measurement("no2", "NO2", _UG, 1, SensorDeviceClass.NITROGEN_DIOXIDE),
    _measurement("o3", "O3", _UG, 1, SensorDeviceClass.OZONE),
    AirSensorDescription(
        key="air_index",
        translation_key="air_index",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: r.index_value,
        attrs_fn=lambda r: {"level": r.index_level, "index": r.index_name, "sensor_generation": r.sensor_origin},
    ),
    _standard("pm25_who", "PM25"),
    _standard("pm10_who", "PM10"),
    _standard("no2_who", "NO2"),
    _standard("o3_who", "O3"),
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
    """Register entities for the values this locker actually reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        InPostAirSensor(coordinator, description)
        for description in SENSORS
        if description.value_fn(coordinator.data) is not None
    )


class InPostAirSensor(InPostAirEntity, SensorEntity):
    """One value reported by a Paczkomat."""

    entity_description: AirSensorDescription

    def __init__(self, coordinator: InPostAirCoordinator, description: AirSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Unavailable on failed update, missing value or (for measurements) stale data."""
        if self.entity_description.honors_staleness:
            if not super().available:
                return False
        elif not self.coordinator.last_update_success:
            return False
        return self.native_value is not None

    @property
    def native_value(self) -> float | datetime | None:
        """Return the current value, or None if the locker did not report it."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Qualitative level / standard name from the API, plus location for the map."""
        desc = self.entity_description
        attrs = desc.attrs_fn(self.coordinator.data) if desc.attrs_fn else {}
        if desc.with_location:
            data = self.coordinator.config_entry.data
            if data.get(CONF_LATITUDE) is not None and data.get(CONF_LONGITUDE) is not None:
                attrs[ATTR_LATITUDE] = data[CONF_LATITUDE]
                attrs[ATTR_LONGITUDE] = data[CONF_LONGITUDE]
            if address := ", ".join(p for p in (data.get(CONF_CITY), data.get(CONF_ADDRESS)) if p):
                attrs["address"] = address
        return attrs or None
