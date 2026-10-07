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
- items without a duration (radio, streams): they never end by themselves; use
  next;
- the player playing something else (another media id): the queue stops
  following it until you play from the queue again.

Items that fail to play during advancing are skipped (at most 3 in a row).

## Actions (for automations and scripts)

`media_queue.add` (`entity_id`, `media_content_id`, `media_content_type`,
`mode`: replace/add/next/play, `title`), `media_queue.play_index`,
`media_queue.next`, `media_queue.previous`, `media_queue.remove`,
`media_queue.move`, `media_queue.clear`, and `media_queue.get_queue` (returns
the queue). Users who may not control a player cannot change its queue.

## Websocket API (used by the panel)

`media_queue/get`, `media_queue/subscribe`, `media_queue/add`,
`media_queue/play_index`, `media_queue/remove`, `media_queue/move`,
`media_queue/clear`, `media_queue/next`, `media_queue/previous`; all take
`entity_id`.

## Remove

Delete the integration entry, remove `custom_components/media_queue` and
`.storage/media_queue`, restart.

## Development

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest -q          # 100 % line + branch coverage enforced
.venv/bin/mypy custom_components/media_queue tests
.venv/bin/ruff check . && .venv/bin/ruff format --check .
npm test                               # node --test, 100 % for frontend/lib
```
