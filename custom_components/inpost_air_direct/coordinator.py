"""Data update coordinator for one InPost locker."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AirReading, InPostAirClient, InPostAirError
from .const import CONF_LOCKER_CODE, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, STALE_AFTER

_LOGGER = logging.getLogger(__name__)

type InPostAirConfigEntry = ConfigEntry[InPostAirCoordinator]


class InPostAirCoordinator(DataUpdateCoordinator[AirReading]):
    """Polls the air-sensors endpoint for a single locker."""

    config_entry: InPostAirConfigEntry

    def __init__(self, hass: HomeAssistant, entry: InPostAirConfigEntry) -> None:
        self.code: str = entry.data[CONF_LOCKER_CODE]
        minutes = entry.options.get(CONF_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.code}",
            update_interval=timedelta(minutes=minutes) if minutes else DEFAULT_SCAN_INTERVAL,
        )
        self.client = InPostAirClient(async_get_clientsession(hass))
        self._stale_logged = False

    async def _async_update_data(self) -> AirReading:
        try:
            reading = await self.client.async_get_reading(self.code)
        except InPostAirError as err:
            raise UpdateFailed(str(err)) from err
        stale = reading.is_stale(dt_util.utcnow(), STALE_AFTER)
        if stale and not self._stale_logged:
            _LOGGER.warning(
                "Locker %s returns stale data (measurement window ended %s); "
                "measurement entities will be unavailable until it reports again",
                self.code,
                reading.till_time,
            )
        elif not stale and self._stale_logged:
            _LOGGER.info("Locker %s reports fresh data again", self.code)
        self._stale_logged = stale
        return reading

    @property
    def is_stale(self) -> bool:
        """Whether the last reading is too old to be trusted as current."""
        return self.data is not None and self.data.is_stale(dt_util.utcnow(), STALE_AFTER)
