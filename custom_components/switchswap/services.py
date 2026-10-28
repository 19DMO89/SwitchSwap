"""Dienste von SwitchSwap (für Automationen und Skripte)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEVICE_ID,
    CONF_MAPPING,
    CONF_NEW_DEVICE_ID,
    CONF_OLD_DEVICE_ID,
    CONF_REMOVE_DEVICE,
    CONF_UPDATE_AUTOMATIONS,
    DOMAIN,
    SERVICE_CANCEL,
    SERVICE_COMPLETE,
    SERVICE_LIST,
    SERVICE_PREPARE,
)
from .swap import SwapManager

PREPARE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Optional(CONF_REMOVE_DEVICE, default=True): cv.boolean,
    }
)
COMPLETE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_OLD_DEVICE_ID): cv.string,
        vol.Required(CONF_NEW_DEVICE_ID): cv.string,
        vol.Optional(CONF_UPDATE_AUTOMATIONS, default=True): cv.boolean,
        vol.Optional(CONF_MAPPING): {cv.entity_id: vol.Any(None, cv.entity_id)},
    }
)
CANCEL_SCHEMA = vol.Schema({vol.Required(CONF_OLD_DEVICE_ID): cv.string})


def _manager(hass: HomeAssistant) -> SwapManager:
    if (manager := hass.data.get(DOMAIN)) is None:
        raise HomeAssistantError("SwitchSwap ist nicht geladen")
    return manager


@callback
def async_register_services(hass: HomeAssistant) -> None:
    async def _prepare(call: ServiceCall) -> ServiceResponse:
        snapshot = await _manager(hass).async_prepare(
            call.data[CONF_DEVICE_ID], call.data[CONF_REMOVE_DEVICE]
        )
        return {
            "old_device_id": snapshot["device_id"],
            "device": snapshot["label"],
            "entities": [entity["entity_id"] for entity in snapshot["entities"]],
        }

    async def _complete(call: ServiceCall) -> ServiceResponse:
        return await _manager(hass).async_complete(
            call.data[CONF_OLD_DEVICE_ID],
            call.data[CONF_NEW_DEVICE_ID],
            call.data.get(CONF_MAPPING),
            call.data[CONF_UPDATE_AUTOMATIONS],
        )

    async def _cancel(call: ServiceCall) -> None:
        await _manager(hass).async_cancel(call.data[CONF_OLD_DEVICE_ID])

    async def _list(call: ServiceCall) -> ServiceResponse:
        pending: list[dict[str, Any]] = [
            {
                "old_device_id": swap_id,
                "device": snap["label"],
                "manufacturer": snap["manufacturer"],
                "model": snap["model"],
                "created": snap["created"],
                "removed": snap["removed"],
                "entities": [entity["entity_id"] for entity in snap["entities"]],
            }
            for swap_id, snap in _manager(hass).pending.items()
        ]
        return {"pending": pending}

    hass.services.async_register(
        DOMAIN, SERVICE_PREPARE, _prepare, PREPARE_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE, _complete, COMPLETE_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _cancel, CANCEL_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_LIST, _list, supports_response=SupportsResponse.ONLY
    )


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    for service in (SERVICE_PREPARE, SERVICE_COMPLETE, SERVICE_CANCEL, SERVICE_LIST):
        hass.services.async_remove(DOMAIN, service)
