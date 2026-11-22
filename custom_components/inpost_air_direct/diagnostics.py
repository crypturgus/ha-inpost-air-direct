"""Diagnostics download for InPost Air Direct."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import InPostAirConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: InPostAirConfigEntry
) -> dict[str, Any]:
    """Return config and the last raw API payload (locker codes are public, nothing to redact)."""
    coordinator = entry.runtime_data
    return {
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "last_update_success": coordinator.last_update_success,
        "update_interval": str(coordinator.update_interval),
        "is_stale": coordinator.is_stale,
        "last_payload": coordinator.data.raw if coordinator.data else None,
    }
