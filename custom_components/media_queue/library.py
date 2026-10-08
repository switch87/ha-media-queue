"""The playlist library: saved queues, shared by every player."""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, QUEUE_LIMIT, SAVE_DELAY
from .enrich import TagFile, TagReader, with_tags
from .model import QueueItem
from .tags import Tags, local_file

PLAYLIST_STORAGE_KEY = f"{DOMAIN}.playlists"
PLAYLIST_STORAGE_VERSION = 1
NAME_MAX = 100
# Items per playlist (a queue holds no more) and playlists in the library.
PLAYLIST_ITEMS = QUEUE_LIMIT
PLAYLISTS_MAX = 500


def _invalid(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def clean_name(name: Any) -> str:
    """Return the trimmed name, or raise when it is no usable name."""
    text = name.strip() if isinstance(name, str) else ""
    if not 0 < len(text) <= NAME_MAX:
        raise _invalid("invalid_name", max=str(NAME_MAX))
    return text


def _copies(items: list[QueueItem]) -> list[QueueItem]:
    """Return the items with new ids (a playlist owns its own items)."""
    return [dataclasses.replace(item, item_id=uuid4().hex) for item in items]


@dataclass(slots=True, kw_only=True)
class Playlist:
    """One saved playlist."""

    playlist_id: str
    name: str
    items: list[QueueItem]
    created: str
    updated: str

    def pick(self, item_id: str | None) -> list[QueueItem]:
        """Return every item, or only the one with item_id."""
        if item_id is None:
            return list(self.items)
        for item in self.items:
            if item.item_id == item_id:
                return [item]
        raise _invalid("unknown_item", item_id=item_id)

    def summary(self) -> dict[str, Any]:
        """Return what a list of playlists shows."""
        durations = [item.duration for item in self.items if item.duration]
        return {
            "id": self.playlist_id,
            "name": self.name,
            "count": len(self.items),
            "duration": float(sum(durations)) if durations else None,
            "created": self.created,
            "updated": self.updated,
        }

    def as_dict(self) -> dict[str, Any]:
        """Return the playlist with its items as JSON-serialisable data."""
        return {
            "id": self.playlist_id,
            "name": self.name,
            "items": [item.as_dict() for item in self.items],
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Playlist | None:
        """Return the playlist stored in data, or None when it is unusable."""
        if not isinstance(data, dict):
            return None
        fields = [data.get(key) for key in ("id", "name", "created", "updated")]
        raw_items = data.get("items")
        if not all(isinstance(value, str) for value in fields) or not isinstance(
            raw_items, list
        ):
            return None
        items = [
            item
            for raw in raw_items[:PLAYLIST_ITEMS]
            if (item := QueueItem.from_dict(raw)) is not None
        ]
        name = str(data["name"]).strip()
        if not items or not 0 < len(name) <= NAME_MAX:
            return None
        return cls(
            playlist_id=data["id"],
            name=name,
            items=items,
            created=data["created"],
            updated=data["updated"],
        )


class PlaylistLibrary:
    """All saved playlists of the installation and their storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the library; call async_load before use."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, PLAYLIST_STORAGE_VERSION, PLAYLIST_STORAGE_KEY
        )
        self._playlists: dict[str, Playlist] = {}
        # Completing tags: one round at a time; items whose file was read.
        self._tags = TagReader(hass, "playlists")
        self._read_ids: set[str] = set()
        self._repairing: asyncio.Task[None] | None = None
        self._again = False

    @property
    def count(self) -> int:
        """Return the number of playlists."""
        return len(self._playlists)

    @property
    def item_count(self) -> int:
        """Return the number of items in all playlists."""
        return sum(len(playlist.items) for playlist in self._playlists.values())

    async def async_load(self) -> None:
        """Restore the stored playlists (dropping what does not fit)."""
        data = await self._store.async_load()
        raw_list = data.get("playlists") if isinstance(data, dict) else None
        names: set[str] = set()
        for raw in raw_list if isinstance(raw_list, list) else []:
            playlist = Playlist.from_dict(raw)
            if (
                playlist is None
                or playlist.playlist_id in self._playlists
                or playlist.name.casefold() in names
            ):
                continue
            self._playlists[playlist.playlist_id] = playlist
            names.add(playlist.name.casefold())
        self.repair()

    async def async_unload(self) -> None:
        """Stop completing tags and write pending changes now."""
        if self._repairing is not None:
            self._repairing.cancel()
        await self._store.async_save(self._data())

    def summaries(self) -> list[dict[str, Any]]:
        """Return every playlist's summary, by name."""
        ordered = sorted(self._playlists.values(), key=lambda p: p.name.casefold())
        return [playlist.summary() for playlist in ordered]

    def get(self, playlist_id: str) -> Playlist:
        """Return the playlist with playlist_id."""
        if (playlist := self._playlists.get(playlist_id)) is None:
            raise _invalid("unknown_playlist", playlist=playlist_id)
        return playlist

    def named(self, name: str) -> Playlist:
        """Return the playlist called name (any case)."""
        if (playlist := self._by_name(name.strip())) is None:
            raise _invalid("unknown_playlist", playlist=name)
        return playlist

    def save(self, name: Any, items: list[QueueItem], *, overwrite: bool) -> Playlist:
        """Save items under name; an existing name only with overwrite."""
        name = clean_name(name)
        if not items:
            raise _invalid("playlist_empty")
        if len(items) > PLAYLIST_ITEMS:
            raise _invalid("playlist_too_long", limit=str(PLAYLIST_ITEMS))
        now = dt_util.utcnow().isoformat()
        existing = self._by_name(name)
        if existing is not None:
            if not overwrite:
                raise _invalid("playlist_exists", name=existing.name)
            existing.name = name
            existing.items = _copies(items)
            existing.updated = now
            self._changed()
            self.repair()
            return existing
        if len(self._playlists) >= PLAYLISTS_MAX:
            raise _invalid("too_many_playlists", limit=str(PLAYLISTS_MAX))
        playlist = Playlist(
            playlist_id=uuid4().hex,
            name=name,
            items=_copies(items),
            created=now,
            updated=now,
        )
        self._playlists[playlist.playlist_id] = playlist
        self._changed()
        self.repair()
        return playlist

    def rename(self, playlist_id: str, name: Any) -> None:
        """Give a playlist another name (not one of another playlist)."""
        playlist = self.get(playlist_id)
        name = clean_name(name)
        other = self._by_name(name)
        if other is not None and other is not playlist:
            raise _invalid("playlist_exists", name=other.name)
        playlist.name = name
        playlist.updated = dt_util.utcnow().isoformat()
        self._changed()

    def delete(self, playlist_id: str) -> None:
        """Remove a playlist."""
        self.get(playlist_id)
        del self._playlists[playlist_id]
        self._changed()

    def load(self, playlist_id: str, item_id: str | None) -> list[QueueItem]:
        """Return the items to put in a queue; complete missing tags later."""
        items = self.get(playlist_id).pick(item_id)
        self.repair()
        return items

    # ------------------------------------------------------------------- tags

    @callback
    def repair(self) -> None:
        """Read, in the background, the tags that playlist items lack.

        Items without an artist or a duration whose media id is a local file
        are read; a file that was read is not read again in this run (one
        without tags is not read at every save), a missing one (a share
        that is not mounted yet) is tried again at the next repair. One
        round at a time; a repair asked meanwhile adds a round.
        """
        if self._repairing is not None and not self._repairing.done():
            self._again = True
            return
        self._repairing = self.hass.async_create_background_task(
            self._async_repair(), f"{DOMAIN} playlist tags"
        )

    async def _async_repair(self) -> None:
        while True:
            self._again = False
            await self._tags.read(self._missing(), self)
            if not self._again:
                return

    def _missing(self) -> list[TagFile]:
        media_dirs = self.hass.config.media_dirs
        return [
            (item.item_id, *found)
            for playlist in self._playlists.values()
            for item in playlist.items
            if (item.artist is None or item.duration is None)
            and item.item_id not in self._read_ids
            and (found := local_file(media_dirs, item.media_content_id)) is not None
        ]

    def tag_ids(self) -> set[str]:
        """Return the ids of every playlist item (tag target)."""
        return {
            item.item_id
            for playlist in self._playlists.values()
            for item in playlist.items
        }

    def apply_tags(self, found: dict[str, Tags]) -> bool:
        """Put the tags on the playlist items they belong to."""
        self._read_ids.update(found)
        changed = False
        for playlist in self._playlists.values():
            for position, item in enumerate(playlist.items):
                if (tags := found.get(item.item_id)) is not None:
                    playlist.items[position] = with_tags(item, tags)
                    changed = True
        return changed

    def tags_changed(self) -> None:
        """Store the completed playlists (delayed, tag target)."""
        self._changed()

    def _by_name(self, name: str) -> Playlist | None:
        folded = name.casefold()
        for playlist in self._playlists.values():
            if playlist.name.casefold() == folded:
                return playlist
        return None

    def _changed(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def _data(self) -> dict[str, Any]:
        return {
            "playlists": [playlist.as_dict() for playlist in self._playlists.values()]
        }
