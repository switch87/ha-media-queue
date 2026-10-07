# Media queue for Home Assistant

A play queue for every `media_player`, kept by Home Assistant itself, and a
sidebar page **Muziek** to use it: the library on the left (everything Home
Assistant's media browser offers for the chosen player: local media, NAS, radio,
DLNA, …), the queue on the right, transport controls on top.

- **▶ Play** replaces the queue with the item and starts it, **⏭ Play next** puts
  it after the current item, **➕ Add to queue** appends it. Works for single
  tracks and for folders, albums and artists (expanded into their tracks,
  depth-first in the source's order, at most 1000 items per queue).
- The queue shows the current item; click an item to jump to it, ✕ to remove
  it, drag the handle to reorder, clear it with the button in its header.
- Players stay normal entities: pause and volume go to the player itself;
  previous/next go through the queue.
- Queues survive a restart (stored in `.storage/media_queue`).
- **Playlists** (`.m3u`, `.m3u8`, `.pls` on the local media source): adding a
  playlist queues its entries in order, with the `#EXTINF`/`TitleN` titles.
  Entries are relative to the playlist's folder (absolute paths inside the
  media folder work too; backslashes, UTF-8 with or without BOM and Latin-1
  are understood); `http(s)` URLs become items; entries outside the media
  folder and missing files are skipped. When a *folder* is added, playlist
  files in it are skipped (their tracks are in the folder already).
- The play/next/add buttons appear only for audio: not on the media-source
  roots, nor on cameras, images, image uploads, text-to-speech, AI tasks,
  pictures or videos (those can still be browsed).
- English and Dutch; on a phone the library and the queue are tabs.

Screenshots: `docs/screenshots/`.

## Install

Copy `custom_components/media_queue` to `/config/custom_components/`, restart
Home Assistant, then *Settings → Devices & services → Add integration → Media
queue*. Nothing to configure. The sidebar gets **Muziek** for every user.

No extra Python packages; the panel is a few small JavaScript modules served by
the integration (no build step, nothing from the internet).

## How playing works

Each queue item is played with `media_player.play_media` on the real player.
`media-source://` items are resolved first (like the players do themselves) and
sent as a URL with content type `music` (or `video`/`image`); items from the
player's own library are sent as they are.

The integration follows the player's state and plays the next item when the
current one **ends by itself**: the player leaves `playing` for
`idle`/`off`/`on`/`standby` (or pauses) within 5 s of the item's duration,
estimated from the last reported position and its timestamp (or, without a
position, from the time it played). Things that are *not* an end:

- a stop or pause before the end (someone pressed stop in another app or card):
  the queue waits; pressing play on the player continues following it;
- items without a duration (radio, streams): they never end by themselves, on
  purpose (Gert, 2026-10-07): a stop of the radio elsewhere must never start
  the next item. Press next to go on;
- the player playing something else (another media id): the queue stops
  following it until you play from the queue again.

Durations and positions reported as text (MPD) are understood; positions
reported before the item was started are ignored.

Items that fail to play during advancing are skipped (at most 3 in a row), as
are items the player accepts but does not start within 25 s (a URL it cannot
fetch, a format it cannot play). The panel shows these errors.

## What the players themselves do with each item

The queue plays one item at a time with a plain `media_player.play_media`
(no `enqueue`). What a player does with that call is up to its integration:

- **MPD (core `mpd`)**: every `play_media` clears MPD's own playlist, adds the
  one item and plays it. MPD's playlist therefore only ever holds the current
  item; the queue lives in Home Assistant. MPD reports durations as text; that
  is handled. **Turn MPD's repeat mode off**: with repeat on (and single off or
  on), MPD replays the single item forever, never stops, and the queue never
  moves on. Random/consume make no difference with one item.
- **Sonos (core `sonos`)**: files and streams from the media sources are
  played with Sonos's "play URI" path (Sonos's own queue is left alone).
  Items from **Sonos favorites or the Sonos music library** (ids such as
  `A:ALBUM/…`, `FV:…`) go through Sonos's queue-replacing path: each item
  clears Sonos's queue and plays. The panel shows a note when you browse those
  sections; the queue here still steps through them one by one.
- Other players: whatever their `play_media` does for one item; the queue only
  needs the player to report `playing` and, to advance, a duration.

## Actions (for automations and scripts)

`media_queue.add` (`entity_id`, `media_content_id`, `media_content_type`,
`mode`: replace/add/next/play, `title`), `media_queue.play_index`,
`media_queue.next`, `media_queue.previous`, `media_queue.remove`,
`media_queue.move`, `media_queue.clear`, and `media_queue.get_queue` (returns
the queue). `play_index`, `remove` and `move` take an `item_id` (from
`get_queue`) or a position. Users who may not control a player cannot change
its queue; players that do not exist are refused (only `add` creates a queue).

## Websocket API (used by the panel)

`media_queue/get`, `media_queue/subscribe`, `media_queue/add`,
`media_queue/play_index`, `media_queue/remove`, `media_queue/move`,
`media_queue/clear`, `media_queue/next`, `media_queue/previous`; all take
`entity_id`; items are named by `item_id` (the index is a fallback). The
subscription sends a full snapshot when the items change and a small
`{"playback": true, current, next, phase, last_error}` update when only
playback changes; `{"closed": true}` when the integration unloads.

## Remove

Delete the integration entry (this also deletes `.storage/media_queue`),
remove `custom_components/media_queue`, restart.

## Development

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest -q          # 100 % line + branch coverage enforced
.venv/bin/mypy custom_components/media_queue tests
.venv/bin/ruff check . && .venv/bin/ruff format --check .
npm test                               # node --test, 100 % for frontend/lib
```
