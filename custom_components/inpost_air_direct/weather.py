"""Weather entity: temperature, humidity and pressure of one locker (no forecast)."""
from __future__ import annotations

from homeassistant.components.weather import WeatherEntity
from homeassistant.const import UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import InPostAirConfigEntry, InPostAirCoordinator
from .entity import InPostAirEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InPostAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the weather entity when the locker reports a temperature."""
    if entry.runtime_data.data.temperature is not None:
        async_add_entities([InPostAirWeather(entry.runtime_data)])


class InPostAirWeather(InPostAirEntity, WeatherEntity):
    """The API has no sky condition or forecast; only current measurements are exposed."""

    _attr_name = None  # use the device name
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA

    def __init__(self, coordinator: InPostAirCoordinator) -> None:
        super().__init__(coordinator, "weather")

    @property
    def available(self) -> bool:
        return super().available and self.native_temperature is not None

    @property
    def native_temperature(self) -> float | None:
        return self.coordinator.data.temperature

    @property
    def humidity(self) -> float | None:
        return self.coordinator.data.values.get("HUMIDITY")

    @property
    def native_pressure(self) -> float | None:
        return self.coordinator.data.values.get("PRESSURE")
