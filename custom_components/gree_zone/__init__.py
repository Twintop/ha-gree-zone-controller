"""The Gree Zone Controller integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .api import GreeZoneClient
from .const import CONF_KEY, CONF_MAC, DOMAIN, PLATFORMS
from .coordinator import GreeZoneCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = GreeZoneClient(entry.data[CONF_HOST], entry.data[CONF_MAC], entry.data[CONF_KEY])
    coordinator = GreeZoneCoordinator(hass, entry, client)
    await coordinator.async_load_memory()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
