# Changelog

## 0.3.0 — 2026-10-07

### Added

- **Playlist library** shared by all players: save a player's queue as a
  named playlist (the queue's shown order, with titles, artists, albums and
  durations as known; any source: local files, DLNA, radio URLs, …), load it
  into any player's queue with Play / Play next / Add (shuffle and repeat
  apply as for any add), load a single track of it, rename and delete.
  Names are 1–100 characters and unique regardless of case; at most 1000
  items per playlist and 500 playlists. Stored in `.storage/media_queue.playlists`
  (delayed save).
- Muziek page: a save button above the queue (asks before overwriting an
  existing name) and a **Playlists** folder at the top of the library for
  every player, with play/next/add, open (tracks with their own buttons),
  rename and delete (confirmed).
- Websocket commands `media_queue/playlists/{list,get,save,rename,delete,load}`
  and actions `media_queue.save_playlist`, `load_playlist`, `rename_playlist`,
  `delete_playlist`, `get_playlists`. Saving and loading need control of the
  player; renaming and deleting need an admin or a user who may control at
  least one media player; listing is open to every user.
- The playlists as a **media source** ("Playlists (Media queue)",
  "Afspeellijsten (Muziek)" on Dutch installations) in Home Assistant's own
  media browser: a playlist opens to its tracks, each playable with its
  original media id. A whole playlist is loaded from the Muziek page or the
  action (HA's browser plays one item).
- Diagnostics: number of playlists and items (no names).

### Changed

- Removing the integration also deletes the saved playlists.


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
- **Titles from the tags** of local files (ID3, Vorbis, MP4, … via mutagen,
  which HA core ships too): the queue shows "title – artist" with the
  file name as tooltip; items also get album and duration. Tags are read in
  the background after the add (batches of at most 100 files / 2 s, at most
  1000 files per add, a 30 s guard per batch, files over 1 GiB skipped), so
  adding stays as fast as before. Embedded covers are never read: FLAC
  metadata blocks and large ID3 tags are walked block by block / frame by
  frame, everything else reads at most 256 kB per file (an M4A/Ogg file with a
  larger cover keeps its file name).
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
- New requirement: `mutagen>=1.47` (no exact pin, so HA core can move on).

## 0.1.0 — 2026-10-07

First release: a queue per media player kept by Home Assistant, the sidebar
page "Muziek" (library, queue, transport), actions and a websocket API.
