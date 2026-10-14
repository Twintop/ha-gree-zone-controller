"""The temperature unit of the controller and its wall panel."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GreeZoneCoordinator
from .entity import GreeZoneEntity
from .temperature import UNIT_C, UNIT_F

UNIT_OPTIONS = {UNIT_C: UnitOfTemperature.CELSIUS.value, UNIT_F: UnitOfTemperature.FAHRENHEIT.value}
OPTION_UNITS = {option: unit for unit, option in UNIT_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: GreeZoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GreeTemperatureUnit(coordinator)])


class GreeTemperatureUnit(GreeZoneEntity, SelectEntity):
    """°C or °F, for the whole controller.

    TemUnit is written to the AC unit. The controller, the wall panel and every
    zone switch with it; the zone setpoints keep their value.
    """

    _attr_name = "Temperature unit"
    _attr_icon = "mdi:thermometer"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(UNIT_OPTIONS.values())

    def __init__(self, coordinator: GreeZoneCoordinator) -> None:
        super().__init__(coordinator, coordinator.ac_unit)
        self._attr_unique_id = f"{coordinator.ac_unit}_temperature_unit"

    @property
    def current_option(self) -> str | None:
        return UNIT_OPTIONS.get(self.values.get("TemUnit"))

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_command(self.sub_mac, {"TemUnit": OPTION_UNITS[option]})
