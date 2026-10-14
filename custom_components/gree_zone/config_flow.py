"""Config flow: discover the controller, bind, then name the zones. Options flow:
whether the zone setpoints are remembered per mode."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .api import GreeZoneClient, GreeZoneError
from .const import (
    AC_UNIT_SUFFIX,
    CONF_AC_UNIT,
    CONF_KEY,
    CONF_MAC,
    CONF_SETPOINT_MEMORY,
    CONF_ZONES,
    DEFAULT_SETPOINT_MEMORY,
    DOMAIN,
)

CONF_ALWAYS_ON = "always_on"


class GreeZoneConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._zone_macs: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GreeZoneOptionsFlow:
        return GreeZoneOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            try:
                client = GreeZoneClient(host)
                info = await client.scan()
                client.mac = info["mac"]
                key = await client.bind()
                subs = await client.sub_units()
            except (GreeZoneError, KeyError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(client.mac)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                # The AC unit is sub-unit 00, the zones are 01 to 08.
                macs = [s["mac"] for s in subs if "mac" in s]
                ac = [mac for mac in macs if mac.endswith(AC_UNIT_SUFFIX)]
                self._zone_macs = sorted(mac for mac in macs if not mac.endswith(AC_UNIT_SUFFIX))
                if not ac or not self._zone_macs:
                    errors["base"] = "no_zones"
                else:
                    self._data = {
                        CONF_HOST: host,
                        CONF_MAC: client.mac,
                        CONF_KEY: key,
                        CONF_AC_UNIT: ac[0],
                    }
                    return await self.async_step_zones()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        labels = {f"zone_{n}": f"Zone {n}" for n in range(1, len(self._zone_macs) + 1)}
        if user_input is not None:
            always_on = user_input.get(CONF_ALWAYS_ON, [])
            self._data[CONF_ZONES] = [
                {"mac": mac, "name": user_input[field], "always_on": field in always_on}
                for field, mac in zip(labels, self._zone_macs)
            ]
            return self.async_create_entry(title="Gree Zone Controller", data=self._data)
        schema: dict[Any, Any] = {
            vol.Required(field, default=label): str for field, label in labels.items()
        }
        schema[vol.Optional(CONF_ALWAYS_ON, default=["zone_1"])] = cv.multi_select(labels)
        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))


class GreeZoneOptionsFlow(OptionsFlow):
    """One option: remember the zone setpoints per mode, on by default."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SETPOINT_MEMORY, DEFAULT_SETPOINT_MEMORY)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_SETPOINT_MEMORY, default=current): bool}),
        )
