# Media queue — implementation plan

Design: `docs/design.md`. Every task: test first, watch it fail on an assertion,
implement, full gate green (pytest 100 % line + branch, `mypy --strict`, `ruff`),
one commit. Frontend logic: `node --test --experimental-test-coverage` at 100 % for
the logic modules.

## Environment

- `.venv` (python3.14), `requirements_test.txt`:
  `pytest-homeassistant-custom-component==0.13.367` (HA 2026.9.4, the Pi's version),
  pytest-cov, mypy, ruff. No runtime requirements (only HA core components).
- `pytest.ini` (coverage enforced), `tests/conftest.py`, `mypy.ini` (strict),
  `ruff.toml` — taken over from ha-music-library.
- Node 26 for the frontend tests (`frontend/test/*.test.mjs`), no npm packages.

## Files

```
custom_components/media_queue/
  __init__.py      async_setup: websocket commands + services (once);
                   entry setup/unload: QueueManager (Store), panel
  const.py         domain, limits, storage key, panel names
  manifest.json    0.1.0, deps http/frontend/panel_custom/media_source/media_player/websocket_api
  model.py         QueueItem, Queue: pure list logic (modes, remove, move, clear,
                   next/previous position, serialisation)
  expand.py        browse an item (media_source or the player entity) depth-first
                   into playable leaves, capped
  controller.py    QueueController per media_player: play an item (resolve +
                   play_media), the end-of-item state machine, commands, lock
  manager.py       QueueManager: controllers per entity, Store (delayed save),
                   subscribers
  websocket.py     media_queue/{get,subscribe,add,play_index,remove,move,clear,next,previous}
  services.py      media_queue.{add,play_index,remove,move,clear,next,previous,get_queue}
  panel.py         static path (versioned URL) + panel_custom registration "Muziek"
  config_flow.py   single instance, no options
  diagnostics.py
  strings.json  translations/{en,nl}.json  services.yaml  icons.json
  frontend/
    media-queue-panel.js   thin DOM layer (custom element <media-queue-panel>)
    lib/*.js               pure logic modules (tested with node --test)
    test/*.test.mjs
hacs.json  README.md
```

## The end-of-item state machine (controller.py)

Phase per player: `idle` (not following the player), `starting` (we sent
play_media), `playing` (armed: we follow this item, also while paused), `stopped`
(someone stopped it before the end; resuming re-arms it).

- Our own commands (play_index / next / previous / add with replace or play) go
  through `_play(index)`: phase `starting`; state events during the service call
  are ignored. Armed (`playing`) at the first `playing` state after the call that is
  really the new item: the state was not `playing` before the call, or
  media_content_id changed, or the position restarted after the call. The
  player's own media_content_id at that moment is the *fingerprint*.
- `playing` → `idle`/`off`/`on`/`standby` not caused by us: natural end when the
  estimated position (last position + time since media_position_updated_at while
  playing) reached duration − 5 s; then the next item plays. Without a known
  position the time since arming is used. Without a known duration (radio, streams)
  it is *never* an end: the user stopped it → `stopped`. (Deviation from the design
  text "idle without our stop = end": that would start the next track whenever
  someone presses stop in the Sonos app or an HA card.)
- `playing` → `paused` at the end (players that pause at the end of an item) → next.
  Paused elsewhere → stays armed.
- `playing` with a different non-empty media_content_id than the fingerprint →
  someone plays something else on that player → `idle` (we stop following).
- `stopped` → `playing` with the same (or unknown) fingerprint → armed again.
- unavailable / unknown / buffering: ignored.
- End of the queue → `idle`, current stays on the last item.
- An item that fails to play during auto-advance is skipped (max 3 in a row).
- Phase `playing`/`stopped` and the fingerprint are persisted so a HA restart keeps
  following the player.

## Tasks (TDD order) and tests

1. **Scaffold**: env files, manifest, const, conftest. Test: the integration's
   manifest loads with version 0.1.0, config_flow, local_push, dependencies.
2. **Queue model + Store persistence** — `model.py`: add with replace / add / next /
   play (insert positions with and without a current item), remove (before, at,
   after current; removing the current item keeps "what comes next"), move (current
   follows its item), clear, next/previous position, item ids unique, cap to the
   queue limit (truncated count), to/from dict (tolerant of bad stored data).
   `manager.py`: queues persisted via Store (delayed save), restored on load,
   unknown/malformed storage ignored, subscribers notified on change.
3. **Expansion** — `expand.py`: leaf → itself; media-source folder → recursive
   through `media_source.async_browse_media` in source order; other ids through the
   entity's `async_browse_media`; can_play folder without children → itself; non
   playable leaves skipped; cap (truncated flag); depth limit; cycles; BrowseError on
   a nested folder skipped; unknown entity / no browse support → translated error.
4. **Playback** — `controller.py` `_play`: media-source ids resolved with
   `media_source.async_resolve_media(hass, id, entity_id)` →
   `async_process_play_media_url` → `media_player.play_media` (type music / video by
   mime); other ids played as they are; errors → translated HomeAssistantError and
   phase idle.
5. **State machine** — every transition above, incl. idle vs off, position ≈
   duration, paused at the end, radio stream without duration (never advances),
   stop elsewhere, resume, detach, events during our own call ignored, same item
   replayed, end of queue, skipping failing items, restart restore.
6. **Commands** — add (all modes, play for replace/play), play_index, next,
   previous (restart at index 0), remove, move, clear, with index validation errors
   and permission per entity.
7. **WebSocket API** — every command through `hass_ws_client`, subscribe gets the
   initial state and updates and stops on unsubscribe, errors as websocket errors,
   non-admin users allowed, entity permissions respected.
8. **Services** — same operations for automations; `get_queue` returns response data.
9. **Config flow + panel + setup/unload** — single instance, panel registered with
   title "Muziek", icon mdi:playlist-music, require_admin false, module URL under a
   versioned static path; unload removes the panel and flushes the Store; commands
   without a loaded entry raise `not_loaded`.
10. **Diagnostics** — per player: item count, current, phase.
11. **Translations** — en == strings.json, nl complete, every translation_key used in
    code exists.
12. **Frontend logic** (node tests, 100 %): `i18n.js` (nl/en by hass.language,
    placeholders), `queue-view.js` (rows, current, total duration/count, status),
    `reorder.js` (drag from/to → move indices, no-op detection), `browse-actions.js`
    (which of ▶ ⏭ ➕ / open apply to a browse item, payload for media_queue/add),
    `player-memory.js` (remember/restore the chosen player, storage failures),
    `players.js` (player list from hass.states, sorted, PLAY_MEDIA only, browse
    capability), `transport.js` (what play/pause/prev/next do).
13. **Frontend panel** — `media-queue-panel.js`: picker, library, queue, transport,
    tabs on phone width; end-to-end in the browser pane.
14. **README, hacs.json**, e2e on ~/Workspace/ha-dev, screenshots in
    `docs/screenshots/`.
