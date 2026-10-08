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
  (195 kB wheel, `py3-none-any`), works on aarch64/Python 3.14. The manifest
  asks `mutagen>=1.47` (review fix: no exact pin, so a later HA core with a
  newer mutagen still loads the integration); the tests pin 1.48.1.
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

## e2e 0.2.0 (dev HA 2026.9.4 on gaia, 127.0.0.1:8124, demo players)

Test library: `scripts/make_dev_library.py ~/Workspace/ha-dev/lib` (Yeti: 7
tagged tracks, Night Owls: 4). Player: `media_player.living_room` (demo).
Ends of items were simulated through the REST state API (playing near the end,
then idle); no real speakers.

- Storage migration: the 0.1.0 store (1.1, one queue) was rewritten as 1.2 with
  `shuffle: false`, `repeat: "off"` at the first start of 0.2.0.
- Tags: ▶ on the Yeti folder → 7 rows with file names, within a second
  "Soap Shop Rock – Amon Düül II" … with album and duration; file name as
  tooltip, "Play: title – artist" as accessible name.
- Shuffle on with Cerberus (3rd) playing → Cerberus on top, still current, the
  rest mixed, note "Shuffled: the queue is shown in play order."; shuffle off →
  album order, Cerberus current at 3; no play_media call on either toggle.
- Repeat all + shuffle, last item ends → queue mixed anew, the item that just
  ended not first, the new first item plays. Repeat all in order → item 0
  plays after the last.
- Repeat one, item ends → the same item is played again, current unchanged.
- Repeat button cycles all → one → off → all (icons and `aria-pressed`
  checked in the DOM).
- Add (➕) of Night Owls while shuffled → the 4 tracks mixed into the part
  after the current item, tags read.
- Restart of the dev HA → order, current, shuffle, repeat and tag titles the
  same; shuffle off after the restart still restores the album order.
- Phone width: transport wraps (shuffle, previous, play, next, repeat on one
  row, volume below), queue tab shows the shuffled note.
- Screenshots: `docs/screenshots/panel-shuffle-repeat-tags-en.jpg`,
  `docs/screenshots/panel-phone-queue-shuffle-en.jpg`.

Per-file cost of the tags (gaia, local SSD, warm): 0.1–0.5 ms, ~20 small reads
and ~10 seeks, 0.7 kB read for an MP3 and 8.6 kB for a FLAC (first call in a
process ~36 ms: mutagen's lazy imports). On the Pi over CIFS each file costs
some network round trips (estimate a few ms to ~20 ms), which is why tags are
read after the add, in the background.

### Review fix: covers

mutagen reads embedded cover art in full (FLAC PICTURE, ID3 APIC, MP4 covr):
5.6 MB for a FLAC with a 5 MB picture. `tags.py` now walks FLAC metadata
blocks itself (STREAMINFO + VORBIS_COMMENT only), walks the frames of ID3v2.3/
2.4 tags over 128 kB itself (TIT2/TPE1/TALB only; v2.2, unsynchronised or
flagged frames give no titles; the duration from mutagen's `MPEGInfo` after
the tag), and gives every other file to mutagen through a reader that stops at
256 kB (over it: file name). Reads use an 8 kB buffer. Measured: 16 kB for a
FLAC or MP3 with a 5 MB cover, 25 kB for an MP3 without.

---

# Addendum: 0.3.0 — a playlist library

Gert: "een wachtrij zou als een playlist moeten opgeslagen kunnen worden, in
een lokale library van playlists die voor alle players beschikbaar is".

## Design decisions

- **One library for the whole installation** (`library.py`,
  `PlaylistLibrary`), own Store `media_queue.playlists` (version 1.1, delayed
  save 5 s, flushed at unload; tolerant loading: malformed playlists and
  items are dropped). A playlist: `id`, `name` (trimmed, 1–100 characters,
  unique without regard to case), `items` (the queue items as they are:
  media id, type, title, artist, album, duration, thumbnail, media class —
  any source), `created`, `updated` (ISO timestamps). At most 1000 items per
  playlist (a queue holds no more) and 500 playlists.
- **Saving** takes a player's queue in its shown (play) order; an existing
  name is refused unless `overwrite` (the panel asks first). Rename keeps the
  id; a name taken by another playlist is refused (overwrite is not offered
  for renames: delete the other one first).
- **Loading** puts copies of the items (new item ids) into a player's queue
  with the usual modes (replace/add/next/play) and the usual shuffle/repeat
  rules; one track of a playlist can be loaded on its own (`item_id`). No
  browsing or expansion is needed; items without a duration get their tags
  read like any local item.
- **Permissions**: list/get need nothing beyond a logged-in user (the page is
  for every user). Save needs control of the player whose queue is saved;
  load needs control of the target player; rename and delete need an admin
  or a user who may control at least one media player.
- **API**: websocket `media_queue/playlists/{list,get,save,rename,delete,load}`
  (playlists by id); actions `media_queue.save_playlist`, `load_playlist`,
  `rename_playlist`, `delete_playlist`, `get_playlists` (by name, for
  automations).
- **Media source** `media-source://media_queue` ("Afspeellijsten (Muziek)"):
  HA's own media browser shows the playlists for every player; a playlist
  opens to its tracks, each playable with its original media id. The
  playlist itself is not playable there (HA's browser plays one item); the
  whole playlist is loaded from the Muziek page or the action. The Muziek
  page hides this source in its own library (it has a better folder for it).
- **Panel**: a "Save as playlist" button in the queue header (inline dialog
  for the name; an existing name asks to overwrite); a "Playlists" folder at
  the top of the library for every player: ▶ ⏭ ➕ per playlist and per track,
  open, rename, delete (confirmed). The list is fetched when the folder is
  opened (no live subscription).
- Removing the integration deletes the playlists too (like the queues).
- Diagnostics: number of playlists and of items only (no names).

## Tasks 0.3.0

24. `library.py`: model, validation, limits, Store, tolerant loading.
25. Manager owns the library; controller loads playlist items into a queue.
26. Websocket commands with permissions.
27. Actions, strings, icons.
28. Media source platform.
29. Diagnostics, removal deletes the playlists.
30. Frontend logic (`lib/playlists.js`, strings).
31. Panel: save dialog, playlists folder, rename/delete.
32. Release docs 0.3.0; e2e with screenshots (nl).

## e2e 0.3.0 (dev HA 2026.9.4, demo players)

- Saved the Living Room queue (11 tagged items) from the panel as
  "Zondagochtend"; saving "zondagochtend" again asked to overwrite (the name
  is looked up in the list first, no error round trip).
- On Bedroom (another player, empty queue): ➕ Add → 11 items, ⏭ Play next →
  22 (inserted at the top: nothing was current), ▶ Play → replaced by the
  11 items, the first one played on Bedroom; ➕ on one track of the opened
  playlist → that track appended.
- Rename to "Zondag" (dialog prefilled, focus back on the button), delete
  with confirmation → "no saved playlists yet" note.
- HA's own media browser: Media → "Playlists (Media queue)" lists the
  playlists; one opens to its tracks with titles "title – artist".
- Screenshots (nl): `docs/screenshots/playlist-*-nl.jpg`; English, for the
  README: `docs/images/*.png`.

## Community packaging (2026-10-07)

Gert: follow the HACS standard, public repo github.com/switch87/ha-media-queue,
MIT licence. Added LICENSE, `.github/workflows/validate.yml` (hacs/action with
`ignore: brands` until a brand icon exists, hassfest) and `ci.yml` (pytest at
100 %, mypy, ruff, node tests), tests for hassfest's manifest key order and
service icons, a community README and CONTRIBUTING.md. The sidebar title now
follows the installation's language ("Music", Dutch "Muziek").

---

# Addendum: 0.4.0 — complete playlists, listening history, stream URLs

Three wishes from Gert, through the Pi agent (2026-10-07). Same rules as
before: TDD (a test that fails on an assertion about the missing behaviour
first), 100 % line + branch coverage, `mypy --strict`, `ruff`, node tests at
100 % for `frontend/lib`.

## 1. Tags in saved playlists (the bug the Pi hit)

Saving a queue right after an add stored the items as they were *then*: the
background tag reading had not reached them, so artist, album and duration
were missing (a playlist of about five hours showed 58 minutes).

- The tag reading of 0.2.0 is moved out of `controller.py` into
  **`enrich.py`** (`TagReader`): the same batches (at most `TAG_BATCH` files
  or `TAG_BUDGET` seconds per batch), the same cover-art-skipping reader, the
  same 30 s guard per batch and 10 minute pause per *source* after a hung
  mount. A source is a player's queue or the playlist library; each has its
  own reader, so a stuck mount never pauses the other.
- A `TagTarget` is what a reader fills: `tag_ids()` (the items still there),
  `apply_tags()` (put the tags on them, return whether anything changed) and
  `tags_changed()` (tell the world / schedule a store write).
  `QueueController` and `PlaylistLibrary` are both targets.
- **Repair pass** `PlaylistLibrary.repair()`: every playlist item that lacks
  an artist *or* a duration and whose media id is a local media file is read
  in the background, playlist by playlist, and written through the library's
  usual delayed save (5 s). It runs
  - at **setup** (after `async_load`), so the playlists already stored on the
    Pi are completed without saving them again,
  - after a **save** and after a **load** (`PlaylistLibrary.load()`), so a
    queue saved before its tags were read is completed right away.
  One pass at a time (`TagReader.busy`); a pass that finds nothing starts no
  task at all.
- Nothing blocks the event loop: the reading itself stays in the executor.

## 2. Listening history and "Most played"

- **`history.py`**, `ListeningHistory`: own store `media_queue.history`
  (version 1), one entry per media id with `count`, `last_played` and the
  title/artist/album/duration/thumbnail as known, `HISTORY_MAX` 2000 entries
  (the least played and oldest are dropped). Loading is tolerant: malformed
  entries are skipped (a new store needs no migration code; unknown data is
  ignored the way `Queue.from_dict` ignores it).
- **What counts as a play**: an item that really played `PLAY_SECONDS` (30 s)
  or half its duration, whichever comes first — measured by the controller
  from the player's own state changes (the seconds it was in `playing`), so a
  skip or a stop before that counts for nothing. Counted once per start of an
  item (`repeat one` counts every repetition). Counted for every player.
- **Only real tracks**: a known duration and a media id that is not a bare
  `http(s)` URL. Radio and other streams have no duration (and a stream URL
  entered by hand is a URL), so they are never counted.
- **Writes**: at most one delayed save every `HISTORY_SAVE_DELAY` (5 minutes)
  while music plays, plus a soon save (5 s) when a player stops or the queue
  ends, and a save at unload. Easy on the SD card.
- **"Most played"** (`Meest beluisterd` on Dutch installations) is a
  **virtual playlist** in the library: id `most_played`, always first in the
  list, at most `MOST_PLAYED_MAX` (100) tracks, ordered by count descending
  then last played descending. It is built from the history on demand, so it
  is always current. It cannot be renamed, deleted or overwritten
  (`playlist_readonly`), and a name clash with it is refused like any other.
  Item ids are derived from the media id (`uuid5`), so the panel can load one
  of its tracks. It shows in the panel's Playlists folder and in Home
  Assistant's own media browser, like every playlist.
- **API**: websocket `media_queue/history/{list,reset}`, actions
  `media_queue.get_history` (response only) and `media_queue.reset_history`.
  Reading is open to every logged-in user; resetting needs an admin or a user
  who may control a media player (like renaming a playlist).
- Diagnostics: the number of tracks and the total number of plays only.
- Removing the integration deletes the history store too.

## 3. Stream URLs from the Muziek page

- **`stream.py`**: `async_expand_url`. Only `http` and `https` with a host
  are accepted (`invalid_url`); `file://`, `media-source://` and the rest are
  refused before any request. A URL whose path ends in `.m3u`, `.m3u8` or
  `.pls` is fetched (HA's shared aiohttp session, `STREAM_TIMEOUT` 10 s, at
  most `MAX_PLAYLIST_BYTES` 256 kB) and expanded with the readers of
  `playlist.py`; entries are resolved against the playlist URL and only
  `http(s)` entries are kept. Everything else becomes one stream item without
  a request (nothing is probed, nothing is downloaded).
  Errors are translated: `stream_unreachable` (timeout, connection, HTTP
  status), `stream_bad_content` (a content type that is neither a playlist
  nor text) and `stream_empty` (a playlist without usable entries).
- Items: the URL as media id, `music` as type, the given name or the file
  name from the URL as title. They are added through the normal modes
  (replace / add / next / play), so shuffle and repeat apply as always; no
  tags are read for them.
- **API**: websocket `media_queue/add_url` and action `media_queue.add_url`
  (`entity_id`, `url`, `mode`, `title`), control of the player required.
- **Favourites**: a URL is saved as a favourite with
  `media_queue/streams/save` (`url`, `name`, `overwrite`) — it becomes an
  ordinary saved playlist with the expanded items, so it is listed in the
  Playlists folder, plays with ▶ ⏭ ➕ and can be renamed and deleted with the
  code that is already there. No second kind of storage.
- **Panel**: a row under the library header with the URL field and ▶ ⏭ ➕ 💾
  (`frontend/lib/streams.js`: cleaning and validating the URL, the messages,
  the title suggestion).

## Tasks 0.4.0

33. `enrich.py`: `TagReader`/`TagTarget` out of the controller (no behaviour
    change), controller as a target.
34. `PlaylistLibrary` as a tag target + `repair()`, called on setup, save and
    load.
35. `history.py`: entries, store, record, top list, reset, pruning.
36. Controller: measure what really played, count a play, flush on stop.
37. Library: the virtual "Most played" playlist; rename/delete/overwrite
    refused.
38. Websocket + actions for the history; strings, icons, services.yaml.
39. `stream.py`: validation, playlist fetching and expansion, errors.
40. `add_url` and `streams/save` (favourites) in the websocket API and the
    actions.
41. Frontend logic `streams.js`, playlist nodes for the read-only playlist,
    labels.
42. Panel: the stream row.
43. Diagnostics, store removal, manifest 0.4.0.
44. README, CHANGELOG, e2e on the dev HA with English screenshots.

## Hang report from the Pi (handled first)

The Pi agent reported "websocket ws_get hangs while a subscription is
active" and a Muziek page that stopped responding, after it had added a
`media_queue:` line to `configuration.yaml` (12:00) and removed it (12:30).

- `ws_get`, `subscribe` and every subscriber callback are synchronous
  `@callback`s: no awaits, no locks, no I/O. Regression tests
  (`tests/test_concurrency.py`, real asyncio with timeouts) show `get`
  answering with two panels subscribed, during tag reading and during
  playlist save/load; on the dev HA 200 `get`s under that load took 0.3 ms
  median, 1.2 ms max, and both panels kept receiving updates.
- What did hang: the controller holds its lock across `play_media`
  (`blocking=True`, no limit). A player that never answers kept the lock
  forever, so next/previous/play_index/add/load on that player never
  returned (the test failed on its 5 s timeout). Fixed with
  `PLAY_TIMEOUT` (30 s) and the translated `play_timeout` error.
- A subscriber that raises is now dropped (and logged) instead of failing
  the change; players without subscribers are forgotten; diagnostics show
  the number of open subscriptions.
- `media_queue:` in YAML: `CONFIG_SCHEMA` is HA's
  `config_entry_only_config_schema`, which logs "does not support YAML
  setup" and raises a repair issue; `async_setup` runs once either way.
  A test confirms the entry still loads once and answers; README and
  CHANGELOG say so. The YAML line itself cannot cause a hang.

## Deviations from the plan above

- Repair reads each item *whose file was read* once per run, not every
  item handed to the reader: a file missing at start-up (a share mounted
  after HA) is tried again at the next save/load. A `TagReader.busy` flag
  was not needed; the library runs one repair round at a time and a
  request meanwhile adds one more round.
- HA creates background tasks eagerly: a repair round with nothing to read
  finishes inside `async_create_background_task`, so "is a round running"
  is `task.done()`, not a field cleared in `finally` (that left a finished
  task blocking every later round; found by the tests).
- The history store has no migration function: it is new, and an
  unreachable hook would break the 100 % rule. Malformed data is dropped at
  load, like the other stores.

## e2e 0.4.0 (dev HA 2026.9.4 on gaia, 127.0.0.1:8124, demo players)

Player states were driven through the REST state API where playback had to
be simulated (the demo players do not really play); tracks of the generated
test library are about 31 s long.

- **Playlist repair at setup**: a playlist "Saved before 0.4.0" with 11
  items without artist, album or duration was put in the store with HA
  stopped. At start, all 11 had title, artist and duration in memory
  (367 s in total) and in `.storage` 5 s later.
- **Save right after add**: Night Owls (4 files) added and saved in the same
  second: the saved playlist had file names and no duration; 2 s later all
  four had title, artist and duration.
- **History**: shuffle and repeat all were on. First item played 17 s then
  paused → counted; the next skipped after 5 s → not counted; the third
  stopped after 17 s → counted (and the store written within seconds);
  the first played again for 16 s → count 2. "Most played" appeared first
  in the playlist list with these tracks; rename, delete and save-over were
  refused with the translated message. A simulated state of other media
  (another content id) detached the queue and counted nothing.
- **Stream URLs** (local test server): play (replace) of an mp3 stream,
  add of an `.m3u` (2 streams; a `file://` entry dropped), next of a
  `.pls`, play (keep queue) of another URL — each in the right place, the
  URL sent to the player as it is. Refused with their own messages:
  `file://`, `media-source://`, an HTML page behind `.m3u`, an empty
  playlist, a closed port, a server that never answers (after 10.0 s).
  Favourite "Test radio" saved from the `.m3u` (2 streams).
- **Panel** (Playwright, Chromium): the stream row's ▶ ⏭ ➕ and Enter add
  and clear the field; an invalid URL shows "Enter an http:// or https://
  address."; the HTML page shows the server's message; ➕ on "Most played"
  added its 11 tracks; it has only ▶ ⏭ ➕ (no rename/delete).
- Screenshots (English, 1280×800 scaled to 800×500 like the others; the
  "Most played" counts are generated demo data): `docs/images/most-played.png`,
  `most-played-tracks.png`, `stream-url.png`, `save-favourite.png`,
  `phone-stream.png`.
