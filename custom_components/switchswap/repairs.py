"""Reparatur-Flow: neu angelerntes Gerät als Ersatz übernehmen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import BooleanSelector

from .const import CONF_IS_REPLACEMENT, CONF_SWAP_ID
from .flow_helpers import SwapMappingMixin, get_manager, pending_selector
from .swap import device_label


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    return NewDeviceRepairFlow((data or {}).get("new_device_id"))


class NewDeviceRepairFlow(SwapMappingMixin, RepairsFlow):
    """Fragt, welches vorgemerkte Gerät durch das neue ersetzt wird."""

    def __init__(self, new_device_id: str | None) -> None:
        self._new_device_id = new_device_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        manager = get_manager(self.hass)
        if manager is None or not manager.pending:
            return self.async_abort(reason="no_pending")
        device = dr.async_get(self.hass).async_get(self._new_device_id or "")
        if device is None:
            return self.async_abort(reason="device_not_found")

        if user_input is not None:
            if not user_input[CONF_IS_REPLACEMENT]:
                return self.async_create_entry(data={})
            self._swap_id = user_input[CONF_SWAP_ID]
            return await self.async_step_mapping()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IS_REPLACEMENT, default=True): BooleanSelector(),
                    vol.Required(
                        CONF_SWAP_ID, default=next(iter(manager.pending))
                    ): pending_selector(manager),
                }
            ),
            description_placeholders={"device": device_label(device)},
        )

    async def _async_swap_done(self, result: dict[str, Any]) -> FlowResult:
        return self.async_create_entry(data={})
