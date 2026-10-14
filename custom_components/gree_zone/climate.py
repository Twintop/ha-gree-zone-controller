"""The ducted AC unit behind the zone controller."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GreeZoneCoordinator
from .entity import GreeZoneEntity
from .temperature import to_unit

# Mod values as used by this controller (NOT the usual Gree numbering);
# mapped by cycling the wall panel through its modes.
MOD_TO_HVAC: dict[int, HVACMode] = {
    1: HVACMode.COOL,
    2: HVACMode.HEAT,
    3: HVACMode.DRY,
    4: HVACMode.FAN_ONLY,
    5: HVACMode.AUTO,
}
HVAC_TO_MOD = {v: k for k, v in MOD_TO_HVAC.items()}

FAN_MODES: dict[int, str] = {
    0: "auto",
    1: "low",
    2: "medium_low",
    3: "medium",
    4: "medium_high",
    5: "high",
    6: "turbo",
}
FAN_TO_SPD = {v: k for k, v in FAN_MODES.items()}
# The panel only offers Turbo in Cool and Heat.
TURBO_MODES = {HVACMode.COOL, HVACMode.HEAT}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: GreeZoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GreeZoneClimate(coordinator)])


class GreeZoneClimate(GreeZoneEntity, ClimateEntity):
    """Power, mode and fan speed of the ducted unit."""

    _attr_name = None  # use the device name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, *MOD_TO_HVAC.values()]
    _attr_supported_features = (
        ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: GreeZoneCoordinator) -> None:
        super().__init__(coordinator, coordinator.ac_unit)
        self._attr_unique_id = f"{coordinator.ac_unit}_climate"

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self.values.get("Pow") == 0:
            return HVACMode.OFF
        return MOD_TO_HVAC.get(self.values.get("Mod"))

    @property
    def fan_modes(self) -> list[str]:
        if self.hvac_mode in TURBO_MODES or self.fan_mode == "turbo":
            return list(FAN_MODES.values())
        return [mode for mode in FAN_MODES.values() if mode != "turbo"]

    @property
    def fan_mode(self) -> str | None:
        return FAN_MODES.get(self.values.get("WdSpd"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        names = {zone["mac"]: zone["name"] for zone in self.coordinator.zones}
        unit = self.coordinator.temperature_unit
        memory = {
            MOD_TO_HVAC[int(mode)].value: {
                names.get(mac, mac): to_unit(setpoint["StTem"], setpoint.get("StFahFlg", 0), unit)
                for mac, setpoint in zones.items()
            }
            for mode, zones in self.coordinator.setpoint_memory.items()
            if int(mode) in MOD_TO_HVAC
        }
        return {
            "raw_mode": self.values.get("Mod"),
            "error_code": self.values.get("AllErr"),
            "setpoint_memory": memory,
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_command(self.sub_mac, {"Pow": 0})
        else:
            await self.coordinator.async_set_mode(HVAC_TO_MOD[hvac_mode])

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.async_command(self.sub_mac, {"WdSpd": FAN_TO_SPD[fan_mode]})

    async def async_turn_on(self) -> None:
        await self.coordinator.async_command(self.sub_mac, {"Pow": 1})

    async def async_turn_off(self) -> None:
        await self.coordinator.async_command(self.sub_mac, {"Pow": 0})
