"""Zone damper switches."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GreeZoneCoordinator
from .entity import GreeZoneEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: GreeZoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Always-on zones get no switch: switching them off is refused by the
    # controller or shuts the whole system down.
    async_add_entities(
        [
            GreeSystemSwitch(coordinator),
            *(GreeZoneSwitch(coordinator, z) for z in coordinator.zones if not z["always_on"]),
        ]
    )


class GreeSystemSwitch(GreeZoneEntity, SwitchEntity):
    """Whole-system power. Zones keep their own setting while the system is off."""

    _attr_name = "System"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: GreeZoneCoordinator) -> None:
        super().__init__(coordinator, coordinator.ac_unit)
        self._attr_unique_id = f"{coordinator.ac_unit}_system"

    @property
    def is_on(self) -> bool | None:
        pow_ = self.values.get("Pow")
        return None if pow_ is None else pow_ == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.sub_mac, {"Pow": 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.sub_mac, {"Pow": 0})


class GreeZoneSwitch(GreeZoneEntity, SwitchEntity):
    """Opens/closes one zone."""

    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: GreeZoneCoordinator, zone: dict[str, Any]) -> None:
        super().__init__(coordinator, zone["mac"])
        self._attr_name = zone["name"]
        self._attr_unique_id = f"{zone['mac']}_zone"

    @property
    def is_on(self) -> bool | None:
        pow_ = self.values.get("Pow")
        return None if pow_ is None else pow_ == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.sub_mac, {"Pow": 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.sub_mac, {"Pow": 0})
