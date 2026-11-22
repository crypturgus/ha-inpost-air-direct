"""InPost Air Direct integration."""
from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import InPostAirError
from .const import CONF_ADDRESS, CONF_CITY, CONF_LATITUDE, CONF_LONGITUDE
from .coordinator import InPostAirConfigEntry, InPostAirCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.WEATHER]


async def async_setup_entry(hass: HomeAssistant, entry: InPostAirConfigEntry) -> bool:
    """Set up one locker from a UI config entry."""
    coordinator = InPostAirCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    if CONF_LATITUDE not in entry.data:
        await _async_backfill_location(hass, entry, coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: InPostAirConfigEntry) -> bool:
    """Unload platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: InPostAirConfigEntry) -> None:
    """Reload so a new polling interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_backfill_location(
    hass: HomeAssistant, entry: InPostAirConfigEntry, coordinator: InPostAirCoordinator
) -> None:
    """Entries created before 0.3.0 have no location; look it up once (best effort)."""
    try:
        locker = await coordinator.client.async_get_locker(coordinator.code)
    except InPostAirError as err:
        _LOGGER.debug("Could not look up location of %s: %s", coordinator.code, err)
        return
    if locker is None:
        return
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_LATITUDE: locker.latitude,
            CONF_LONGITUDE: locker.longitude,
            CONF_CITY: locker.city,
            CONF_ADDRESS: locker.address,
        },
    )
