"""Per-zone target temperatures."""
from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MAX_TEMP, MIN_TEMP, TEMP_OFFSET
from .coordinator import GreeZoneCoordinator
from .entity import GreeZoneEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: GreeZoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(GreeZoneSetpoint(coordinator, zone) for zone in coordinator.zones)


class GreeZoneSetpoint(GreeZoneEntity, NumberEntity):
    """A zone's setpoint; the controller stores it as degrees above 16 °C."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_TEMP
    _attr_native_max_value = MAX_TEMP
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: GreeZoneCoordinator, zone: dict[str, Any]) -> None:
        super().__init__(coordinator, zone["mac"])
        self._attr_name = f"{zone['name']} target temperature"
        self._attr_unique_id = f"{zone['mac']}_target_temperature"

    @property
    def native_value(self) -> float | None:
        raw = self.values.get("StTem")
        return None if raw is None else raw + TEMP_OFFSET

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(self.sub_mac, {"StTem": int(value) - TEMP_OFFSET})
