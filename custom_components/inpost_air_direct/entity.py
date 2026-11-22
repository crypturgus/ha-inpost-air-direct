"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InPostAirCoordinator

ATTRIBUTION = "Data from InPost (unofficial API)"

_MODELS = {1: "Air sensor (gen. 1)", 2: "Air sensor (gen. 2)"}


class InPostAirEntity(CoordinatorEntity[InPostAirCoordinator]):
    """Groups all entities of one locker under a device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: InPostAirCoordinator, key: str) -> None:
        super().__init__(coordinator)
        code = coordinator.code
        self._attr_unique_id = f"{code}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, code)},
            name=f"InPost Air {code}",
            manufacturer="InPost",
            model=_MODELS.get(coordinator.data.sensor_origin, "Air sensor"),
            serial_number=code,
        )

    @property
    def available(self) -> bool:
        """Unavailable on failed update or when the API serves stale data."""
        return super().available and not self.coordinator.is_stale
