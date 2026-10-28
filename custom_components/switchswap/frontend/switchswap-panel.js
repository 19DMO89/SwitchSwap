/* SwitchSwap – Seitenleisten-Panel zum Tauschen von Geräten. */

const STRINGS = {
  de: {
    title: "SwitchSwap",
    pending: "Vorgemerkte Tausche",
    noPending: "Kein Tausch vorgemerkt.",
    since: "seit",
    entities: "Entitäten",
    removed: "Gerät gelöscht",
    stillPresent: "Gerät noch vorhanden",
    assign: "Neues Gerät zuweisen",
    discard: "Verwerfen",
    reallyDiscard: "Tausch wirklich verwerfen? Die gesicherten Daten gehen verloren.",
    yes: "Ja",
    no: "Nein",
    swapDevice: "Gerät tauschen",
    swapIntro: "Defektes Gerät auswählen. SwitchSwap sichert Entitäts-IDs, Namen, Bereiche, Labels, Aliase und Einstellungen.",
    search: "Gerät suchen …",
    selected: "Ausgewählt",
    removeNow: "Gerät jetzt aus Integration und Home Assistant löschen",
    prepare: "Zum Tausch vormerken",
    reallyPrepare: "Gerät jetzt sichern{remove}?",
    andRemove: " und löschen",
    prepared: "{device} wurde gesichert. Jetzt das Ersatzgerät anlernen und danach hier zuweisen.",
    back: "Zurück",
    chooseNew: "Ersatzgerät für {device} wählen",
    chooseNewHint: "Neueste Geräte stehen oben. Mit „neu“ markierte Geräte wurden nach dem Vormerken angelernt.",
    isNew: "neu",
    mapTitle: "Entitäten zuordnen",
    mapHint: "Die gewählte neue Entität übernimmt die alte Entitäts-ID, den Namen und alle Einstellungen.",
    oldEntity: "Alte Entität",
    newEntity: "Neue Entität",
    skip: "— nicht übernehmen —",
    updateAutomations: "Geräte-IDs in automations.yaml / scripts.yaml ersetzen (mit Backup)",
    complete: "Tausch abschließen",
    otherDevice: "Anderes Gerät wählen",
    duplicate: "Eine neue Entität ist mehrfach zugeordnet.",
    done: "Tausch abgeschlossen: {old} → {new}. {mapped} übernommen, {skipped} nicht zugeordnet.",
    noDevices: "Keine Geräte gefunden.",
    noEntities: "Das alte Gerät hatte keine Entitäten.",
    howTitle: "So funktioniert's",
    how1: "Defektes Gerät unten auswählen und vormerken – es wird gesichert und gelöscht.",
    how2: "Ersatzgerät ganz normal anlernen bzw. integrieren.",
    how3: "Hier „Neues Gerät zuweisen“ wählen (oder die Meldung unter Einstellungen → Reparaturen nutzen).",
    how4: "Entitäten prüfen und Tausch abschließen – Dashboards, Verlauf und Automationen laufen weiter.",
    error: "Fehler",
  },
  en: {
    title: "SwitchSwap",
    pending: "Pending swaps",
    noPending: "No swap pending.",
    since: "since",
    entities: "entities",
    removed: "device deleted",
    stillPresent: "device still present",
    assign: "Assign new device",
    discard: "Discard",
    reallyDiscard: "Really discard this swap? The saved data will be lost.",
    yes: "Yes",
    no: "No",
    swapDevice: "Replace a device",
    swapIntro: "Select the broken device. SwitchSwap saves entity IDs, names, areas, labels, aliases and settings.",
    search: "Search device …",
    selected: "Selected",
    removeNow: "Delete device from its integration and Home Assistant now",
    prepare: "Mark for replacement",
    reallyPrepare: "Save device now{remove}?",
    andRemove: " and delete it",
    prepared: "{device} was saved. Now pair the replacement and assign it here.",
    back: "Back",
    chooseNew: "Choose replacement for {device}",
    chooseNewHint: "Newest devices are listed first. Devices marked “new” were added after the swap was prepared.",
    isNew: "new",
    mapTitle: "Map entities",
    mapHint: "The selected new entity takes over the old entity ID, name and all settings.",
    oldEntity: "Old entity",
    newEntity: "New entity",
    skip: "— skip —",
    updateAutomations: "Replace device IDs in automations.yaml / scripts.yaml (with backup)",
    complete: "Complete swap",
    otherDevice: "Choose another device",
    duplicate: "A new entity is assigned more than once.",
    done: "Swap completed: {old} → {new}. {mapped} transferred, {skipped} not mapped.",
    noDevices: "No devices found.",
    noEntities: "The old device had no entities.",
    howTitle: "How it works",
    how1: "Select the broken device below and mark it – it is saved and deleted.",
    how2: "Pair or integrate the replacement as usual.",
    how3: "Choose “Assign new device” here (or use the notice under Settings → Repairs).",
    how4: "Review the entities and complete the swap – dashboards, history and automations keep working.",
    error: "Error",
  },
};

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

class SwitchSwapPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._s = {
      view: "home",
      devices: [],
      pending: [],
      search: "",
      newSearch: "",
      selected: null,
      remove: true,
      confirmPrepare: false,
      confirmCancel: null,
      assign: null,
      busy: false,
      msg: null,
    };
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._render();
      this._load();
      this._subscribe();
    } else {
      const menu = this.shadowRoot.querySelector("ha-menu-button");
      if (menu) menu.hass = hass;
    }
  }

  set narrow(narrow) {
    this._narrow = narrow;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = narrow;
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    if (this._hass) this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  // ------------------------------------------------------------ data

  _t(key, vars = {}) {
    const lang = (this._hass?.language || "en").startsWith("de") ? "de" : "en";
    let text = STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
    for (const [name, value] of Object.entries(vars)) text = text.replace(`{${name}}`, value);
    return text;
  }

  _ws(type, data = {}) {
    return this._hass.callWS({ type: `switchswap/${type}`, ...data });
  }

  async _subscribe() {
    if (this._unsub || this._subscribing) return;
    this._subscribing = true;
    try {
      this._unsub = await this._hass.connection.subscribeEvents(() => {
        clearTimeout(this._reloadTimer);
        this._reloadTimer = setTimeout(() => this._load(), 1500);
      }, "device_registry_updated");
    } catch (err) {
      // Ohne Live-Aktualisierung weiterarbeiten
    }
    this._subscribing = false;
  }

  async _load() {
    try {
      const [devices, pending] = await Promise.all([this._ws("devices"), this._ws("pending")]);
      this._s.devices = devices.devices;
      this._s.pending = pending.pending;
    } catch (err) {
      this._s.msg = { type: "error", text: err.message || String(err) };
    }
    if (this._s.view === "home") this._render();
    else this._renderList("newlist");
  }

  _set(patch) {
    Object.assign(this._s, patch);
    this._render();
  }

  _error(err) {
    this._set({ busy: false, msg: { type: "error", text: `${this._t("error")}: ${err.message || err.code || err}` } });
  }

  _fmtDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString(this._hass.language, { dateStyle: "short", timeStyle: "short" });
    } catch (err) {
      return iso.slice(0, 16).replace("T", " ");
    }
  }

  // ------------------------------------------------------------ events

  async _onClick(ev) {
    const el = ev.target.closest("[data-action]");
    if (!el || this._s.busy) return;
    const { action, id } = el.dataset;
    const s = this._s;

    switch (action) {
      case "select":
        this._set({ selected: id, confirmPrepare: false, msg: null });
        break;
      case "prepare":
        this._set({ confirmPrepare: true });
        break;
      case "prepare-no":
        this._set({ confirmPrepare: false });
        break;
      case "prepare-yes": {
        this._set({ busy: true });
        try {
          const res = await this._ws("prepare", { device_id: s.selected, remove_device: s.remove });
          this._s.selected = null;
          this._s.confirmPrepare = false;
          this._s.busy = false;
          this._s.msg = { type: "success", text: this._t("prepared", { device: res.label }) };
          await this._load();
        } catch (err) {
          this._error(err);
        }
        break;
      }
      case "cancel":
        this._set({ confirmCancel: id });
        break;
      case "cancel-no":
        this._set({ confirmCancel: null });
        break;
      case "cancel-yes":
        this._set({ busy: true });
        try {
          await this._ws("cancel", { swap_id: id });
          this._s.busy = false;
          this._s.confirmCancel = null;
          await this._load();
        } catch (err) {
          this._error(err);
        }
        break;
      case "assign":
        this._set({
          view: "assign",
          assign: { swapId: id, newDeviceId: null, ctx: null, mapping: {}, updateAutomations: true },
          newSearch: "",
          msg: null,
        });
        break;
      case "back":
        this._set({ view: "home", assign: null, msg: null });
        this._load();
        break;
      case "pick-new":
        this._set({ busy: true, msg: null });
        try {
          const ctx = await this._ws("suggest", { swap_id: s.assign.swapId, new_device_id: id });
          const mapping = {};
          for (const old of ctx.old_entities) mapping[old.entity_id] = ctx.suggestion[old.entity_id] || "";
          this._set({ busy: false, assign: { ...s.assign, newDeviceId: id, ctx, mapping } });
        } catch (err) {
          this._error(err);
        }
        break;
      case "other-device":
        this._set({ assign: { ...s.assign, newDeviceId: null, ctx: null, mapping: {} } });
        break;
      case "complete": {
        if (this._hasDuplicates()) return;
        this._set({ busy: true });
        const mapping = {};
        for (const [old, value] of Object.entries(s.assign.mapping)) mapping[old] = value || null;
        try {
          const res = await this._ws("complete", {
            swap_id: s.assign.swapId,
            new_device_id: s.assign.newDeviceId,
            mapping,
            update_automations: s.assign.updateAutomations,
          });
          this._s.view = "home";
          this._s.assign = null;
          this._s.busy = false;
          this._s.msg = {
            type: res.errors.length ? "warning" : "success",
            text:
              this._t("done", {
                old: res.old_device,
                new: res.new_device,
                mapped: res.mapped.length,
                skipped: res.skipped.length,
              }) + (res.errors.length ? ` ${res.errors.join(" · ")}` : ""),
          };
          await this._load();
        } catch (err) {
          this._error(err);
        }
        break;
      }
      case "dismiss":
        this._set({ msg: null });
        break;
    }
  }

  _onInput(ev) {
    const el = ev.target;
    if (el.id === "search") {
      this._s.search = el.value;
      this._renderList("devlist");
    } else if (el.id === "newsearch") {
      this._s.newSearch = el.value;
      this._renderList("newlist");
    }
  }

  _onChange(ev) {
    const el = ev.target;
    if (el.id === "remove") {
      this._s.remove = el.checked;
      this._s.confirmPrepare = false;
      this._render();
    } else if (el.id === "automations") {
      this._s.assign.updateAutomations = el.checked;
    } else if (el.dataset.old) {
      this._s.assign.mapping[el.dataset.old] = el.value;
      this._render();
    }
  }

  _hasDuplicates() {
    const values = Object.values(this._s.assign?.mapping || {}).filter(Boolean);
    return new Set(values).size !== values.length;
  }

  // ------------------------------------------------------------ rendering

  _filtered(listId) {
    const s = this._s;
    const query = (listId === "devlist" ? s.search : s.newSearch).trim().toLowerCase();
    let devices = s.devices.filter((d) => !d.pending);
    if (query) {
      devices = devices.filter((d) =>
        [d.label, d.manufacturer, d.model, d.area, ...(d.integrations || [])]
          .join(" ")
          .toLowerCase()
          .includes(query)
      );
    }
    if (listId === "newlist") {
      devices = devices.filter((d) => d.id !== s.assign?.swapId);
      devices.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    } else {
      devices.sort((a, b) => a.label.localeCompare(b.label));
    }
    return devices;
  }

  _deviceItem(d, action, selected, isNew) {
    const sub = [d.manufacturer, d.model].filter(Boolean).join(" · ");
    const meta = [d.area, (d.integrations || []).join(", "), `${d.entities} ${this._t("entities")}`]
      .filter(Boolean)
      .join(" · ");
    return `
      <button class="item ${selected ? "selected" : ""}" data-action="${action}" data-id="${esc(d.id)}">
        <div class="item-main">
          <span class="item-title">${esc(d.label)}</span>
          ${isNew ? `<span class="badge">${this._t("isNew")}</span>` : ""}
          ${sub ? `<span class="muted">${esc(sub)}</span>` : ""}
        </div>
        <div class="muted small">${esc(meta)}${
          action === "pick-new" && d.created_at ? ` · ${esc(this._fmtDate(d.created_at))}` : ""
        }</div>
      </button>`;
  }

  _renderList(listId) {
    const el = this.shadowRoot.getElementById(listId);
    if (!el) return;
    const s = this._s;
    const devices = this._filtered(listId);
    if (!devices.length) {
      el.innerHTML = `<p class="muted pad">${this._t("noDevices")}</p>`;
      return;
    }
    const swapCreated = s.pending.find((p) => p.old_device_id === s.assign?.swapId)?.created || "";
    el.innerHTML = devices
      .map((d) =>
        listId === "devlist"
          ? this._deviceItem(d, "select", d.id === s.selected, false)
          : this._deviceItem(d, "pick-new", false, d.created_at && swapCreated && d.created_at > swapCreated)
      )
      .join("");
  }

  _renderMsg() {
    const m = this._s.msg;
    if (!m) return "";
    return `<div class="msg ${m.type}"><span>${esc(m.text)}</span><button class="icon" data-action="dismiss">✕</button></div>`;
  }

  _renderPending() {
    const s = this._s;
    if (!s.pending.length) return `<p class="muted">${this._t("noPending")}</p>`;
    return s.pending
      .map((p) => {
        const sub = [p.manufacturer, p.model].filter(Boolean).join(" · ");
        const actions =
          s.confirmCancel === p.old_device_id
            ? `<span class="small">${this._t("reallyDiscard")}</span>
               <button class="danger" data-action="cancel-yes" data-id="${esc(p.old_device_id)}">${this._t("yes")}</button>
               <button class="flat" data-action="cancel-no">${this._t("no")}</button>`
            : `<button class="primary" data-action="assign" data-id="${esc(p.old_device_id)}">${this._t("assign")}</button>
               <button class="flat" data-action="cancel" data-id="${esc(p.old_device_id)}">${this._t("discard")}</button>`;
        return `
          <div class="pending">
            <div class="pending-head">
              <div>
                <div class="item-title">${esc(p.device)}</div>
                <div class="muted small">${esc(sub)}${sub ? " · " : ""}${this._t("since")} ${esc(this._fmtDate(p.created))}
                  · ${p.entities.length} ${this._t("entities")} · ${p.removed ? this._t("removed") : this._t("stillPresent")}</div>
              </div>
              <div class="actions">${actions}</div>
            </div>
            <details>
              <summary>${p.entities.length} ${this._t("entities")}</summary>
              <ul>${p.entities
                .map((e) => `<li><code>${esc(e.entity_id)}</code>${e.name ? ` – ${esc(e.name)}` : ""}</li>`)
                .join("")}</ul>
            </details>
          </div>`;
      })
      .join("");
  }

  _renderPrepareBar() {
    const s = this._s;
    const device = s.devices.find((d) => d.id === s.selected);
    if (!device) return "";
    const buttons = s.confirmPrepare
      ? `<span>${this._t("reallyPrepare", { remove: s.remove ? this._t("andRemove") : "" })}</span>
         <button class="${s.remove ? "danger" : "primary"}" data-action="prepare-yes">${this._t("yes")}</button>
         <button class="flat" data-action="prepare-no">${this._t("no")}</button>`
      : `<button class="primary" data-action="prepare">${this._t("prepare")}</button>`;
    return `
      <div class="prepare-bar">
        <div><span class="muted">${this._t("selected")}:</span> <b>${esc(device.label)}</b></div>
        <label class="check"><input type="checkbox" id="remove" ${s.remove ? "checked" : ""}> ${this._t("removeNow")}</label>
        <div class="actions">${buttons}</div>
      </div>`;
  }

  _renderHome() {
    return `
      ${this._renderMsg()}
      <section class="card">
        <h2>${this._t("pending")}</h2>
        ${this._renderPending()}
      </section>
      <section class="card">
        <h2>${this._t("swapDevice")}</h2>
        <p class="muted">${this._t("swapIntro")}</p>
        <input class="search" id="search" type="search" placeholder="${this._t("search")}" value="${esc(this._s.search)}">
        <div class="list" id="devlist"></div>
        ${this._renderPrepareBar()}
      </section>
      <section class="card">
        <h2>${this._t("howTitle")}</h2>
        <ol class="how">
          <li>${this._t("how1")}</li><li>${this._t("how2")}</li><li>${this._t("how3")}</li><li>${this._t("how4")}</li>
        </ol>
      </section>`;
  }

  _renderMapping() {
    const a = this._s.assign;
    const ctx = a.ctx;
    const counts = {};
    for (const value of Object.values(a.mapping)) if (value) counts[value] = (counts[value] || 0) + 1;
    const rows = ctx.old_entities
      .map((old) => {
        const value = a.mapping[old.entity_id] || "";
        const options = ctx.new_entities
          .filter((n) => n.domain === old.domain)
          .map(
            (n) =>
              `<option value="${esc(n.entity_id)}" ${n.entity_id === value ? "selected" : ""}>${esc(n.entity_id)}${
                n.name ? ` (${esc(n.name)})` : ""
              }</option>`
          )
          .join("");
        return `
          <tr class="${value && counts[value] > 1 ? "dup" : ""}">
            <td><code>${esc(old.entity_id)}</code>${old.name ? `<div class="muted small">${esc(old.name)}</div>` : ""}</td>
            <td class="arrow">→</td>
            <td><select data-old="${esc(old.entity_id)}">
              <option value="" ${value ? "" : "selected"}>${this._t("skip")}</option>${options}
            </select></td>
          </tr>`;
      })
      .join("");
    const dup = this._hasDuplicates();
    return `
      <section class="card">
        <h2>${this._t("mapTitle")}</h2>
        <p><b>${esc(ctx.old_device)}</b> → <b>${esc(ctx.new_device)}</b></p>
        <p class="muted">${this._t("mapHint")}</p>
        ${
          ctx.old_entities.length
            ? `<div class="table-wrap"><table>
                <thead><tr><th>${this._t("oldEntity")}</th><th></th><th>${this._t("newEntity")}</th></tr></thead>
                <tbody>${rows}</tbody></table></div>`
            : `<p class="muted">${this._t("noEntities")}</p>`
        }
        ${dup ? `<div class="msg error"><span>${this._t("duplicate")}</span></div>` : ""}
        <label class="check"><input type="checkbox" id="automations" ${a.updateAutomations ? "checked" : ""}> ${this._t("updateAutomations")}</label>
        <div class="actions end">
          <button class="flat" data-action="other-device">${this._t("otherDevice")}</button>
          <button class="primary" data-action="complete" ${dup ? "disabled" : ""}>${this._t("complete")}</button>
        </div>
      </section>`;
  }

  _renderAssign() {
    const a = this._s.assign;
    const pending = this._s.pending.find((p) => p.old_device_id === a.swapId);
    if (a.ctx) return this._renderMsg() + this._renderMapping();
    return `
      ${this._renderMsg()}
      <section class="card">
        <h2>${this._t("chooseNew", { device: esc(pending?.device || "") })}</h2>
        <p class="muted">${this._t("chooseNewHint")}</p>
        <input class="search" id="newsearch" type="search" placeholder="${this._t("search")}" value="${esc(this._s.newSearch)}">
        <div class="list" id="newlist"></div>
      </section>`;
  }

  _render() {
    const s = this._s;
    const assign = s.view === "assign" && s.assign;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        ${
          assign
            ? `<button class="icon back" data-action="back" title="${this._t("back")}">←</button>`
            : `<ha-menu-button></ha-menu-button>`
        }
        <div class="title">${this._t("title")}</div>
        ${s.busy ? `<div class="spinner"></div>` : ""}
      </div>
      <div class="content ${s.busy ? "busy" : ""}">
        ${assign ? this._renderAssign() : this._renderHome()}
      </div>`;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
    this._renderList(assign ? "newlist" : "devlist");
  }
}

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  .toolbar {
    display: flex; align-items: center; gap: 8px;
    height: var(--header-height, 56px); padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, #fff);
    border-bottom: var(--app-header-border-bottom, none);
    position: sticky; top: 0; z-index: 2;
  }
  .title { font-size: 20px; flex: 1; margin-left: 8px; }
  .content { max-width: 960px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
  .content.busy { opacity: .6; pointer-events: none; }
  .card {
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    border: 1px solid var(--divider-color);
    box-shadow: var(--ha-card-box-shadow, none);
    padding: 16px;
  }
  h2 { margin: 0 0 12px; font-size: 18px; font-weight: 500; }
  p { margin: 0 0 12px; }
  .muted { color: var(--secondary-text-color); }
  .small { font-size: 13px; }
  .pad { padding: 12px; }
  code { font-size: 13px; background: var(--secondary-background-color); padding: 1px 4px; border-radius: 4px; word-break: break-all; }
  button {
    font: inherit; cursor: pointer; border-radius: 8px; padding: 8px 14px;
    border: 1px solid transparent; background: none; color: inherit;
  }
  button:disabled { opacity: .5; cursor: not-allowed; }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  button.danger { background: var(--error-color, #db4437); color: #fff; }
  button.flat { color: var(--primary-color); border-color: var(--divider-color); }
  button.icon { padding: 6px 10px; font-size: 18px; color: inherit; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .actions.end { justify-content: flex-end; margin-top: 12px; }
  .search {
    width: 100%; box-sizing: border-box; padding: 10px 12px; margin-bottom: 8px;
    font: inherit; color: inherit; background: var(--secondary-background-color);
    border: 1px solid var(--divider-color); border-radius: 8px;
  }
  .list { max-height: 380px; overflow-y: auto; border: 1px solid var(--divider-color); border-radius: 8px; }
  .item {
    display: block; width: 100%; text-align: left; border-radius: 0;
    border-bottom: 1px solid var(--divider-color); padding: 10px 12px;
  }
  .item:last-child { border-bottom: none; }
  .item:hover { background: var(--secondary-background-color); }
  .item.selected { background: rgba(var(--rgb-primary-color, 3, 169, 244), .15); box-shadow: inset 3px 0 0 var(--primary-color); }
  .item-main { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
  .item-title { font-weight: 500; }
  .badge { background: var(--success-color, #43a047); color: #fff; font-size: 11px; padding: 1px 6px; border-radius: 8px; }
  .prepare-bar {
    margin-top: 12px; padding: 12px; border-radius: 8px;
    background: var(--secondary-background-color); display: flex; flex-direction: column; gap: 10px;
  }
  .check { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
  .pending { border: 1px solid var(--divider-color); border-radius: 8px; padding: 12px; margin-bottom: 10px; }
  .pending-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; }
  details { margin-top: 8px; }
  summary { cursor: pointer; color: var(--secondary-text-color); font-size: 13px; }
  ul { margin: 6px 0 0; padding-left: 20px; }
  li { margin: 3px 0; }
  .how { margin: 0; padding-left: 20px; }
  .msg {
    display: flex; justify-content: space-between; align-items: center; gap: 8px;
    padding: 10px 12px; border-radius: 8px; margin: 8px 0;
  }
  .msg.success { background: rgba(67, 160, 71, .15); border: 1px solid var(--success-color, #43a047); }
  .msg.warning { background: rgba(255, 166, 0, .15); border: 1px solid var(--warning-color, #ffa600); }
  .msg.error { background: rgba(219, 68, 55, .15); border: 1px solid var(--error-color, #db4437); }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-weight: 500; color: var(--secondary-text-color); padding: 6px; font-size: 13px; }
  td { padding: 8px 6px; border-top: 1px solid var(--divider-color); vertical-align: middle; }
  td.arrow { color: var(--secondary-text-color); width: 20px; }
  tr.dup td { background: rgba(219, 68, 55, .08); }
  select {
    width: 100%; padding: 8px; font: inherit; color: inherit; border-radius: 8px;
    background: var(--secondary-background-color); border: 1px solid var(--divider-color);
  }
  .spinner {
    width: 20px; height: 20px; border-radius: 50%;
    border: 3px solid rgba(255, 255, 255, .3); border-top-color: currentColor;
    animation: spin 1s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 600px) {
    .content { padding: 8px; }
    .pending-head { flex-direction: column; }
  }
`;

if (!customElements.get("switchswap-panel")) customElements.define("switchswap-panel", SwitchSwapPanel);
