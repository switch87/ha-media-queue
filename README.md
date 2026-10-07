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
- **Shuffle** (🔀) and **repeat** (🔁 off → whole queue → current item) per
  player, next to previous/next. They are kept by the queue, not by the
  player: the player's own shuffle/repeat (MPD's random/repeat, Sonos's play
  mode) is never touched. See "Shuffle and repeat" below.
- **Titles from the tags**: items from the local media source (your music
  folder or NAS mount) show "title – artist" from the files' ID3/Vorbis/MP4
  tags instead of the file name (the file name is the tooltip). See "Titles
  from the tags" below.
- Queues, their shuffle/repeat settings and the tag titles survive a restart
  (stored in `.storage/media_queue`).
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

One Python package: **mutagen 1.48.1** (pure Python, ~200 kB), the version
Home Assistant core itself pins for its `tts` integration, so it is usually
installed already; otherwise Home Assistant installs it at the restart. The
panel is a few small JavaScript modules served by the integration (no build
step, nothing from the internet).

Updating from 0.1.0: copy the new folder, restart. The stored queues are
migrated (storage version 1.1 → 1.2: shuffle off, repeat off). Going back to
0.1.0 keeps working; it ignores the new fields.

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

## Shuffle and repeat

- The queue list always shows the **real play order**. Turning shuffle on
  moves the current item to the top (it keeps playing, it stays current) and
  shuffles every other item after it; the panel says "Shuffled: the queue is
  shown in play order." Turning shuffle off puts the queue back in the order
  it was added in (album order), with the current item still current.
- Adding while shuffled: **Add to queue** mixes the new items at random
  places after the current item; **Play next** puts them (shuffled among
  themselves) right after the current item; **Play** replaces the queue with
  the new items, shuffled. In the remembered album order they go where they
  would have gone without shuffle.
- Jump, remove and drag work as usual on the shown (play) order.
- **Repeat whole queue**: after the last item (when it ends, or with the next
  button) the queue starts again at the top; when shuffled it is shuffled anew
  first, without starting with the item that just played.
- **Repeat current item**: when the item ends it plays again. Next and
  previous still move to another item (repeat stays on). An item that does not
  start is not retried: the queue goes on with the next one.
- Both settings are per player and survive a restart; they are also in the
  actions and the websocket API (`set_shuffle`, `set_repeat`).

## Titles from the tags

For items of the local media source (`media-source://media_source/…`), the
title, artist, album and duration are read from the file's tags with
mutagen. Everything else (radio, DLNA, Sonos library, …) keeps the title the
media browser gives it.

- **Add first, tags after**: an add is as fast as before; the items appear
  with their file name (or the playlist's `#EXTINF` title), then a background
  job reads the tags and the queue updates itself (in batches: at most 100
  files or 2 s of reading per batch, one queue update per batch, at most 1000
  files per add).
- **Embedded covers are never read.** FLAC files: only the STREAMINFO and
  VORBIS_COMMENT blocks are read, pictures and padding are skipped. MP3 files
  with a large ID3 tag (over 128 kB, i.e. a big cover): only the title, artist
  and album frames are read, the picture is skipped. Everything else (small
  ID3 tags, M4A, Ogg, …) is read by mutagen, but never more than 256 kB per
  file: an M4A or Ogg file whose tags are bigger (a large cover) keeps its
  file name. Measured: ~16 kB read for a FLAC or MP3 with a 5 MB cover, ~25 kB
  for an MP3 without one (8 kB reads), 0.1–0.5 ms per file on a local disk;
  over a network mount (CIFS) expect a few milliseconds per file.
- A tag title wins over `#EXTINF`, which wins over the file name. Files over
  1 GiB are skipped; a batch that does not return within 30 s (a hung mount)
  ends the reading for that add, the file names stay, and that player reads
  no tags for 10 minutes (logged once).
- The duration from the tags is also used to recognise the end of an item
  when the player does not report a duration itself (radio and streams still
  never end by themselves: they have no tags).
- Items that were in the queue before 0.2.0, or whose reading was cut short
  by a restart, keep their file name until they are added again (nothing is
  re-read at start-up).

## What the players themselves do with each item

The queue plays one item at a time with a plain `media_player.play_media`
(no `enqueue`). What a player does with that call is up to its integration:

- **MPD (core `mpd`)**: every `play_media` clears MPD's own playlist, adds the
  one item and plays it. MPD's playlist therefore only ever holds the current
  item; the queue lives in Home Assistant. MPD reports durations as text; that
  is handled. **Turn MPD's repeat mode off**: with repeat on (and single off or
  on), MPD replays the single item forever, never stops, and the queue never
  moves on. Random/consume make no difference with one item. Use the queue's
  own shuffle and repeat buttons instead; they never change MPD's modes.
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
`media_queue.move`, `media_queue.clear`, `media_queue.set_shuffle`
(`shuffle`: true/false), `media_queue.set_repeat` (`repeat`: off/all/one), and
`media_queue.get_queue` (returns the queue, with `shuffle` and `repeat`). `play_index`, `remove` and `move` take an `item_id` (from
`get_queue`) or a position. Users who may not control a player cannot change
its queue; players that do not exist are refused (only `add` creates a queue).

## Websocket API (used by the panel)

`media_queue/get`, `media_queue/subscribe`, `media_queue/add`,
`media_queue/play_index`, `media_queue/remove`, `media_queue/move`,
`media_queue/clear`, `media_queue/next`, `media_queue/previous`,
`media_queue/set_shuffle` (`shuffle`), `media_queue/set_repeat` (`repeat`);
all take `entity_id`; items are named by `item_id` (the index is a fallback).
A snapshot holds `items` (in play order, each with `title`, `artist`,
`album`, `duration` when known), `current`, `next` (what the next button
plays; `null` at the end, also with repeat all + shuffle because the new order
is drawn when it wraps), `shuffle`, `repeat`, `phase` and `last_error`. The
subscription sends a full snapshot when the items or settings change and a small
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

`scripts/make_dev_library.py <folder>` writes a few tiny tagged MP3 albums
into a dev media folder (for checking tag titles, shuffle and repeat on a
local Home Assistant).
