"""Konstanten für SwitchSwap."""

from __future__ import annotations

DOMAIN = "switchswap"

STORAGE_KEY = f"{DOMAIN}.pending"
STORAGE_VERSION = 1

CONF_DEVICE_ID = "device_id"
CONF_REMOVE_DEVICE = "remove_device"
CONF_SWAP_ID = "swap_id"
CONF_NEW_DEVICE_ID = "new_device_id"
CONF_OLD_DEVICE_ID = "old_device_id"
CONF_UPDATE_AUTOMATIONS = "update_automations"
CONF_MAPPING = "mapping"
CONF_IS_REPLACEMENT = "is_replacement"

SERVICE_PREPARE = "prepare_swap"
SERVICE_COMPLETE = "complete_swap"
SERVICE_CANCEL = "cancel_swap"
SERVICE_LIST = "list_pending"

ISSUE_NEW_DEVICE = "new_device"

# Wert im Zuordnungs-Dropdown für "diese Entität nicht übernehmen"
NO_MATCH = "__none__"

# Dateien, in denen Geräte-/Entitäts-Registry-IDs ersetzt werden
YAML_FILES = ("automations.yaml", "scripts.yaml")
