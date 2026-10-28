"""SwitchSwap – defekte Geräte tauschen und Entitäten auf das Ersatzgerät übernehmen."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .services import async_register_services, async_unregister_services
from .swap import SwapManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = SwapManager(hass)
    await manager.async_load()
    hass.data[DOMAIN] = manager

    async_register_services(hass)
    entry.async_on_unload(
        hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED, manager.async_handle_device_event
        )
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    async_unregister_services(hass)
    hass.data.pop(DOMAIN, None)
    return True
