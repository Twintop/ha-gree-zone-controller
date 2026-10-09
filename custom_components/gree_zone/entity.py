"""Base entity for the Gree Zone Controller."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GreeZoneCoordinator


class GreeZoneEntity(CoordinatorEntity[GreeZoneCoordinator]):
    """An entity backed by one sub-unit of the zone controller."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GreeZoneCoordinator, sub_mac: str) -> None:
        super().__init__(coordinator)
        self.sub_mac = sub_mac
        gateway = coordinator.client.mac
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway)},
            name="Gree Zone Controller",
            manufacturer="Gree",
            model="LE60-13/GH zone controller",
        )

    @property
    def values(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self.sub_mac, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self.values)
