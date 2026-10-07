# Media queue for Home Assistant ("Muziek" page) — design

Date: 2026-10-07 · Status: approved by Gert ("Ja doe de veilige manier")

## Why (Gert's feedback on music_library 0.1.0, which is withdrawn)

- Not separate "Muziek – …" players. Work with the **normal players** (Living Room,
  Werkplaats, any media_player) and **all sources** HA's media browser offers (radio,
  local media/NAS, DLNA, …), with all normal functions (next track, …).
- Everywhere: **play / add to queue / play next**, also whole folders, albums, artists.
- "It is about what Home Assistant supports, not what the players support": one
  extension of HA's media control, not per player.
- Like Winamp / every media player: browse a library, a **visible queue** next to the
  controls, put tracks/albums/folders in it, see what is playing, jump to an item,
  remove and reorder items.
- Gert chose the **safe** variant: a separate sidebar page "Muziek" (library left,
  queue right) instead of patching HA's built-in media panel internals (which can break
  on HA updates).

## Solution: custom integration `media_queue` + sidebar panel "Muziek"

### Backend (Python, no background load)

- **One queue per media_player entity**, kept by HA, independent of the player's own
  queue support. Items: `media_content_id` (media-source://… or URL), type, title,
  thumbnail (if known), duration (if known). Persisted with `homeassistant.helpers.storage.Store`
  so a restart keeps the queues.
- **Adding** (`mode`: replace / add / next / play): a playable leaf is one item; an
  expandable item (folder/album/artist/playlist from any source) is expanded through
  HA's media browser of that player (`media_player` browse via the entity /
  `media_source.async_browse_media`) recursively, depth-first in the source's order,
  playable leaves only, capped (e.g. 1000 items, translated warning when cut).
- **Playing an item**: resolve `media-source://` ids with `media_source.async_resolve_media`
  for that player, then `media_player.play_media` on the real player (no enqueue).
- **Advancing**: listen to the player's state; when the current item ends (state
  leaves `playing` to `idle`/`off` without a stop/pause requested by us, or position ≈
  duration), play the next item. Explicit commands next / previous / stop / jump(index)
  through the integration. No polling loops.
- **API** for the panel (websocket commands) and services for automations/scripts:
  get (queue + current index for a player), add (entity, media id/type, mode), play
  index, remove index, move (from, to), clear, next, previous. Subscribe command so the
  panel updates live.
- Players stay normal entities; transport (pause, volume) goes to the player itself.

### Frontend panel "Muziek" (JS, served by the integration, registered with panel_custom)

- Player picker (all media_player entities; remembers the last choice per browser).
- Left: library browser using HA's normal `media_player/browse_media` for the chosen
  player — all sources, same tree as HA's media menu. Per item buttons: ▶ Play
  (replace), ⏭ Play next, ➕ Add to queue; works for folders/albums/artists too.
- Right: the queue — current item highlighted, click to jump, remove (✕), drag to
  reorder, clear; total count.
- Bottom/top: transport controls of the chosen player (play/pause, previous/next via the
  queue, volume) and now-playing info from the player state.
- Dutch and English labels; works on phone width (stacked: library / queue tabs).
- No build chain dependency on the Pi: one or a few static JS modules (Lit from HA's
  own frontend is not importable — use plain web components or a vendored small lib).

## Constraints

- Nothing heavy on the Pi (RPi 3B+, ±150 MB free): no indexing, lazy browsing, no
  polling, small JS.
- Test only on gaia (local HA dev instance at ~/Workspace/ha-dev); no playback tests on
  the real speakers — tests assert the calls HA makes; Gert tests playing himself.
- Release: tarball + sha256 to ~/releases on the Pi, Dutch install note via the
  agent-bridge; the Pi agent installs at a moment Gert agrees to.
- Gert's standard: TDD, 100 % line + branch coverage for the Python code (pytest.ini
  enforced), mypy --strict, ruff; frontend logic in testable modules with its own
  tests (node's built-in test runner + coverage) and an end-to-end check with
  screenshots in the browser pane.
- Author gert@pellin.be, no AI attribution in commits.

music_library 0.1.0 is withdrawn (the Pi removed its config entries); its files on the
Pi can be removed when media_queue is installed.
