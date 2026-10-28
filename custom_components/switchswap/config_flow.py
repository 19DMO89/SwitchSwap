"""Config- und Options-Flow für SwitchSwap."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import BooleanSelector, DeviceSelector

from .const import (
    CONF_DEVICE_ID,
    CONF_NEW_DEVICE_ID,
    CONF_REMOVE_DEVICE,
    CONF_SWAP_ID,
    DOMAIN,
)
from .flow_helpers import SwapMappingMixin, get_manager, pending_selector
from .swap import SwapError


class SwitchSwapConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung – es gibt nichts zu konfigurieren."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="SwitchSwap", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SwitchSwapOptionsFlow()


class SwitchSwapOptionsFlow(SwapMappingMixin, OptionsFlow):
    """Menü: Gerät vormerken, Tausch abschließen, Tausch verwerfen."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        manager = get_manager(self.hass)
        if manager is None:
            return self.async_abort(reason="not_loaded")
        menu = ["prepare"]
        if manager.pending:
            menu += ["complete", "cancel"]
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders={"pending": manager.pending_summary()},
        )

    async def async_step_prepare(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        manager = get_manager(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                snapshot = await manager.async_prepare(
                    user_input[CONF_DEVICE_ID], user_input[CONF_REMOVE_DEVICE]
                )
            except SwapError as err:
                errors["base"] = err.key
            else:
                return self.async_abort(
                    reason="prepared",
                    description_placeholders={
                        "device": snapshot["label"],
                        "count": str(len(snapshot["entities"])),
                    },
                )
        return self.async_show_form(
            step_id="prepare",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): DeviceSelector(),
                    vol.Required(CONF_REMOVE_DEVICE, default=True): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        manager = get_manager(self.hass)
        if not manager.pending:
            return self.async_abort(reason="no_pending")
        errors: dict[str, str] = {}
        if user_input is not None:
            new_device_id = user_input[CONF_NEW_DEVICE_ID]
            if new_device_id == user_input[CONF_SWAP_ID]:
                errors["base"] = "same_device"
            elif dr.async_get(self.hass).async_get(new_device_id) is None:
                errors["base"] = "device_not_found"
            else:
                self._swap_id = user_input[CONF_SWAP_ID]
                self._new_device_id = new_device_id
                return await self.async_step_mapping()
        return self.async_show_form(
            step_id="complete",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SWAP_ID): pending_selector(manager),
                    vol.Required(CONF_NEW_DEVICE_ID): DeviceSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_cancel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        manager = get_manager(self.hass)
        if not manager.pending:
            return self.async_abort(reason="no_pending")
        if user_input is not None:
            label = manager.pending[user_input[CONF_SWAP_ID]]["label"]
            await manager.async_cancel(user_input[CONF_SWAP_ID])
            return self.async_abort(
                reason="cancelled", description_placeholders={"device": label}
            )
        return self.async_show_form(
            step_id="cancel",
            data_schema=vol.Schema({vol.Required(CONF_SWAP_ID): pending_selector(manager)}),
        )

    async def _async_swap_done(self, result: dict[str, Any]) -> ConfigFlowResult:
        return self.async_abort(
            reason="completed",
            description_placeholders={
                "old": result["old_device"],
                "new": result["new_device"],
                "mapped": str(len(result["mapped"])),
                "skipped": str(len(result["skipped"])),
            },
        )
