"""Polling coordinator for the Gree Zone Controller."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GreeZoneClient, GreeZoneError
from .const import (
    AC_COLS,
    CONF_AC_UNIT,
    CONF_KEY,
    CONF_ZONES,
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
    ZONE_COLS,
)

_LOGGER = logging.getLogger(__name__)

# The controller takes a few seconds to apply a command and keeps reporting the
# old value meanwhile, so commanded values are held until confirmed (or expired).
HOLD_SECONDS = 20
CONFIRM_DELAY_SECONDS = 4

# The wall panel remembers zone setpoints per mode and recalls them when the mode
# is changed on the panel; mode changes over WiFi skip that, so we keep our own
# copy, learning changes made anywhere (HA, panel, app). Mode and setpoints are
# read in one gateway reply so they always belong together, and a reading is only
# learned once the mode was also seen on the previous poll, so a poll caught in
# the middle of a panel mode switch is never stored under the wrong mode.
MODE_SETTLE_SECONDS = 8
STORAGE_VERSION = 1


class GreeZoneCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls the AC unit and every zone; data is {sub_mac: {col: value}}."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: GreeZoneClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.entry = entry
        self.client = client
        self.ac_unit: str = entry.data[CONF_AC_UNIT]
        self.zones: list[dict[str, Any]] = entry.data[CONF_ZONES]
        # Zone sub-unit …0N mirrors its setpoint in the gateway's StTemN.
        self._setpoint_cols = {zone["mac"]: f"StTem{int(zone['mac'][-2:])}" for zone in self.zones}
        self._held: dict[str, dict[str, tuple[Any, float]]] = {}
        # {str(Mod): {zone_mac: raw StTem}}
        self.setpoint_memory: dict[str, dict[str, int]] = {}
        self._store: Store[dict[str, dict[str, int]]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.setpoints"
        )
        self._mode: int | None = None
        self._mode_since = 0.0

    async def async_load_memory(self) -> None:
        self.setpoint_memory = await self._store.async_load() or {}

    def _remember(self, mode: int, zone_mac: str, raw: int) -> None:
        slot = self.setpoint_memory.setdefault(str(mode), {})
        if slot.get(zone_mac) != raw:
            slot[zone_mac] = raw
            self._store.async_delay_save(lambda: self.setpoint_memory, 5)

    def _learn(self, mode: int | None, setpoints: dict[str, int]) -> None:
        now = time.monotonic()
        if mode != self._mode:
            self._mode, self._mode_since = mode, now
            return
        if mode is None or self._held or now - self._mode_since < MODE_SETTLE_SECONDS:
            return
        for zone_mac, raw in setpoints.items():
            self._remember(mode, zone_mac, raw)

    async def _read_setpoints(self) -> tuple[int | None, dict[str, int]]:
        """Mode plus every zone's setpoint, from a single gateway reply."""
        res = await self.client.status(
            self.client.mac, ["Mod", *self._setpoint_cols.values()]
        )
        setpoints = {
            mac: res[col] for mac, col in self._setpoint_cols.items() if col in res
        }
        return res.get("Mod"), setpoints

    async def _poll(self) -> dict[str, dict[str, Any]]:
        mode, setpoints = await self._read_setpoints()
        data = {self.ac_unit: await self.client.status(self.ac_unit, AC_COLS)}
        for zone in self.zones:
            data[zone["mac"]] = await self.client.status(zone["mac"], ZONE_COLS)
            if zone["mac"] in setpoints:
                data[zone["mac"]]["StTem"] = setpoints[zone["mac"]]
        self._learn(mode, setpoints)
        return data

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            data = await self._poll()
        except GreeZoneError:
            # A wrong key looks like silence. The key changes if the module is
            # re-paired in the Gree+ app, so re-bind once and retry.
            try:
                key = await self.client.bind()
                data = await self._poll()
            except GreeZoneError as err:
                raise UpdateFailed(str(err)) from err
            if key != self.entry.data[CONF_KEY]:
                _LOGGER.info("Gree zone controller key changed; stored the new one")
                self.hass.config_entries.async_update_entry(
                    self.entry, data={**self.entry.data, CONF_KEY: key}
                )
        self._apply_held(data)
        return data

    def _apply_held(self, data: dict[str, dict[str, Any]]) -> None:
        now = time.monotonic()
        for target, cols in list(self._held.items()):
            for col, (value, expires) in list(cols.items()):
                if data.get(target, {}).get(col) == value or now > expires:
                    del cols[col]
                else:
                    data.setdefault(target, {})[col] = value
            if not cols:
                del self._held[target]

    async def async_command(self, target: str, values: dict[str, Any]) -> None:
        """Send a command, hold the new values until the controller confirms them."""
        try:
            await self.client.command(target, values)
        except GreeZoneError as err:
            raise HomeAssistantError(str(err)) from err
        expires = time.monotonic() + HOLD_SECONDS
        self._held.setdefault(target, {}).update({k: (v, expires) for k, v in values.items()})
        if self.data is not None:
            self.data.setdefault(target, {}).update(values)
            mode = self.data.get(self.ac_unit, {}).get("Mod")
            if "StTem" in values and target != self.ac_unit and mode is not None:
                self._remember(mode, target, values["StTem"])
            self.async_set_updated_data(self.data)
        async_call_later(self.hass, CONFIRM_DELAY_SECONDS, self._async_confirm)

    async def async_set_mode(self, mode: int) -> None:
        """Switch mode and recall that mode's zone setpoints, as the wall panel does."""
        current = (self.data or {}).get(self.ac_unit, {}).get("Mod")
        switching = current is not None and mode != current
        if switching and not self._held:
            # Snapshot the outgoing mode from a fresh read, in case a setpoint was
            # changed on the panel or app since the last poll.
            try:
                read_mode, setpoints = await self._read_setpoints()
            except GreeZoneError as err:
                _LOGGER.debug("Could not snapshot setpoints before mode change: %s", err)
            else:
                if read_mode == current:
                    for zone_mac, raw in setpoints.items():
                        self._remember(current, zone_mac, raw)
        await self.async_command(self.ac_unit, {"Pow": 1, "Mod": mode})
        if not switching:
            return
        for zone in self.zones:
            raw = self.setpoint_memory.get(str(mode), {}).get(zone["mac"])
            if raw is not None and raw != self.data.get(zone["mac"], {}).get("StTem"):
                await self.async_command(zone["mac"], {"StTem": raw})

    async def _async_confirm(self, _now: datetime) -> None:
        await self.async_request_refresh()
