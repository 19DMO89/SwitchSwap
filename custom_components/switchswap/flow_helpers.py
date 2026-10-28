"""Gemeinsame Flow-Schritte für Options-Flow und Reparatur-Flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_UPDATE_AUTOMATIONS, DOMAIN, NO_MATCH
from .swap import SwapError, SwapManager, device_label


def get_manager(hass: HomeAssistant) -> SwapManager | None:
    return hass.data.get(DOMAIN)


def pending_selector(manager: SwapManager) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(
                    value=swap_id,
                    label=f"{snap['label']} ({snap.get('manufacturer') or ''} {snap.get('model') or ''})".replace(" ()", ""),
                )
                for swap_id, snap in manager.pending.items()
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class SwapMappingMixin:
    """Stellt den Schritt 'mapping' (Entitäten zuordnen) bereit."""

    hass: HomeAssistant
    _swap_id: str | None = None
    _new_device_id: str | None = None

    async def _async_swap_done(self, result: dict[str, Any]) -> FlowResult:
        raise NotImplementedError

    async def async_step_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        manager = get_manager(self.hass)
        if manager is None or self._swap_id not in manager.pending:
            return self.async_abort(reason="no_pending")  # type: ignore[attr-defined]
        snapshot = manager.pending[self._swap_id]
        new_device = dr.async_get(self.hass).async_get(self._new_device_id)
        if new_device is None:
            return self.async_abort(reason="device_not_found")  # type: ignore[attr-defined]

        errors: dict[str, str] = {}
        error_text = ""
        if user_input is not None:
            data = dict(user_input)
            update_automations = data.pop(CONF_UPDATE_AUTOMATIONS, True)
            mapping = {key: (None if val == NO_MATCH else val) for key, val in data.items()}
            targets = [val for val in mapping.values() if val]
            if len(targets) != len(set(targets)):
                errors["base"] = "duplicate_target"
            else:
                try:
                    result = await manager.async_complete(
                        self._swap_id, self._new_device_id, mapping, update_automations
                    )
                except SwapError as err:
                    errors["base"] = err.key
                    error_text = str(err)
                else:
                    return await self._async_swap_done(result)
            defaults = {key: val or NO_MATCH for key, val in mapping.items()}
        else:
            defaults = {
                key: val or NO_MATCH
                for key, val in manager.suggest_mapping(
                    self._swap_id, self._new_device_id
                ).items()
            }

        new_entries = manager.device_entities(self._new_device_id)
        fields: dict[Any, Any] = {}
        for old in snapshot["entities"]:
            options = [SelectOptionDict(value=NO_MATCH, label="— nicht übernehmen / skip —")]
            options += [
                SelectOptionDict(
                    value=entry.entity_id,
                    label=f"{entry.entity_id}"
                    + (f" ({entry.original_name})" if entry.original_name else ""),
                )
                for entry in new_entries
                if entry.domain == old["domain"]
            ]
            fields[vol.Required(old["entity_id"], default=defaults.get(old["entity_id"], NO_MATCH))] = SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
            )
        fields[vol.Required(CONF_UPDATE_AUTOMATIONS, default=True)] = BooleanSelector()

        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="mapping",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "old": snapshot["label"],
                "new": device_label(new_device),
                "count": str(len(snapshot["entities"])),
                "error": error_text,
            },
        )
