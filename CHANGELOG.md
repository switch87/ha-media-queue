# Changelog

## 0.2.0 — 2026-10-07

Gert's wishes after 0.1.0 ("Dat ziet er al beter uit").

### Added

- **Shuffle** per player (🔀 in the transport, `mdi:shuffle-variant` /
  `mdi:shuffle-disabled`, `aria-pressed`, English and Dutch labels). The queue
  list shows the real play order; the current item stays current when
  shuffle goes on or off; turning it off restores the order the items were
  added in. Adding while shuffled: *add* mixes the new items into what comes
  after the current item, *next*/*play* put them (shuffled) right after it.
- **Repeat** per player, cycling off → whole queue → current item
  (`mdi:repeat-off` / `mdi:repeat` / `mdi:repeat-once`). Repeat all starts
  again at the top after the last item (shuffled anew when shuffle is on, never
  with the item that just played); repeat one plays the item again when it
  ends; next/previous still move.
- Shuffle and repeat are kept by Home Assistant, never by the player (MPD's
  random/repeat and Sonos's play mode are not touched), stored per player and
  available as actions (`media_queue.set_shuffle`, `media_queue.set_repeat`)
  and websocket commands (`media_queue/set_shuffle`, `media_queue/set_repeat`);
  snapshots and `get_queue` carry `shuffle` and `repeat`; diagnostics too.
- **Titles from the tags** of local files (ID3, Vorbis, MP4, … via mutagen
  1.48.1, the version HA core pins): the queue shows "title – artist" with the
  file name as tooltip; items also get album and duration. Tags are read in
  the background after the add (batches of at most 100 files / 2 s, at most
  1000 files per add, a 30 s guard per batch, files over 1 GiB skipped), so
  adding stays as fast as before.
- The tag duration is used to recognise the end of an item when the player
  reports no duration.
- `scripts/make_dev_library.py`: tiny tagged MP3s for a dev media folder.

### Changed

- Storage version 1.1 → 1.2 with a migration (shuffle off, repeat off).
  Rolling back to 0.1.0 keeps working.
- Queues whose only content is a non-default shuffle/repeat setting are
  stored too.
- `next` in snapshots is what the next button plays (the first item at the end
  with repeat all; unknown with repeat all + shuffle).
- New requirement: `mutagen==1.48.1`.

## 0.1.0 — 2026-10-07

First release: a queue per media player kept by Home Assistant, the sidebar
page "Muziek" (library, queue, transport), actions and a websocket API.
