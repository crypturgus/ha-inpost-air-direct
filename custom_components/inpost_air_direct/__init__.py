"""InPost Air Direct integration."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import InPostAirConfigEntry, InPostAirCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: InPostAirConfigEntry) -> bool:
    """Set up one locker from a UI config entry."""
    coordinator = InPostAirCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: InPostAirConfigEntry) -> bool:
    """Unload sensors."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: InPostAirConfigEntry) -> None:
    """Reload so a new polling interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)
