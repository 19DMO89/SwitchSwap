"""WebSocket-API für das SwitchSwap-Panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .swap import SwapError, SwapManager


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    for command in (
        ws_pending,
        ws_devices,
        ws_prepare,
        ws_suggest,
        ws_complete,
        ws_cancel,
        ws_exchange_suggest,
        ws_exchange,
    ):
        websocket_api.async_register_command(hass, command)


def _manager(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> SwapManager | None:
    if (manager := hass.data.get(DOMAIN)) is None:
        connection.send_error(msg["id"], "not_loaded", "SwitchSwap ist nicht geladen")
    return manager


@websocket_api.websocket_command({vol.Required("type"): "switchswap/pending"})
@websocket_api.require_admin
@callback
def ws_pending(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if manager := _manager(hass, connection, msg):
        connection.send_result(msg["id"], {"pending": manager.pending_overview()})


@websocket_api.websocket_command({vol.Required("type"): "switchswap/devices"})
@websocket_api.require_admin
@callback
def ws_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if manager := _manager(hass, connection, msg):
        connection.send_result(msg["id"], {"devices": manager.devices_overview()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "switchswap/prepare",
        vol.Required("device_id"): str,
        vol.Optional("remove_device", default=True): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_prepare(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (manager := _manager(hass, connection, msg)):
        return
    try:
        snapshot = await manager.async_prepare(msg["device_id"], msg["remove_device"])
    except SwapError as err:
        connection.send_error(msg["id"], err.key, str(err))
        return
    connection.send_result(
        msg["id"], {"swap_id": snapshot["device_id"], "label": snapshot["label"]}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "switchswap/suggest",
        vol.Required("swap_id"): str,
        vol.Required("new_device_id"): str,
    }
)
@websocket_api.require_admin
@callback
def ws_suggest(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (manager := _manager(hass, connection, msg)):
        return
    try:
        result = manager.mapping_context(msg["swap_id"], msg["new_device_id"])
    except SwapError as err:
        connection.send_error(msg["id"], err.key, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "switchswap/complete",
        vol.Required("swap_id"): str,
        vol.Required("new_device_id"): str,
        vol.Required("mapping"): {str: vol.Any(None, str)},
        vol.Optional("update_automations", default=True): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_complete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (manager := _manager(hass, connection, msg)):
        return
    targets = [value for value in msg["mapping"].values() if value]
    if len(targets) != len(set(targets)):
        connection.send_error(
            msg["id"], "duplicate_target", "Eine neue Entität ist mehrfach zugeordnet"
        )
        return
    try:
        result = await manager.async_complete(
            msg["swap_id"],
            msg["new_device_id"],
            msg["mapping"],
            msg["update_automations"],
        )
    except SwapError as err:
        connection.send_error(msg["id"], err.key, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "switchswap/cancel", vol.Required("swap_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_cancel(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (manager := _manager(hass, connection, msg)):
        return
    try:
        await manager.async_cancel(msg["swap_id"])
    except SwapError as err:
        connection.send_error(msg["id"], err.key, str(err))
        return
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "switchswap/exchange_suggest",
        vol.Required("device_a"): str,
        vol.Required("device_b"): str,
    }
)
@websocket_api.require_admin
@callback
def ws_exchange_suggest(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (manager := _manager(hass, connection, msg)):
        return
    try:
        result = manager.exchange_context(msg["device_a"], msg["device_b"])
    except SwapError as err:
        connection.send_error(msg["id"], err.key, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "switchswap/exchange",
        vol.Required("device_a"): str,
        vol.Required("device_b"): str,
        vol.Required("mapping"): {str: vol.Any(None, str)},
        vol.Optional("update_automations", default=True): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_exchange(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (manager := _manager(hass, connection, msg)):
        return
    try:
        result = await manager.async_exchange(
            msg["device_a"],
            msg["device_b"],
            msg["mapping"],
            msg["update_automations"],
        )
    except SwapError as err:
        connection.send_error(msg["id"], err.key, str(err))
        return
    connection.send_result(msg["id"], result)
