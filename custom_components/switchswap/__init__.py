"""SwitchSwap – defekte Geräte tauschen und Entitäten auf das Ersatzgerät übernehmen."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PANEL_ICON, PANEL_TITLE, PANEL_URL_PATH, PANEL_WEBCOMPONENT
from .services import async_register_services, async_unregister_services
from .swap import SwapManager
from .websocket import async_register_websocket

FRONTEND_URL = f"/{DOMAIN}_frontend"
FRONTEND_DIR = Path(__file__).parent / "frontend"
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


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
    await _async_register_panel(hass)
    return True


async def _async_register_panel(hass: HomeAssistant) -> None:
    # Statische Pfade und WebSocket-Befehle lassen sich nicht wieder abmelden,
    # daher nur einmal pro Home-Assistant-Lauf registrieren.
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(FRONTEND_DIR), False)]
        )
        async_register_websocket(hass)
        hass.data[_STATIC_REGISTERED] = True

    version = (await async_get_integration(hass, DOMAIN)).version
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_WEBCOMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{FRONTEND_URL}/switchswap-panel.js?v={version}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=True,
        config={},
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    async_unregister_services(hass)
    hass.data.pop(DOMAIN, None)
    return True
