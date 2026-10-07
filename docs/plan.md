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

---

# Addendum: 0.2.0 — shuffle, repeat, tag titles

Gert's feedback on 0.1.0 ("Dat ziet er al beter uit"): a shuffle and a repeat
button per player, managed by the queue in Home Assistant, and real titles
(ID3/Vorbis/MP4 tags) instead of file names. Same rules as 0.1.0: TDD, 100 %
line + branch, mypy --strict, ruff, node tests at 100 % for `frontend/lib`.

## Design decisions

### Shuffle: `items` is always the play order

- A queue has `shuffle` (bool) and, while shuffle is on, `original`: the item
  ids in their unshuffled order. The `items` list itself **is the play order**:
  the panel shows exactly what plays next, and every existing command (jump,
  remove, move, next/previous, `item_id` and index) keeps working unchanged.
  (Equivalent to "flag + permutation", but the permutation is applied to the
  list instead of stored next to it, so indices in the API never need
  translating.)
- **Shuffle on**: the current item moves to the top and stays current; every
  other item is shuffled after it (played ones included, like most players).
  Without a current item the whole queue is shuffled.
- **Shuffle off**: `items` return to `original` order; the current item stays
  current (it continues from its place in the album); without a current item
  the item that was next stays next.
- **Adding while shuffled**: `add` scatters each new item at a random position
  *after* the current item (the upcoming part stays a random mix);
  `next`/`play`/`replace` insert the new block shuffled among itself where they
  always do (after the current item / at the top). In `original` the new items
  go where they would have gone unshuffled (`add`: the end; `next`/`play`:
  after the current item), so turning shuffle off gives the album order back.
- Remove and move work on the play order; remove also drops the id from
  `original`, move does not change `original` (moving is about play order).
- `clear` keeps the shuffle and repeat settings (they belong to the player).

### Repeat: off → all → one

- `all`: after the last item (natural end or the next button) the queue starts
  again at the top; with shuffle on it is reshuffled first, and the item that
  just played is never the first one again (when there are two or more).
- `one`: at the natural end the current item plays again. Next/previous still
  move (and the repeat stays on). An item that fails to (re)start is not
  repeated: advancing then continues with the next item, as before.
- `next` in the snapshot is what the next button plays: with repeat `all` at
  the end it is the first item (`null` with shuffle on: the order is drawn when
  it wraps); the panel enables the button for repeat `all` anyway.
- MPD's own repeat/random (and every player's own shuffle/repeat) are never
  touched; the queue sends one item at a time as before.

### Storage

- Store **minor** version 1 → 2 (`STORAGE_MINOR_VERSION`), migration adds
  `shuffle: false`, `repeat: "off"` to each 0.1.0 queue. A minor bump keeps a
  rollback to 0.1.0 working: HA hands newer minor data to old code as it is,
  and `Queue.from_dict` ignores keys it does not know.
- Players whose queue is empty but whose shuffle/repeat is not the default are
  stored too, so the buttons survive a restart.

### Tags

- Library: **mutagen 1.48.1** — HA core's `tts` integration pins exactly this
  version, so on the Pi it is (almost always) installed already; pure Python
  (195 kB wheel, `py3-none-any`), works on aarch64/Python 3.14. Pinned in the
  manifest at the same version as core.
- Only items of the local media source (`media-source://media_source/<dir>/…`,
  files inside a configured media dir) are read; everything else keeps its
  browse title.
- **Add first, enrich later**: items enter the queue immediately with the file
  name (or `#EXTINF`) as title, so an add stays as fast as in 0.1.0; a
  background task then reads the tags in the executor in batches (at most 100
  files or 2 s per batch, at most 1000 files per add), replaces title/artist/
  album/duration of the items still in the queue and pushes one queue update
  per batch. One batch at a time per player. Files over 1 GiB are skipped; a
  batch that does not return within 30 s (hung CIFS mount) ends the enrichment
  of that add (the thread is left to finish on its own).
- Priority: tag title > `#EXTINF`/browse title > file name. The panel shows
  "title – artist" and keeps the file name as tooltip.
- The tag duration is used by the end-of-item check when the player reports
  no duration itself (still never for radio/streams: they have no tag
  duration).
- Items whose enrichment was interrupted by a restart keep their file-name
  title (no re-reading at start-up: nothing heavy at boot).

## Tasks 0.2.0

15. **Model**: `Repeat`, `Queue.shuffle/repeat/original`, `set_shuffle`, shuffle-
    aware `add`/`remove`/`clear`, `rewind` (wrap, reshuffle, avoid repeat of
    the last item), serialisation (tolerant).
16. **Storage**: minor version 2 with migration; settings of empty queues kept.
17. **Controller**: repeat one/all in advancing and next, wrap with reshuffle,
    `set_shuffle`/`set_repeat`, snapshot `shuffle`/`repeat`, item duration as
    fallback for the end check.
18. **API**: websocket `media_queue/set_shuffle`, `media_queue/set_repeat`;
    actions `media_queue.set_shuffle`, `media_queue.set_repeat`; strings, icons.
19. **Tags**: `tags.py` (path of a local item, bounded tag reader), item fields
    artist/album/duration, background enrichment, manifest requirement.
20. **Frontend logic**: shuffle/repeat button state and cycling, queue row
    label "title – artist" with the file name as tooltip, rows key that sees
    title changes, next enabled for repeat all.
21. **Panel**: shuffle and repeat buttons in the transport (aria-pressed,
    nl/en labels), "shuffled" note on the queue header.
22. **Release docs**: manifest 0.2.0, README, CHANGELOG.md.
23. **e2e** on the dev HA with tagged test files; screenshots.
