"""UI flow for configuring a Paczkomat code."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InPostAirError, InPostAirNotFound, fetch_reading
from .const import (
    CONF_LOCKER_CODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

CODE_PATTERN = re.compile(r"^[A-Z0-9]{3,32}$")


class InPostAirDirectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one Paczkomat per entry."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the locker identifier and validate API data."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input[CONF_LOCKER_CODE]).strip().upper()
            if not CODE_PATTERN.fullmatch(code):
                errors[CONF_LOCKER_CODE] = "invalid_code"
            else:
                await self.async_set_unique_id(code)
                self._abort_if_unique_id_configured()
                try:
                    await fetch_reading(async_get_clientsession(self.hass), code)
                except InPostAirNotFound:
                    errors[CONF_LOCKER_CODE] = "not_found"
                except InPostAirError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error validating locker %s", code)
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=f"InPost Air {code}", data={CONF_LOCKER_CODE: code}
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_LOCKER_CODE): str}), user_input
            ),
            errors=errors,
        )

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
