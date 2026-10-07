// The "Muziek" panel: library (left), queue (right), transport on top.
// Plain web component, no build step; the logic lives in ./lib (tested with node).

import { addMessage, browseMessage, itemActions, needsSigning, sortedChildren, sourceNote } from "./lib/browse-actions.js";
import { languageOf, translate } from "./lib/i18n.js";
import { rememberPlayer, restorePlayer } from "./lib/player-memory.js";
import { listPlayers, playersKey } from "./lib/players.js";
import { limiter } from "./lib/limiter.js";
import { applyUpdate, errorText, idsKey, newError, queueRows, rowTitle } from "./lib/queue-view.js";
import { dropIndex, rowAt } from "./lib/reorder.js";
import {
  nowPlaying,
  playPauseAction,
  queueButtons,
  repeatButton,
  shuffleButton,
  volumeOf,
} from "./lib/transport.js";

const STYLE = `
  :host { display: block; height: 100%; background: var(--primary-background-color); color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  * { box-sizing: border-box; }
  button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; border-radius: 50%;
    padding: 6px; display: inline-flex; align-items: center; justify-content: center; }
  button:hover:not(:disabled) { background: rgba(127, 127, 127, 0.15); }
  button:disabled { opacity: 0.35; cursor: default; }
  .page { display: flex; flex-direction: column; height: 100vh; height: 100dvh; }
  header { display: flex; align-items: center; gap: 8px; padding: 0 12px; min-height: 56px;
    background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, white); }
  header h1 { font-size: 20px; font-weight: 400; margin: 0 8px 0 0; flex: 1; white-space: nowrap; }
  header select { font: inherit; padding: 6px 8px; border-radius: 6px; max-width: 55vw;
    border: 1px solid rgba(255, 255, 255, 0.5); background: var(--card-background-color); color: var(--primary-text-color); }
  .menu { display: none; }
  .narrow .menu { display: inline-flex; }
  .now { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: var(--card-background-color);
    border-bottom: 1px solid var(--divider-color); }
  .now img, .now .art { width: 48px; height: 48px; border-radius: 4px; object-fit: cover; flex: none;
    background: var(--secondary-background-color); display: flex; align-items: center; justify-content: center; }
  .now .info { flex: 1; min-width: 0; }
  .now .t { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .now .s { color: var(--secondary-text-color); font-size: 0.9em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .now .main { background: var(--primary-color); color: var(--text-primary-color, white); padding: 10px; }
  .now .mode { color: var(--secondary-text-color); }
  .now .mode.on { color: var(--primary-color); }
  .now input[type=range] { width: 120px; accent-color: var(--primary-color); }
  .narrow .now { flex-wrap: wrap; row-gap: 4px; }
  .narrow .now .info { flex: 1 1 calc(100% - 64px); }
  .narrow .now input[type=range] { flex: 1; width: auto; }
  .tabs { display: none; }
  .narrow .tabs { display: flex; border-bottom: 1px solid var(--divider-color); background: var(--card-background-color); }
  .tabs button { flex: 1; border-radius: 0; padding: 12px; border-bottom: 2px solid transparent; }
  .tabs button.active { border-bottom-color: var(--primary-color); color: var(--primary-color); }
  .columns { flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px; min-height: 0; }
  .narrow .columns { grid-template-columns: 1fr; padding: 0; }
  .narrow .columns > section { display: none; border-radius: 0; }
  .narrow.tab-library .library, .narrow.tab-queue .queue { display: flex; }
  section { display: flex; flex-direction: column; min-height: 0; background: var(--card-background-color);
    border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color); overflow: hidden; }
  section > .head { display: flex; align-items: center; gap: 4px; padding: 6px 8px; min-height: 48px;
    border-bottom: 1px solid var(--divider-color); }
  section > .head .label { flex: 1; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-left: 4px; }
  section > .head .count { color: var(--secondary-text-color); font-size: 0.9em; }
  ul { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }
  li { display: flex; align-items: center; gap: 8px; padding: 4px 8px; min-height: 52px; border-bottom: 1px solid var(--divider-color); }
  li .thumb { width: 40px; height: 40px; border-radius: 4px; object-fit: cover; flex: none; display: flex;
    align-items: center; justify-content: center; color: var(--secondary-text-color); background: var(--secondary-background-color); }
  li .title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: default; }
  li button.title { display: block; text-align: left; border-radius: 4px; padding: 4px; font: inherit; }
  li .title.link { cursor: pointer; }
  button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
  li .title.link:hover { text-decoration: underline; }
  li.current { background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.15); }
  li.current .title { font-weight: 600; color: var(--primary-color); }
  li.next .title::after { content: " ·"; color: var(--secondary-text-color); }
  li.drop-before { box-shadow: inset 0 3px 0 var(--primary-color); }
  li.drop-after { box-shadow: inset 0 -3px 0 var(--primary-color); }
  li.dragging { opacity: 0.5; }
  .handle { cursor: grab; touch-action: none; color: var(--secondary-text-color); }
  .actions { display: flex; flex: none; }
  .empty, .note { padding: 16px; color: var(--secondary-text-color); }
  .note { padding: 8px 12px; font-size: 0.9em; border-bottom: 1px solid var(--divider-color); }
  .toast { position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%); max-width: 90vw; padding: 10px 16px;
    border-radius: 8px; background: var(--primary-text-color); color: var(--primary-background-color); opacity: 0;
    transition: opacity 0.2s; pointer-events: none; z-index: 10; }
  .toast.show { opacity: 0.92; }
`;

/** Create an element: h("button", {class: "x", onclick: f}, child, …). */
function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (key in el && key !== "list") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) el.append(child);
  }
  return el;
}

const icon = (name) => h("ha-icon", { icon: name });

class MediaQueuePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._narrow = false;
    this._language = null;
    this._players = [];
    this._playersKey = null;
    this._entityId = null;
    this._snapshot = null;
    this._unsubscribe = null;
    this._stack = [];
    this._listing = null;
    this._tab = "library";
    this._stateObj = undefined;
    this._idsKey = null;
    this._signed = new Map();
    this._toastTimer = null;
    this._lastErrorAt = null;
    this._dragging = false;
    this._retryTimer = null;
    this._observer = null;
    this._signLimit = limiter(4);
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    this._narrow = Boolean(narrow);
    this._root?.classList.toggle("narrow", this._narrow);
  }

  set panel(_panel) {}

  set route(_route) {}

  disconnectedCallback() {
    clearTimeout(this._retryTimer);
    this._stopSubscription();
  }

  connectedCallback() {
    if (this._hass && this._entityId && !this._unsubscribe) this._subscribe();
  }

  t(key, params) {
    return translate(this._language, key, params);
  }

  // ---------------------------------------------------------------- updates

  _update() {
    const hass = this._hass;
    const language = languageOf(hass);
    if (language !== this._language) {
      this._language = language;
      this._playersKey = null;
      this._idsKey = null;
      this._stateObj = undefined;
      this._build();
    }
    const players = listPlayers(hass.states);
    const key = playersKey(players);
    if (key !== this._playersKey) {
      this._players = players;
      this._playersKey = key;
      this._renderPicker();
      const wanted = players.some((p) => p.entityId === this._entityId)
        ? this._entityId
        : restorePlayer(window.localStorage, players);
      if (wanted !== this._entityId) this._select(wanted);
    }
    const stateObj = this._entityId ? hass.states[this._entityId] : null;
    if (stateObj !== this._stateObj) {
      this._stateObj = stateObj;
      this._renderTransport();
    }
  }

  _build() {
    const root = h("div", { class: `page tab-${this._tab}${this._narrow ? " narrow" : ""}` });
    this._root = root;
    this._picker = h("select", { "aria-label": this.t("player"), onchange: (e) => this._select(e.target.value, true) });
    this._now = h("div", { class: "now" });
    this._libraryHead = h("div", { class: "head" });
    this._libraryNote = h("div", { class: "note", hidden: true }, this.t("cannot_browse"));
    this._libraryList = h("ul");
    this._queueCount = h("span", { class: "count" });
    this._clearButton = h(
      "button",
      { title: this.t("clear"), "aria-label": this.t("clear"), onclick: () => this._call({ type: "media_queue/clear" }) },
      icon("mdi:playlist-remove"),
    );
    this._queueNote = h("div", { class: "note", hidden: true }, this.t("shuffled"));
    this._queueList = h("ul");
    this._toast = h("div", { class: "toast", role: "status" });
    this._tabButtons = {
      library: h("button", { role: "tab", onclick: () => this._showTab("library") }, this.t("library")),
      queue: h("button", { role: "tab", onclick: () => this._showTab("queue") }, this.t("queue")),
    };
    root.append(
      h(
        "header",
        {},
        h(
          "button",
          {
            class: "menu",
            "aria-label": "Menu",
            onclick: () => this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true })),
          },
          icon("mdi:menu"),
        ),
        h("h1", {}, this.t("title")),
        this._picker,
      ),
      this._now,
      h("nav", { class: "tabs", role: "tablist" }, this._tabButtons.library, this._tabButtons.queue),
      h(
        "div",
        { class: "columns" },
        h("section", { class: "library" }, this._libraryHead, this._libraryNote, this._libraryList),
        h(
          "section",
          { class: "queue" },
          h("div", { class: "head" }, h("span", { class: "label" }, this.t("queue")), this._queueCount, this._clearButton),
          this._queueNote,
          this._queueList,
        ),
      ),
      this._toast,
    );
    this.shadowRoot.replaceChildren(h("style", {}, STYLE), root);
    this._showTab(this._tab);
    this._renderLibrary();
    this._renderQueue();
  }

  _showTab(tab) {
    this._tab = tab;
    this._root.classList.toggle("tab-library", tab === "library");
    this._root.classList.toggle("tab-queue", tab === "queue");
    for (const [name, button] of Object.entries(this._tabButtons)) {
      button.classList.toggle("active", name === tab);
      button.setAttribute("aria-selected", String(name === tab));
    }
  }

  // ----------------------------------------------------------------- player

  _renderPicker() {
    if (!this._players.length) {
      this._picker.replaceChildren(h("option", { value: "" }, this.t("no_players")));
      this._picker.disabled = true;
      return;
    }
    this._picker.disabled = false;
    this._picker.replaceChildren(
      ...this._players.map((p) => h("option", { value: p.entityId, selected: p.entityId === this._entityId }, p.name)),
    );
    this._picker.value = this._entityId ?? "";
  }

  _player() {
    return this._players.find((p) => p.entityId === this._entityId) ?? null;
  }

  _select(entityId, remember = false) {
    if (remember) rememberPlayer(window.localStorage, entityId);
    this._entityId = entityId || null;
    if (this._picker && this._entityId) this._picker.value = this._entityId;
    this._snapshot = null;
    this._idsKey = null;
    this._stack = [];
    this._stateObj = undefined;
    this._subscribe();
    this._openNode(null);
    if (this._hass) this._update();
  }

  _stopSubscription() {
    const unsubscribe = this._unsubscribe;
    this._unsubscribe = null;
    if (unsubscribe) unsubscribe.then((stop) => stop()).catch(() => {});
  }

  _subscribe() {
    this._stopSubscription();
    this._renderQueue();
    if (!this._entityId) return;
    const entityId = this._entityId;
    this._unsubscribe = this._hass.connection.subscribeMessage(
      (snapshot) => {
        if (snapshot.entity_id !== this._entityId) return;
        if (snapshot.closed) {
          // The integration reloaded: subscribe again shortly.
          this._unsubscribe = null;
          this._retry(2000);
          return;
        }
        const merged = applyUpdate(this._snapshot, snapshot);
        if (!merged) return; // a playback update before the first snapshot
        const error = newError(this._lastErrorAt, merged, this._snapshot === null);
        this._lastErrorAt = merged.last_error?.at ?? null;
        if (error) this._notify(errorText((key, params) => this.t(key, params), error));
        this._snapshot = merged;
        this._renderQueue();
        this._renderTransport();
      },
      { type: "media_queue/subscribe", entity_id: entityId },
    );
    const pending = this._unsubscribe;
    pending.catch((err) => {
      if (this._unsubscribe !== pending) return; // another player was chosen meanwhile
      this._notify(this.t("error", { message: err.message ?? err.code }));
      this._unsubscribe = null;
      this._retry(5000);
    });
  }

  _retry(delay) {
    clearTimeout(this._retryTimer);
    this._retryTimer = setTimeout(() => {
      if (this.isConnected && this._entityId && !this._unsubscribe) this._subscribe();
    }, delay);
  }

  // ---------------------------------------------------------------- library

  async _openNode(node, back = false) {
    const player = this._player();
    if (!player) {
      this._listing = null;
      this._renderLibrary();
      return;
    }
    this._listing = "loading";
    this._renderLibrary();
    try {
      const result = await this._hass.callWS(browseMessage(player.entityId, player.canBrowse, node));
      if (player.entityId !== this._entityId) return;
      if (!back && node) this._stack.push(node);
      if (!node) this._stack = [];
      this._listing = result;
    } catch (err) {
      this._listing = null;
      this._notify(this.t("error", { message: err.message ?? err.code }));
    }
    this._renderLibrary();
  }

  _back() {
    this._stack.pop();
    const parent = this._stack[this._stack.length - 1] ?? null;
    this._openNode(parent, true);
  }

  _renderLibrary() {
    if (!this._libraryList) return;
    const player = this._player();
    const listing = this._listing;
    const node = this._stack[this._stack.length - 1] ?? null;
    const note = !player
      ? null
      : !player.canBrowse
        ? "cannot_browse"
        : sourceNote(this._hass?.entities?.[player.entityId], node);
    this._libraryNote.hidden = !note;
    this._libraryNote.textContent = note ? this.t(note) : "";
    const title = listing && listing !== "loading" ? listing.title : this.t("library");
    this._libraryHead.replaceChildren(
      h(
        "button",
        { title: this.t("back"), "aria-label": this.t("back"), disabled: this._stack.length === 0, onclick: () => this._back() },
        icon("mdi:arrow-left"),
      ),
      h("span", { class: "label" }, title),
    );
    if (listing === "loading") {
      this._libraryList.replaceChildren(h("li", { class: "empty" }, this.t("loading")));
      return;
    }
    const children = sortedChildren(listing, listing?.children ?? []);
    if (!children.length) {
      this._libraryList.replaceChildren(h("li", { class: "empty" }, this.t("empty_folder")));
      return;
    }
    this._libraryList.replaceChildren(...children.map((item) => this._libraryRow(item)));
  }

  _libraryRow(item) {
    const actions = itemActions(item);
    const button = (mode, iconName, label) =>
      h(
        "button",
        { title: label, "aria-label": `${label}: ${item.title}`, onclick: () => this._add(item, mode) },
        icon(iconName),
      );
    return h(
      "li",
      {},
      this._thumb(item.thumbnail, item.can_expand ? "mdi:folder-music" : "mdi:music-note"),
      actions.open
        ? h(
            "button",
            {
              class: "title link",
              title: `${this.t("open")}: ${item.title}`,
              onclick: () => this._openNode(item),
            },
            item.title,
          )
        : h("span", { class: "title", title: item.title }, item.title),
      h(
        "span",
        { class: "actions" },
        actions.play && button("replace", "mdi:play", this.t("play")),
        actions.next && button("next", "mdi:skip-next", this.t("play_next")),
        actions.add && button("add", "mdi:playlist-plus", this.t("add")),
      ),
    );
  }

  async _add(item, mode) {
    try {
      const result = await this._hass.callWS(addMessage(this._entityId, item, mode));
      this._notify(
        result.truncated ? this.t("truncated", { limit: result.limit }) : this.t("added", { count: result.added }),
      );
    } catch (err) {
      this._notify(this.t("error", { message: err.message ?? err.code }));
    }
  }

  _thumb(url, fallbackIcon) {
    if (!url) return h("span", { class: "thumb" }, icon(fallbackIcon));
    const img = h("img", {
      class: "thumb",
      alt: "",
      loading: "lazy",
      onerror: () => img.replaceWith(h("span", { class: "thumb" }, icon(fallbackIcon))),
    });
    if (!needsSigning(url)) {
      img.src = url;
      return img;
    }
    // Sign only what scrolls into view, a few requests at a time.
    img.dataset.src = url;
    this._observer ??= new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        this._observer.unobserve(entry.target);
        this._sign(entry.target.dataset.src).then((src) => {
          entry.target.src = src;
        });
      }
    });
    this._observer.observe(img);
    return img;
  }

  async _sign(url) {
    if (!needsSigning(url)) return url;
    if (!this._signed.has(url)) {
      this._signed.set(
        url,
        this._signLimit(() => this._hass.callWS({ type: "auth/sign_path", path: url, expires: 3600 }))
          .then((result) => result.path)
          .catch(() => url),
      );
    }
    return this._signed.get(url);
  }

  // ------------------------------------------------------------------ queue

  _renderQueue() {
    if (!this._queueList) return;
    const rows = queueRows(this._snapshot);
    this._queueCount.textContent = this.t("items", { count: rows.length });
    this._clearButton.disabled = rows.length === 0;
    this._queueNote.hidden = !(this._snapshot?.shuffle && rows.length);
    if (this._dragging) return;
    const key = idsKey(rows);
    if (key === this._idsKey && rows.length) {
      // Same items in the same order: only move the current/next markers.
      [...this._queueList.children].forEach((li, index) => {
        li.classList.toggle("current", rows[index].current);
        li.classList.toggle("next", rows[index].next);
      });
      return;
    }
    this._idsKey = key;
    if (!rows.length) {
      this._queueList.replaceChildren(h("li", { class: "empty" }, this.t("empty_queue")));
      return;
    }
    this._queueList.replaceChildren(
      ...rows.map((row) =>
        h(
          "li",
          { class: [row.current && "current", row.next && "next"].filter(Boolean).join(" ") },
          h(
            "span",
            {
              class: "handle",
              title: this.t("move"),
              "aria-label": this.t("move"),
              onpointerdown: (e) => this._startDrag(e, row.index, row.id),
            },
            icon("mdi:drag"),
          ),
          this._thumb(row.thumbnail, "mdi:music-note"),
          h(
            "button",
            {
              class: "title link",
              title: rowTitle(this.t("play"), row),
              "aria-label": `${this.t("play")}: ${row.label}`,
              onclick: () => this._call({ type: "media_queue/play_index", item_id: row.id }),
            },
            row.label,
          ),
          h(
            "button",
            {
              title: this.t("remove"),
              "aria-label": `${this.t("remove")}: ${row.label}`,
              onclick: () => this._call({ type: "media_queue/remove", item_id: row.id }),
            },
            icon("mdi:close"),
          ),
        ),
      ),
    );
  }

  _startDrag(event, from, itemId) {
    event.preventDefault();
    this._dragging = true; // updates wait until the drop, the rows stay put
    const handle = event.currentTarget;
    try {
      handle.setPointerCapture(event.pointerId); // keep the moves while outside the handle
    } catch {
      // the pointer is already gone; the drop still works on the handle
    }
    const rows = [...this._queueList.children];
    const boxes = rows.map((row) => row.getBoundingClientRect());
    rows[from].classList.add("dragging");
    let target = null;
    const clear = () => rows.forEach((row) => row.classList.remove("drop-before", "drop-after"));
    const move = (e) => {
      clear();
      target = rowAt(boxes, e.clientY);
      if (target) rows[target.index].classList.add(target.before ? "drop-before" : "drop-after");
    };
    const end = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", cancel);
      clear();
      rows[from].classList.remove("dragging");
      this._dragging = false;
      const to = target ? dropIndex(from, target.index, target.before, rows.length) : null;
      if (to !== null) this._call({ type: "media_queue/move", item_id: itemId, to_index: to });
      this._renderQueue();
    };
    const cancel = () => {
      target = null;
      end();
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", cancel);
  }

  // -------------------------------------------------------------- transport

  _renderTransport() {
    if (!this._now) return;
    const stateObj = this._stateObj;
    const info = nowPlaying(stateObj, this._snapshot);
    const action = playPauseAction(stateObj, this._snapshot);
    const buttons = queueButtons(this._snapshot);
    const volume = volumeOf(stateObj);
    const shuffle = shuffleButton(this._snapshot);
    const repeat = repeatButton(this._snapshot);
    const fallback = () => h("span", { class: "art" }, icon("mdi:music"));
    const art = info.picture ? h("img", { alt: "", onerror: () => art.replaceWith(fallback()) }) : fallback();
    if (info.picture) this._sign(info.picture).then((src) => (art.src = src));
    this._now.replaceChildren(
      art,
      h(
        "div",
        { class: "info" },
        h("div", { class: "t" }, info.title ?? this.t("nothing_playing")),
        h("div", { class: "s" }, info.subtitle),
      ),
      h(
        "button",
        {
          class: shuffle.pressed ? "mode on" : "mode",
          title: this.t(shuffle.title),
          "aria-label": this.t("shuffle"),
          "aria-pressed": String(shuffle.pressed),
          disabled: !this._entityId,
          onclick: () => this._call({ type: "media_queue/set_shuffle", shuffle: shuffle.value }),
        },
        icon(shuffle.icon),
      ),
      h(
        "button",
        {
          title: this.t("previous"),
          "aria-label": this.t("previous"),
          disabled: !buttons.previous,
          onclick: () => this._call({ type: "media_queue/previous" }),
        },
        icon("mdi:skip-previous"),
      ),
      h(
        "button",
        {
          class: "main",
          title: this.t("play_pause"),
          "aria-label": this.t("play_pause"),
          disabled: !action,
          onclick: () => this._playPause(),
        },
        icon(action?.icon ?? "mdi:play"),
      ),
      h(
        "button",
        {
          title: this.t("next"),
          "aria-label": this.t("next"),
          disabled: !buttons.next,
          onclick: () => this._call({ type: "media_queue/next" }),
        },
        icon("mdi:skip-next"),
      ),
      h(
        "button",
        {
          class: repeat.value === "all" ? "mode" : "mode on",
          title: this.t(repeat.title),
          "aria-label": this.t(repeat.title),
          disabled: !this._entityId,
          onclick: () => this._call({ type: "media_queue/set_repeat", repeat: repeat.value }),
        },
        icon(repeat.icon),
      ),
      volume !== null &&
        h("input", {
          type: "range",
          min: 0,
          max: 100,
          value: volume,
          title: this.t("volume"),
          "aria-label": this.t("volume"),
          onchange: (e) =>
            this._service("volume_set", { volume_level: Number(e.target.value) / 100 }),
        }),
    );
  }

  _playPause() {
    const action = playPauseAction(this._stateObj, this._snapshot);
    if (action?.kind === "service") this._service(action.service);
    else if (action) this._call({ type: "media_queue/play_index", index: action.index });
  }

  // ---------------------------------------------------------------- helpers

  async _call(message) {
    try {
      await this._hass.callWS({ ...message, entity_id: this._entityId });
    } catch (err) {
      this._notify(this.t("error", { message: err.message ?? err.code }));
    }
  }

  async _service(service, data = {}) {
    try {
      await this._hass.callService("media_player", service, { entity_id: this._entityId, ...data });
    } catch (err) {
      this._notify(this.t("error", { message: err.message ?? err.code }));
    }
  }

  _notify(text) {
    this._toast.textContent = text;
    this._toast.classList.add("show");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => this._toast.classList.remove("show"), 4000);
  }
}

customElements.define("media-queue-panel", MediaQueuePanel);
