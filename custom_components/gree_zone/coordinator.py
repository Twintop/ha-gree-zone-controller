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
    CONF_SETPOINT_MEMORY,
    CONF_ZONES,
    DEFAULT_SETPOINT_MEMORY,
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
# Version 1 stored only StTem per zone, version 2 stores StTem and its bit.
STORAGE_VERSION = 2

# One zone's setpoint as the controller has it: {"StTem": raw, "StFahFlg": bit}
Setpoint = dict[str, int]
# {str(Mod): {zone_mac: Setpoint}}
SetpointMemory = dict[str, dict[str, Setpoint]]


def migrate_memory(data: dict[str, dict[str, Any]]) -> SetpointMemory:
    """Turn a version 1 memory (raw StTem per zone) into version 2."""
    return {
        mode: {
            mac: value if isinstance(value, dict) else {"StTem": value, "StFahFlg": 0}
            for mac, value in zones.items()
        }
        for mode, zones in data.items()
    }


class _MemoryStore(Store[SetpointMemory]):
    """The setpoint memory on disk, migrated from older versions on load."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> SetpointMemory:
        return migrate_memory(old_data)


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
        # Zone sub-unit …0N mirrors its setpoint in the gateway's StTemN, and
        # the setpoint's bit in StFahFlgN.
        self._setpoint_cols = {
            zone["mac"]: (f"StTem{int(zone['mac'][-2:])}", f"StFahFlg{int(zone['mac'][-2:])}")
            for zone in self.zones
        }
        self._held: dict[str, dict[str, tuple[Any, float]]] = {}
        self.setpoint_memory: SetpointMemory = {}
        self._store = _MemoryStore(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.setpoints")
        self._mode: int | None = None
        self._mode_since = 0.0

    async def async_load_memory(self) -> None:
        self.setpoint_memory = await self._store.async_load() or {}

    @property
    def memory_enabled(self) -> bool:
        """The setpoint_memory option. Off: nothing is learned or recalled.

        What was stored is kept, so turning it on again carries on from there.
        """
        return bool(self.entry.options.get(CONF_SETPOINT_MEMORY, DEFAULT_SETPOINT_MEMORY))

    def _remember(self, mode: int, zone_mac: str, setpoint: Setpoint) -> None:
        slot = self.setpoint_memory.setdefault(str(mode), {})
        if slot.get(zone_mac) != setpoint:
            slot[zone_mac] = dict(setpoint)
            self._store.async_delay_save(lambda: self.setpoint_memory, 5)

    def _learn(self, mode: int | None, setpoints: dict[str, Setpoint]) -> None:
        now = time.monotonic()
        if mode != self._mode:
            self._mode, self._mode_since = mode, now
            return
        if (
            not self.memory_enabled
            or mode is None
            or self._held
            or now - self._mode_since < MODE_SETTLE_SECONDS
        ):
            return
        for zone_mac, setpoint in setpoints.items():
            self._remember(mode, zone_mac, setpoint)

    async def _read_setpoints(self) -> tuple[int | None, dict[str, Setpoint]]:
        """Mode plus every zone's setpoint and bit, from a single gateway reply."""
        cols = ["Mod"]
        for setpoint_col, bit_col in self._setpoint_cols.values():
            cols += [setpoint_col, bit_col]
        res = await self.client.status(self.client.mac, cols)
        setpoints = {
            mac: {"StTem": res[setpoint_col], "StFahFlg": res.get(bit_col, 0)}
            for mac, (setpoint_col, bit_col) in self._setpoint_cols.items()
            if setpoint_col in res
        }
        return res.get("Mod"), setpoints

    async def _poll(self) -> dict[str, dict[str, Any]]:
        mode, setpoints = await self._read_setpoints()
        data = {self.ac_unit: await self.client.status(self.ac_unit, AC_COLS)}
        for zone in self.zones:
            data[zone["mac"]] = await self.client.status(zone["mac"], ZONE_COLS)
            if zone["mac"] in setpoints:
                data[zone["mac"]].update(setpoints[zone["mac"]])
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
            if (
                self.memory_enabled
                and "StTem" in values
                and target != self.ac_unit
                and mode is not None
            ):
                self._remember(mode, target, self._setpoint_of(target))
            self.async_set_updated_data(self.data)
        async_call_later(self.hass, CONFIRM_DELAY_SECONDS, self._async_confirm)

    async def async_set_mode(self, mode: int) -> None:
        """Switch mode and, with the memory on, recall that mode's zone setpoints."""
        current = (self.data or {}).get(self.ac_unit, {}).get("Mod")
        use_memory = self.memory_enabled and current is not None and mode != current
        if use_memory and not self._held:
            # Snapshot the outgoing mode from a fresh read, in case a setpoint was
            # changed on the panel or app since the last poll.
            try:
                read_mode, setpoints = await self._read_setpoints()
            except GreeZoneError as err:
                _LOGGER.debug("Could not snapshot setpoints before mode change: %s", err)
            else:
                if read_mode == current:
                    for zone_mac, setpoint in setpoints.items():
                        self._remember(current, zone_mac, setpoint)
        await self.async_command(self.ac_unit, {"Pow": 1, "Mod": mode})
        if not use_memory:
            return
        for zone in self.zones:
            stored = self.setpoint_memory.get(str(mode), {}).get(zone["mac"])
            if stored is not None and stored != self._setpoint_of(zone["mac"]):
                # Both columns: the controller keeps an old bit otherwise.
                await self.async_command(zone["mac"], dict(stored))

    @property
    def temperature_unit(self) -> int | None:
        """TemUnit of the controller: 0 °C, 1 °F. None before the first poll."""
        return (self.data or {}).get(self.ac_unit, {}).get("TemUnit")

    def _setpoint_of(self, zone_mac: str) -> Setpoint:
        """A zone's current setpoint and bit, as last read or commanded."""
        values = (self.data or {}).get(zone_mac, {})
        return {"StTem": values.get("StTem"), "StFahFlg": values.get("StFahFlg", 0)}

    async def _async_confirm(self, _now: datetime) -> None:
        await self.async_request_refresh()
