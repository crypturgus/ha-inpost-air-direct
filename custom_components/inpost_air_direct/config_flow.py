"""UI flow: pick a Paczkomat on a map, by city or by code."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_LATITUDE as HA_LAT, CONF_LONGITUDE as HA_LON, CONF_RADIUS
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import search
from .api import AirReading, InPostAirClient, InPostAirError, InPostAirNotFound, Locker
from .catalog import async_get_catalog
from .const import (
    CITY_RESULTS_LIMIT,
    CONF_ADDRESS,
    CONF_CITY,
    CONF_LATITUDE,
    CONF_LOCKER_CODE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SEARCH_RADIUS_M,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    NEARBY_PROBE_CONCURRENCY,
    NEARBY_PROBE_LIMIT,
    STALE_AFTER,
)

_LOGGER = logging.getLogger(__name__)

CODE_PATTERN = re.compile(r"^[A-Z0-9-]{3,32}$")
CONF_LOCATION = "location"
CONF_QUERY = "query"


def _age_text(reading: AirReading) -> str:
    age = reading.age(dt_util.utcnow())
    if age is None:
        return "?"
    minutes = max(0, int(age.total_seconds() // 60))
    if minutes < 120:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{minutes // 60} h"
    return f"{minutes // 1440} d"


def _place(locker: Locker) -> str:
    return ", ".join(p for p in (locker.city, locker.address) if p)


class InPostAirDirectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one Paczkomat per entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: InPostAirClient | None = None
        self._lockers: dict[str, Locker] = {}
        self._options: list[selector.SelectOptionDict] = []
        self._placeholders: dict[str, str] = {}
        self._pending: tuple[str, AirReading] | None = None

    @property
    def client(self) -> InPostAirClient:
        if self._client is None:
            self._client = InPostAirClient(async_get_clientsession(self.hass))
        return self._client

    # ------------------------------------------------------------------ entry points

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose how to find the locker."""
        return self.async_show_menu(step_id="user", menu_options=["map", "city", "code"])

    async def async_step_map(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Point and radius on a map; nearest lockers are checked for a working temperature."""
        errors: dict[str, str] = {}
        if user_input is not None:
            loc = user_input[CONF_LOCATION]
            try:
                catalog = await async_get_catalog(self.hass, self.client)
            except InPostAirError:
                errors["base"] = "catalog_unavailable"
            else:
                near = search.nearby(catalog, loc[HA_LAT], loc[HA_LON], loc.get(CONF_RADIUS) or DEFAULT_SEARCH_RADIUS_M)
                if not near:
                    errors["base"] = "no_lockers_found"
                elif await self._prepare_nearby_options(near[:NEARBY_PROBE_LIMIT]):
                    return await self.async_step_pick()
                else:
                    errors["base"] = "no_working_lockers"
        default = user_input[CONF_LOCATION] if user_input else {
            HA_LAT: self.hass.config.latitude,
            HA_LON: self.hass.config.longitude,
            CONF_RADIUS: DEFAULT_SEARCH_RADIUS_M,
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_LOCATION, default=default): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=True, icon="mdi:thermometer")
                )
            }
        )
        return self.async_show_form(
            step_id="map",
            data_schema=schema,
            errors=errors,
            description_placeholders={"limit": str(NEARBY_PROBE_LIMIT)},
        )

    async def async_step_city(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Search by city name (case and Polish diacritics insensitive)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                catalog = await async_get_catalog(self.hass, self.client)
            except InPostAirError:
                errors["base"] = "catalog_unavailable"
            else:
                hits = search.by_city(catalog, user_input[CONF_QUERY], CITY_RESULTS_LIMIT)
                if hits:
                    several_cities = len({(l.city, l.province) for l in hits}) > 1
                    self._lockers = {l.code: l for l in hits}
                    self._options = [
                        selector.SelectOptionDict(
                            value=l.code,
                            label=f"{l.code} · {_place(l)}" + (f" ({l.province})" if several_cities else ""),
                        )
                        for l in hits
                    ]
                    self._placeholders = {"count": str(len(hits)), "hidden": "0"}
                    return await self.async_step_pick()
                errors[CONF_QUERY] = "no_lockers_found"
        return self.async_show_form(
            step_id="city",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_QUERY): str}), user_input
            ),
            errors=errors,
        )

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Enter a locker code directly (works without the catalog)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input[CONF_LOCKER_CODE]).strip().upper()
            if not CODE_PATTERN.fullmatch(code):
                errors[CONF_LOCKER_CODE] = "invalid_code"
            else:
                return await self._async_validate(code, errors, step_id="code", field=CONF_LOCKER_CODE)
        return self._show_code_form(user_input, errors)

    def _show_code_form(self, user_input: dict[str, Any] | None, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="code",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_LOCKER_CODE): str}), user_input
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------ selection

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose one of the found lockers."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._async_validate(user_input[CONF_LOCKER_CODE], errors, step_id="pick")
        return self._show_pick_form(errors)

    def _show_pick_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        schema = vol.Schema(
            {
                vol.Required(CONF_LOCKER_CODE): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=self._options, mode=selector.SelectSelectorMode.LIST if len(self._options) <= 12 else selector.SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(
            step_id="pick", data_schema=schema, errors=errors, description_placeholders=self._placeholders
        )

    async def _prepare_nearby_options(self, near: list[tuple[Locker, float]]) -> bool:
        """Probe the nearest lockers live; keep only those with a fresh temperature."""
        sem = asyncio.Semaphore(NEARBY_PROBE_CONCURRENCY)
        now = dt_util.utcnow()

        async def probe(locker: Locker) -> AirReading | None:
            async with sem:
                try:
                    return await self.client.async_get_reading(locker.code)
                except InPostAirError:
                    return None

        readings = await asyncio.gather(*(probe(l) for l, _ in near))
        self._lockers, self._options = {}, []
        for (locker, dist), reading in zip(near, readings, strict=True):
            if reading is None or reading.temperature is None or reading.is_stale(now, STALE_AFTER):
                continue
            self._lockers[locker.code] = locker
            self._options.append(
                selector.SelectOptionDict(
                    value=locker.code,
                    label=f"{reading.temperature:.1f} °C · {locker.code} · {_place(locker)} · "
                    f"{dist / 1000:.1f} km · {_age_text(reading)}",
                )
            )
        self._placeholders = {
            "count": str(len(self._options)),
            "hidden": str(len(near) - len(self._options)),
        }
        return bool(self._options)

    # ------------------------------------------------------------------ validation

    async def _async_validate(
        self, code: str, errors: dict[str, str], step_id: str, field: str = "base"
    ) -> ConfigFlowResult:
        """Live check before adding: must report a temperature; stale data needs confirmation."""
        await self.async_set_unique_id(code)
        self._abort_if_unique_id_configured()
        try:
            reading = await self.client.async_get_reading(code, attempts=2)
        except InPostAirNotFound:
            errors[field] = "not_found"
        except InPostAirError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating locker %s", code)
            errors["base"] = "unknown"
        else:
            if reading.temperature is None:
                errors[field] = "no_temperature"
            elif reading.is_stale(dt_util.utcnow(), STALE_AFTER):
                self._pending = (code, reading)
                return await self.async_step_stale()
            else:
                return await self._async_create(code)
        if step_id == "pick":
            return self._show_pick_form(errors)
        return self._show_code_form({CONF_LOCKER_CODE: code}, errors)

    async def async_step_stale(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Warn that the locker's last measurement is old; allow adding anyway."""
        assert self._pending is not None
        code, reading = self._pending
        if user_input is not None:
            return await self._async_create(code)
        last = dt_util.as_local(reading.till_time).strftime("%Y-%m-%d %H:%M") if reading.till_time else "?"
        return self.async_show_form(
            step_id="stale",
            data_schema=vol.Schema({}),
            description_placeholders={"code": code, "last": last, "age": _age_text(reading)},
        )

    async def _async_create(self, code: str) -> ConfigFlowResult:
        locker = self._lockers.get(code)
        if locker is None:
            try:
                locker = await self.client.async_get_locker(code)
            except InPostAirError:
                locker = None  # location is optional
        data: dict[str, Any] = {CONF_LOCKER_CODE: code}
        title = f"InPost Air {code}"
        if locker is not None:
            data |= {
                CONF_LATITUDE: locker.latitude,
                CONF_LONGITUDE: locker.longitude,
                CONF_CITY: locker.city,
                CONF_ADDRESS: locker.address,
            }
            if place := _place(locker):
                title = f"{code} · {place}"
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return InPostAirOptionsFlow()


class InPostAirOptionsFlow(OptionsFlow):
    """Change the polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60)
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=1,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
