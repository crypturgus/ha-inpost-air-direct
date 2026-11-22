"""Cached catalog of lockers with air sensors (Home Assistant storage, refreshed weekly).

Only used while adding a locker; sensor updates never touch it.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import InPostAirClient, InPostAirError, Locker
from .const import CATALOG_TTL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.catalog"
STORAGE_VERSION = 1
_LOCK = "catalog_lock"
_CACHE = "catalog"


def _decode(raw: Any) -> tuple[datetime, list[Locker]] | None:
    if not isinstance(raw, dict):
        return None
    fetched = dt_util.parse_datetime(str(raw.get("fetched_at", "")))
    items = raw.get("lockers")
    if fetched is None or not isinstance(items, list):
        return None
    try:
        return fetched, [Locker.from_dict(i) for i in items]
    except (TypeError, KeyError):
        return None


async def async_get_catalog(hass: HomeAssistant, client: InPostAirClient) -> list[Locker]:
    """Return the cached catalog, refreshing it when older than CATALOG_TTL.

    If a refresh fails but an older copy exists, the older copy is used.
    """
    data = hass.data.setdefault(DOMAIN, {})
    lock: asyncio.Lock = data.setdefault(_LOCK, asyncio.Lock())
    async with lock:
        store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        cached = data.get(_CACHE) or _decode(await store.async_load())
        now = dt_util.utcnow()
        if cached and now - cached[0] < CATALOG_TTL:
            data[_CACHE] = cached
            return cached[1]
        try:
            lockers = await client.async_get_catalog()
        except InPostAirError as err:
            if cached:
                _LOGGER.warning("Catalog refresh failed (%s); using copy from %s", err, cached[0])
                data[_CACHE] = cached
                return cached[1]
            raise
        _LOGGER.debug("Catalog refreshed: %d lockers with air sensors", len(lockers))
        await store.async_save(
            {"fetched_at": now.isoformat(), "lockers": [l.as_dict() for l in lockers]}
        )
        data[_CACHE] = (now, lockers)
        return lockers
