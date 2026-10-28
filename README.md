# SwitchSwap

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/19DMO89/SwitchSwap/actions/workflows/validate.yml/badge.svg)](https://github.com/19DMO89/SwitchSwap/actions/workflows/validate.yml)

**Defekte Geräte in Home Assistant tauschen, ohne Entitäten, Dashboards, Verlauf und Automationen neu einrichten zu müssen.**

Ein Gerät geht kaputt, das Ersatzgerät bekommt neue Entitäts-IDs wie `sensor.0x00158d000a1b2c_temperature` – und plötzlich sind Dashboards, Automationen und Statistiken kaputt. SwitchSwap merkt sich das alte Gerät, löscht es, und überträgt beim Anlernen des Ersatzgeräts alles auf das neue Gerät.

## Was wird übernommen?

| Gerät | Entitäten |
|---|---|
| Name (vom Benutzer vergeben) | **Entitäts-ID** (`sensor.wohnzimmer_temperatur` bleibt gleich) |
| Bereich | Name, Symbol |
| Labels | Bereich, Labels, Aliase (Sprachassistent) |
| | Geräteklasse (falls überschrieben) |
| | Ausgeblendet / deaktiviert / aktiviert |
| | Entitätsoptionen (Einheit, Nachkommastellen, Sprachassistent-Freigabe, …) |

Da die neue Entität die **alte Entitäts-ID** bekommt, laufen weiter:
- Dashboards, Karten, Szenen, Templates, Automationen und Skripte, die `entity_id` verwenden
- **Verlauf und Langzeitstatistiken** (die neue Entität schreibt in die bestehende Historie weiter)

Automationen mit **Geräte-Auslösern/-Aktionen** (`device_id`) werden in `automations.yaml` und `scripts.yaml` automatisch auf das neue Gerät umgeschrieben (abschaltbar, vorher wird ein Backup `*.switchswap-<zeitstempel>.bak` angelegt).

## Installation

### HACS
1. HACS → Integrationen → ⋮ → **Benutzerdefinierte Repositories**
2. `https://github.com/19DMO89/SwitchSwap` als Kategorie **Integration** hinzufügen
3. **SwitchSwap** installieren und Home Assistant neu starten
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen → SwitchSwap*

### Manuell
Ordner `custom_components/switchswap` nach `<config>/custom_components/` kopieren und neu starten.

## Benutzung

### 1. Defektes Gerät vormerken
*Einstellungen → Geräte & Dienste → SwitchSwap → **Konfigurieren** → Gerät zum Tausch vormerken*

- Gerät auswählen
- **Gerät jetzt löschen** (Standard): Das Gerät wird aus der Integration (z. B. ZHA, Z-Wave, Zigbee2MQTT, sofern die Integration das Entfernen unterstützt) und aus Home Assistant gelöscht. Alle Einstellungen sind vorher gesichert.

### 2. Ersatzgerät anlernen
Das neue Gerät ganz normal anlernen bzw. integrieren.

### 3. Neues Gerät zuweisen
Sobald ein Tausch vorgemerkt ist, meldet SwitchSwap jedes neu angelernte Gerät unter **Einstellungen → Reparaturen**:

> *Neues Gerät erkannt: 0x00158d000a1b2c*

Dort klicken → „Ja, das ist ein Ersatzgerät" → altes Gerät wählen → Entitäten zuordnen → fertig.

Alternativ jederzeit über *SwitchSwap → Konfigurieren → Tausch abschließen*.

Bei der **Zuordnung** schlägt SwitchSwap automatisch passende Entitäten vor (gleicher Typ, Übersetzungsschlüssel, Geräteklasse, Name, unique_id-Muster, Einheit). Jede Zuordnung kann im Dropdown geändert oder auf „nicht übernehmen" gesetzt werden.

Nach dem Abschluss erscheint eine Benachrichtigung mit allen Details.

## Dienste (Aktionen)

| Dienst | Beschreibung |
|---|---|
| `switchswap.prepare_swap` | Gerät sichern (`device_id`) und optional löschen (`remove_device`) |
| `switchswap.complete_swap` | Tausch abschließen (`old_device_id`, `new_device_id`, optional `mapping`, `update_automations`) |
| `switchswap.cancel_swap` | Vorgemerkten Tausch verwerfen |
| `switchswap.list_pending` | Vorgemerkte Tausche als Antwort zurückgeben |

Beispiel:

```yaml
action: switchswap.complete_swap
data:
  old_device_id: 3f1c0a9b2d4e4f6a8b0c1d2e3f405162
  new_device_id: 9a8b7c6d5e4f30211234567890abcdef
  mapping:
    sensor.wohnzimmer_temperatur: sensor.0x00158d000a1b2c_temperature
    sensor.wohnzimmer_luftfeuchte: sensor.0x00158d000a1b2c_humidity
```

## Hinweise & Grenzen

- Ist der Name einer Entität nicht manuell vergeben und unterscheidet sich der Standardname des neuen Geräts, wird der alte Name fest übernommen.
- Belegt eine andere Entität bereits die alte Entitäts-ID, wird sie auf `<id>_old` umbenannt (steht in der Benachrichtigung).
- Neue Entitäten ohne Zuordnung bleiben unverändert; alte Entitäten ohne Zuordnung entfallen.
- Geräte-IDs werden nur in `automations.yaml` und `scripts.yaml` ersetzt – Automationen in Packages oder anderen YAML-Dateien bitte selbst prüfen.
- Für Energiezähler (`total_increasing`) erkennt Home Assistant den Neustart des neuen Zählers als Reset – die Statistik läuft korrekt weiter.

---

## English (short)

SwitchSwap lets you replace a broken device while keeping entity IDs, names, areas, labels, aliases, entity options, history/statistics and device-based automations.

1. *SwitchSwap → Configure → Mark a device for replacement* (optionally deletes it)
2. Pair the new device
3. Accept the **Repairs** notification "New device detected" (or *Configure → Complete a swap*), review the suggested entity mapping, done.

## Lizenz

MIT
