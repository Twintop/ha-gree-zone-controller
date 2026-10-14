"""Per-zone target temperatures."""
from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GreeZoneCoordinator
from .entity import GreeZoneEntity
from .temperature import MAX_C, MAX_F, MIN_C, MIN_F, UNIT_F, from_unit, to_unit


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: GreeZoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(GreeZoneSetpoint(coordinator, zone) for zone in coordinator.zones)


class GreeZoneSetpoint(GreeZoneEntity, NumberEntity):
    """A zone's setpoint, in the controller's unit: half degrees in °C, whole in °F.

    Home Assistant shows it in the user's own unit.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: GreeZoneCoordinator, zone: dict[str, Any]) -> None:
        super().__init__(coordinator, zone["mac"])
        self._attr_name = f"{zone['name']} target temperature"
        self._attr_unique_id = f"{zone['mac']}_target_temperature"

    @property
    def _fahrenheit(self) -> bool:
        return self.coordinator.temperature_unit == UNIT_F

    @property
    def native_unit_of_measurement(self) -> str:
        return UnitOfTemperature.FAHRENHEIT if self._fahrenheit else UnitOfTemperature.CELSIUS

    @property
    def native_min_value(self) -> float:
        return MIN_F if self._fahrenheit else MIN_C

    @property
    def native_max_value(self) -> float:
        return MAX_F if self._fahrenheit else MAX_C

    @property
    def native_step(self) -> float:
        return 1 if self._fahrenheit else 0.5

    @property
    def native_value(self) -> float | None:
        raw = self.values.get("StTem")
        if raw is None:
            return None
        return to_unit(raw, self.values.get("StFahFlg", 0), self.coordinator.temperature_unit)

    async def async_set_native_value(self, value: float) -> None:
        raw, bit = from_unit(value, self.coordinator.temperature_unit)
        # Both columns: the controller keeps an old bit when only StTem is sent.
        await self.coordinator.async_command(self.sub_mac, {"StTem": raw, "StFahFlg": bit})
