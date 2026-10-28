"""Kernlogik von SwitchSwap: Geräte sichern, entfernen und auf ein neues Gerät übertragen."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
import logging
import os
import re
import shutil
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
    label_registry as lr,
)
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ISSUE_NEW_DEVICE,
    STORAGE_KEY,
    STORAGE_VERSION,
    YAML_FILES,
)

_LOGGER = logging.getLogger(__name__)


class SwapError(HomeAssistantError):
    """Fehler mit Übersetzungsschlüssel für die Flows."""

    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key


def device_label(device: dr.DeviceEntry) -> str:
    """Anzeigename eines Geräts."""
    return device.name_by_user or device.name or device.model or device.id


def _plain(value: Any) -> Any:
    """Registry-Werte JSON-tauglich machen."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _plain(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(val) for val in value]
    return value


def _snapshot_entity(entry: er.RegistryEntry) -> dict[str, Any]:
    return {
        "registry_id": entry.id,
        "entity_id": entry.entity_id,
        "unique_id": str(entry.unique_id),
        "platform": entry.platform,
        "domain": entry.domain,
        "name": entry.name,
        "original_name": entry.original_name,
        "icon": entry.icon,
        "area_id": entry.area_id,
        "labels": list(entry.labels),
        "aliases": list(entry.aliases),
        "device_class": entry.device_class,
        "original_device_class": entry.original_device_class,
        "translation_key": entry.translation_key,
        "unit_of_measurement": entry.unit_of_measurement,
        "entity_category": _plain(entry.entity_category),
        "hidden_by": _plain(entry.hidden_by),
        "disabled_by": _plain(entry.disabled_by),
        "options": _plain(entry.options),
    }


def _device_tokens(identifiers: Any, connections: Any) -> list[str]:
    """Gerätespezifische Kennungen (MAC, IEEE, ...) für den unique_id-Vergleich."""
    tokens: set[str] = set()
    for item in [*identifiers, *connections]:
        value = "_".join(str(part) for part in list(item)[1:]).lower()
        if len(value) >= 4:
            tokens.add(value)
            tokens.add(re.sub(r"[:\-_]", "", value))
    return sorted(tokens, key=len, reverse=True)


def _uid_rest(unique_id: str, tokens: list[str]) -> str:
    uid = unique_id.lower()
    for token in tokens:
        uid = uid.replace(token, "")
    return uid


def _uid_tail(unique_id: str) -> str:
    return "-".join(re.split(r"[.\-_:/]", unique_id.lower())[-2:])


def _score(
    old: dict[str, Any],
    new: er.RegistryEntry,
    old_tokens: list[str],
    new_tokens: list[str],
) -> int:
    """Wie gut passt eine neue Entität zu einer alten? -1 = gar nicht."""
    if old["domain"] != new.domain:
        return -1
    score = 1
    if old["translation_key"] and old["translation_key"] == new.translation_key:
        score += 4
    if (
        old["original_device_class"]
        and old["original_device_class"] == new.original_device_class
    ):
        score += 3
    if old["original_name"] and old["original_name"] == new.original_name:
        score += 3
    old_rest = _uid_rest(old["unique_id"], old_tokens)
    if (
        old_rest
        and old["platform"] == new.platform
        and old_rest == _uid_rest(str(new.unique_id), new_tokens)
    ):
        score += 5
    elif _uid_tail(old["unique_id"]) == _uid_tail(str(new.unique_id)):
        score += 2
    if (
        old["unit_of_measurement"]
        and old["unit_of_measurement"] == new.unit_of_measurement
    ):
        score += 1
    if old["entity_category"] == _plain(new.entity_category):
        score += 1
    return score


class SwapManager:
    """Verwaltet vorgemerkte Gerätetausche."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.pending: dict[str, dict[str, Any]] = {}
        self._issue_ids: set[str] = set()

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.pending = data.get("pending", {})

    async def _async_save(self) -> None:
        await self._store.async_save({"pending": self.pending})

    # ------------------------------------------------------------------ helpers

    def device_entities(self, device_id: str) -> list[er.RegistryEntry]:
        return er.async_entries_for_device(
            er.async_get(self.hass), device_id, include_disabled_entities=True
        )

    def pending_overview(self) -> list[dict[str, Any]]:
        return [
            {
                "old_device_id": swap_id,
                "device": snap["label"],
                "manufacturer": snap["manufacturer"],
                "model": snap["model"],
                "created": snap["created"],
                "removed": snap["removed"],
                "entities": [
                    {
                        "entity_id": entity["entity_id"],
                        "name": entity["name"] or entity["original_name"],
                    }
                    for entity in snap["entities"]
                ],
            }
            for swap_id, snap in self.pending.items()
        ]

    def devices_overview(self) -> list[dict[str, Any]]:
        """Alle Geräte für die Auswahl im Panel."""
        area_reg = ar.async_get(self.hass)
        result = []
        for device in dr.async_get(self.hass).devices.values():
            if device.entry_type == dr.DeviceEntryType.SERVICE:
                continue
            area = area_reg.async_get_area(device.area_id) if device.area_id else None
            created_at = getattr(device, "created_at", None)
            result.append(
                {
                    "id": device.id,
                    "label": device_label(device),
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "area": area.name if area else None,
                    "integrations": sorted(
                        {
                            entry.domain
                            for entry_id in device.config_entries
                            if (entry := self.hass.config_entries.async_get_entry(entry_id))
                        }
                    ),
                    "entities": len(self.device_entities(device.id)),
                    "created_at": created_at.isoformat() if created_at else None,
                    "pending": device.id in self.pending,
                }
            )
        return result

    def mapping_context(self, swap_id: str, new_device_id: str) -> dict[str, Any]:
        """Alte Entitäten, neue Entitäten und Zuordnungsvorschlag für das Panel."""
        if swap_id not in self.pending:
            raise SwapError("no_pending", f"Kein vorgemerkter Tausch für {swap_id}")
        if swap_id == new_device_id:
            raise SwapError("same_device", "Altes und neues Gerät sind identisch")
        new_device = dr.async_get(self.hass).async_get(new_device_id)
        if new_device is None:
            raise SwapError("device_not_found", f"Gerät {new_device_id} nicht gefunden")
        snapshot = self.pending[swap_id]
        return {
            "old_device": snapshot["label"],
            "new_device": device_label(new_device),
            "old_entities": [
                {
                    "entity_id": entity["entity_id"],
                    "domain": entity["domain"],
                    "name": entity["name"] or entity["original_name"],
                }
                for entity in snapshot["entities"]
            ],
            "new_entities": [
                {
                    "entity_id": entry.entity_id,
                    "domain": entry.domain,
                    "name": entry.name or entry.original_name,
                }
                for entry in self.device_entities(new_device_id)
            ],
            "suggestion": self.suggest_mapping(swap_id, new_device_id),
        }

    def pending_summary(self) -> str:
        if not self.pending:
            return "–"
        return "\n".join(
            f"- {snap['label']} ({len(snap['entities'])} Entitäten, {snap['created'][:10]})"
            for snap in self.pending.values()
        )

    # ------------------------------------------------------------------ prepare

    async def async_prepare(
        self, device_id: str, remove_device: bool = True
    ) -> dict[str, Any]:
        """Gerät sichern und optional entfernen."""
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get(device_id)
        if device is None:
            raise SwapError("device_not_found", f"Gerät {device_id} nicht gefunden")
        if device_id in self.pending:
            raise SwapError(
                "already_pending", f"Für {device_label(device)} ist bereits ein Tausch vorgemerkt"
            )

        entries = self.device_entities(device_id)
        snapshot: dict[str, Any] = {
            "device_id": device.id,
            "label": device_label(device),
            "name": device.name,
            "name_by_user": device.name_by_user,
            "area_id": device.area_id,
            "labels": list(device.labels),
            "manufacturer": device.manufacturer,
            "model": device.model,
            "identifiers": [list(item) for item in device.identifiers],
            "connections": [list(item) for item in device.connections],
            "config_entries": list(device.config_entries),
            "created": dt_util.utcnow().isoformat(),
            "removed": False,
            "entities": [_snapshot_entity(entry) for entry in entries],
        }
        self.pending[device_id] = snapshot
        await self._async_save()

        if remove_device:
            await self._async_remove_device(device)
            snapshot["removed"] = True
            await self._async_save()

        persistent_notification.async_create(
            self.hass,
            f"**{snapshot['label']}** wurde mit {len(entries)} Entitäten gesichert"
            + (" und entfernt" if remove_device else "")
            + ".\n\nLerne jetzt das Ersatzgerät an. SwitchSwap meldet neue Geräte "
            "unter *Einstellungen → Reparaturen*, alternativ: *Geräte & Dienste → "
            "SwitchSwap → Konfigurieren → Tausch abschließen*.",
            title="SwitchSwap: Gerät vorgemerkt",
            notification_id=f"{DOMAIN}_{device_id}",
        )
        return snapshot

    async def _async_remove_device(self, device: dr.DeviceEntry) -> None:
        """Gerät aus den Integrationen und der Registry entfernen."""
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        entries = self.device_entities(device.id)

        for entry_id in list(device.config_entries):
            config_entry = self.hass.config_entries.async_get_entry(entry_id)
            if config_entry is None:
                continue
            removed = False
            try:
                integration = await async_get_integration(self.hass, config_entry.domain)
                component = await integration.async_get_component()
                if hasattr(component, "async_remove_config_entry_device"):
                    removed = await component.async_remove_config_entry_device(
                        self.hass, config_entry, device
                    )
            except Exception:  # noqa: BLE001 - Integrationsfehler dürfen den Tausch nicht blockieren
                _LOGGER.exception(
                    "Integration %s konnte Gerät %s nicht entfernen",
                    config_entry.domain,
                    device.id,
                )
            if removed and dev_reg.async_get(device.id):
                dev_reg.async_update_device(device.id, remove_config_entry_id=entry_id)

        for entry in entries:
            if ent_reg.async_get(entry.entity_id):
                ent_reg.async_remove(entry.entity_id)
        if dev_reg.async_get(device.id):
            dev_reg.async_remove_device(device.id)

    # ------------------------------------------------------------------ mapping

    def suggest_mapping(self, swap_id: str, new_device_id: str) -> dict[str, str | None]:
        """Automatische Zuordnung alte Entität -> neue Entität."""
        snapshot = self.pending[swap_id]
        new_device = dr.async_get(self.hass).async_get(new_device_id)
        new_entries = self.device_entities(new_device_id)
        old_tokens = _device_tokens(snapshot["identifiers"], snapshot["connections"])
        new_tokens = (
            _device_tokens(new_device.identifiers, new_device.connections)
            if new_device
            else []
        )

        pairs = []
        for index, old in enumerate(snapshot["entities"]):
            for new in new_entries:
                if (score := _score(old, new, old_tokens, new_tokens)) > 0:
                    pairs.append((score, index, new.entity_id))
        pairs.sort(key=lambda pair: (-pair[0], pair[1]))

        mapping: dict[str, str | None] = {
            old["entity_id"]: None for old in snapshot["entities"]
        }
        used: set[str] = set()
        for _score_value, index, new_entity_id in pairs:
            old_entity_id = snapshot["entities"][index]["entity_id"]
            if mapping[old_entity_id] is None and new_entity_id not in used:
                mapping[old_entity_id] = new_entity_id
                used.add(new_entity_id)
        return mapping

    # ------------------------------------------------------------------ complete

    async def async_complete(
        self,
        swap_id: str,
        new_device_id: str,
        mapping: dict[str, str | None] | None = None,
        update_automations: bool = True,
    ) -> dict[str, Any]:
        """Tausch abschließen: Einstellungen des alten Geräts auf das neue übertragen."""
        snapshot = self.pending.get(swap_id)
        if snapshot is None:
            raise SwapError("no_pending", f"Kein vorgemerkter Tausch für {swap_id}")
        if new_device_id == swap_id:
            raise SwapError("same_device", "Altes und neues Gerät sind identisch")

        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        new_device = dev_reg.async_get(new_device_id)
        if new_device is None:
            raise SwapError("device_not_found", f"Gerät {new_device_id} nicht gefunden")

        if mapping is None:
            mapping = self.suggest_mapping(swap_id, new_device_id)

        # Zuordnung auf Registry-IDs auflösen, weil sich entity_ids unterwegs ändern
        resolved: list[tuple[dict[str, Any], str]] = []
        skipped: list[str] = []
        errors: list[str] = []
        for old in snapshot["entities"]:
            new_entity_id = mapping.get(old["entity_id"])
            if not new_entity_id:
                skipped.append(old["entity_id"])
                continue
            new_entry = ent_reg.async_get(new_entity_id)
            if new_entry is None or new_entry.device_id != new_device_id:
                errors.append(
                    f"{new_entity_id} gehört nicht zu {device_label(new_device)}"
                )
                skipped.append(old["entity_id"])
                continue
            resolved.append((old, new_entry.id))

        # Falls das alte Gerät beim Vormerken nicht entfernt wurde: jetzt
        old_device = dev_reg.async_get(swap_id)
        if old_device is not None:
            await self._async_remove_device(old_device)

        mapped: list[dict[str, str]] = []
        moved: list[str] = []
        id_map: dict[str, str] = {swap_id: new_device_id}
        for old, registry_id in resolved:
            try:
                moved_id = self._async_apply_entity(old, registry_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Übernahme von %s fehlgeschlagen", old["entity_id"])
                errors.append(f"{old['entity_id']}: {err}")
                continue
            if moved_id:
                moved.append(moved_id)
            mapped.append(
                {
                    "entity_id": old["entity_id"],
                    "from": mapping[old["entity_id"]] or "",
                }
            )
            id_map[old["registry_id"]] = registry_id

        self._apply_device(snapshot, new_device)

        yaml_updated: list[str] = []
        if update_automations:
            try:
                yaml_updated = await self._async_update_yaml_references(id_map)
            except OSError as err:
                errors.append(f"Automationen/Skripte: {err}")

        del self.pending[swap_id]
        await self._async_save()
        self._async_cleanup_issues(new_device_id)
        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{swap_id}")

        result = {
            "old_device": snapshot["label"],
            "new_device": device_label(dev_reg.async_get(new_device_id) or new_device),
            "mapped": mapped,
            "skipped": skipped,
            "renamed_conflicts": moved,
            "yaml_updated": yaml_updated,
            "errors": errors,
        }
        self._notify_result(result)
        return result

    def _async_apply_entity(self, old: dict[str, Any], registry_id: str) -> str | None:
        """Eine Entität übernehmen. Gibt ggf. die entity_id eines verdrängten Eintrags zurück."""
        ent_reg = er.async_get(self.hass)
        target = old["entity_id"]
        current = er.async_resolve_entity_id(ent_reg, registry_id)
        if current is None:
            raise HomeAssistantError("Entität existiert nicht mehr")

        moved_to: str | None = None
        if current != target:
            occupant = ent_reg.async_get(target)
            if occupant is not None:
                object_id = target.split(".", 1)[1]
                moved_to = ent_reg.async_generate_entity_id(
                    occupant.domain, f"{object_id}_old"
                )
                ent_reg.async_update_entity(target, new_entity_id=moved_to)
            elif (state := self.hass.states.get(target)) is not None and (
                state.attributes.get("restored")
            ):
                self.hass.states.async_remove(target)
            ent_reg.async_update_entity(current, new_entity_id=target)

        new_entry = ent_reg.async_get(target)
        assert new_entry is not None
        updates: dict[str, Any] = {"icon": old["icon"]}

        if old["name"] is not None:
            updates["name"] = old["name"]
        elif old["original_name"] and old["original_name"] != new_entry.original_name:
            updates["name"] = old["original_name"]

        if old["area_id"] and ar.async_get(self.hass).async_get_area(old["area_id"]):
            updates["area_id"] = old["area_id"]
        label_reg = lr.async_get(self.hass)
        labels = {label for label in old["labels"] if label_reg.async_get_label(label)}
        if labels:
            updates["labels"] = set(new_entry.labels) | labels
        if old["aliases"]:
            updates["aliases"] = type(new_entry.aliases)(old["aliases"])
        if old["device_class"] is not None:
            updates["device_class"] = old["device_class"]

        if old["hidden_by"] == er.RegistryEntryHider.USER.value:
            updates["hidden_by"] = er.RegistryEntryHider.USER
        elif old["hidden_by"] is None and new_entry.hidden_by is not None:
            updates["hidden_by"] = None
        if old["disabled_by"] == er.RegistryEntryDisabler.USER.value:
            updates["disabled_by"] = er.RegistryEntryDisabler.USER
        elif old["disabled_by"] is None and new_entry.disabled_by is not None:
            updates["disabled_by"] = None

        ent_reg.async_update_entity(target, **updates)

        for domain, options in old["options"].items():
            if domain.endswith(".private") or not isinstance(options, dict):
                continue
            try:
                ent_reg.async_update_entity_options(target, domain, options)
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Optionen %s für %s nicht übernommen", domain, target)
        return moved_to

    def _apply_device(self, snapshot: dict[str, Any], new_device: dr.DeviceEntry) -> None:
        updates: dict[str, Any] = {}
        name = snapshot["name_by_user"] or (
            snapshot["name"] if snapshot["name"] != new_device.name else None
        )
        if name:
            updates["name_by_user"] = name
        if snapshot["area_id"] and ar.async_get(self.hass).async_get_area(
            snapshot["area_id"]
        ):
            updates["area_id"] = snapshot["area_id"]
        label_reg = lr.async_get(self.hass)
        labels = {label for label in snapshot["labels"] if label_reg.async_get_label(label)}
        if labels:
            updates["labels"] = set(new_device.labels) | labels
        if updates:
            dr.async_get(self.hass).async_update_device(new_device.id, **updates)

    async def _async_update_yaml_references(self, id_map: dict[str, str]) -> list[str]:
        """Geräte- und Entitäts-Registry-IDs in automations.yaml / scripts.yaml ersetzen."""
        stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")

        def _update() -> list[str]:
            changed = []
            for filename in YAML_FILES:
                path = self.hass.config.path(filename)
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8") as file:
                    text = file.read()
                new_text = text
                for old_id, new_id in id_map.items():
                    new_text = re.sub(rf"\b{re.escape(old_id)}\b", new_id, new_text)
                if new_text != text:
                    shutil.copy2(path, f"{path}.switchswap-{stamp}.bak")
                    with open(path, "w", encoding="utf-8") as file:
                        file.write(new_text)
                    changed.append(filename)
            return changed

        changed = await self.hass.async_add_executor_job(_update)
        for filename in changed:
            domain = filename.removesuffix(".yaml").removesuffix("s")
            if self.hass.services.has_service(domain, "reload"):
                await self.hass.services.async_call(domain, "reload", blocking=True)
        return changed

    def _notify_result(self, result: dict[str, Any]) -> None:
        lines = [
            f"**{result['old_device']}** → **{result['new_device']}**",
            "",
            f"Übernommen: {len(result['mapped'])} Entitäten",
        ]
        lines += [f"- {item['from']} → {item['entity_id']}" for item in result["mapped"]]
        if result["skipped"]:
            lines += ["", "Nicht zugeordnet (entfernt):"]
            lines += [f"- {entity_id}" for entity_id in result["skipped"]]
        if result["renamed_conflicts"]:
            lines += ["", "Verdrängte Entitäten wurden umbenannt:"]
            lines += [f"- {entity_id}" for entity_id in result["renamed_conflicts"]]
        if result["yaml_updated"]:
            lines += [
                "",
                "Geräte-IDs ersetzt in: " + ", ".join(result["yaml_updated"])
                + " (Backup *.switchswap-*.bak angelegt)",
            ]
        if result["errors"]:
            lines += ["", "Fehler:"] + [f"- {error}" for error in result["errors"]]
        persistent_notification.async_create(
            self.hass,
            "\n".join(lines),
            title="SwitchSwap: Tausch abgeschlossen",
        )

    # ------------------------------------------------------------------ cancel

    async def async_cancel(self, swap_id: str) -> None:
        if self.pending.pop(swap_id, None) is None:
            raise SwapError("no_pending", f"Kein vorgemerkter Tausch für {swap_id}")
        await self._async_save()
        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{swap_id}")
        self._async_cleanup_issues()

    # ------------------------------------------------------------------ new device detection

    @callback
    def async_handle_device_event(self, event: Event) -> None:
        """Bei neu angelerntem Gerät eine Reparatur anbieten."""
        if event.data.get("action") != "create" or not self.pending:
            return
        device_id = event.data["device_id"]
        device = dr.async_get(self.hass).async_get(device_id)
        if device is None:
            return
        issue_id = f"{ISSUE_NEW_DEVICE}_{device_id}"
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="new_device_detected",
            translation_placeholders={"device": device_label(device)},
            data={"new_device_id": device_id},
        )
        self._issue_ids.add(issue_id)

    @callback
    def _async_cleanup_issues(self, new_device_id: str | None = None) -> None:
        for issue_id in list(self._issue_ids):
            if self.pending and issue_id != f"{ISSUE_NEW_DEVICE}_{new_device_id}":
                continue
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            self._issue_ids.discard(issue_id)
