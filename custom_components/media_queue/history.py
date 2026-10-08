"""The listening history: how often each real track really played, on any player.

A play counts when a track played PLAY_SECONDS or half its duration,
whichever comes first (the controller measures it). Only real tracks are
counted: a known duration and a media id that is no bare http(s) URL, so
radio and other streams never are. Writes are rare: one delayed save per
HISTORY_SAVE_DELAY while music plays, a soon save when a player stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SAVE_DELAY
from .model import QueueItem

HISTORY_STORAGE_KEY = f"{DOMAIN}.history"
HISTORY_STORAGE_VERSION = 1
# Seconds between writes while music plays (SD cards), tracks remembered.
HISTORY_SAVE_DELAY = 300
HISTORY_MAX = 2000
# A play counts after this many seconds, or half the duration if that is less.
PLAY_SECONDS = 30.0

_STREAM_SCHEMES = ("http://", "https://")


def countable(item: QueueItem) -> bool:
    """Return whether item is a real track (not a stream or radio)."""
    return item.duration is not None and not item.media_content_id.lower().startswith(
        _STREAM_SCHEMES
    )


def played_enough(seconds: float, duration: float | None) -> bool:
    """Return whether seconds of playing count as a play."""
    if seconds <= 0:
        return False
    return seconds >= PLAY_SECONDS or (duration is not None and seconds >= duration / 2)


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


@dataclass(slots=True, kw_only=True)
class Play:
    """One track of the history and how often it played."""

    media_content_id: str
    media_content_type: str
    title: str
    artist: str | None
    album: str | None
    duration: float | None
    thumbnail: str | None
    media_class: str | None
    count: int
    last_played: str

    def as_item(self) -> QueueItem:
        """Return the track as a queue item; its id follows from the media id."""
        return QueueItem(
            item_id=uuid5(NAMESPACE_URL, self.media_content_id).hex,
            media_content_id=self.media_content_id,
            media_content_type=self.media_content_type,
            title=self.title,
            artist=self.artist,
            album=self.album,
            duration=self.duration,
            thumbnail=self.thumbnail,
            media_class=self.media_class,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the entry as JSON-serialisable data."""
        return {
            "media_content_id": self.media_content_id,
            "media_content_type": self.media_content_type,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "media_class": self.media_class,
            "count": self.count,
            "last_played": self.last_played,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Play | None:
        """Return the entry stored in data, or None when it is unusable."""
        if not isinstance(data, dict):
            return None
        item = QueueItem.from_dict({**data, "id": ""})
        count = data.get("count")
        last = data.get("last_played")
        if (
            item is None
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
            or not isinstance(last, str)
        ):
            return None
        return cls(
            media_content_id=item.media_content_id,
            media_content_type=item.media_content_type,
            title=item.title,
            artist=item.artist,
            album=item.album,
            duration=item.duration,
            thumbnail=item.thumbnail,
            media_class=_text(data.get("media_class")),
            count=count,
            last_played=last,
        )


def _rank(play: Play) -> tuple[int, str]:
    return (play.count, play.last_played)


class ListeningHistory:
    """Play counts of every real track, stored with rare writes."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the history; call async_load before use."""
        self._store: Store[dict[str, Any]] = Store(
            hass, HISTORY_STORAGE_VERSION, HISTORY_STORAGE_KEY
        )
        self._plays: dict[str, Play] = {}
        # When the pending write is due (None: nothing pending).
        self._due: datetime | None = None

    @property
    def track_count(self) -> int:
        """Return the number of tracks in the history."""
        return len(self._plays)

    @property
    def play_count(self) -> int:
        """Return the number of plays of all tracks."""
        return sum(play.count for play in self._plays.values())

    async def async_load(self) -> None:
        """Restore the stored history (dropping what does not fit)."""
        data = await self._store.async_load()
        tracks = data.get("tracks") if isinstance(data, dict) else None
        for raw in tracks if isinstance(tracks, list) else []:
            play = Play.from_dict(raw)
            if play is not None and play.media_content_id not in self._plays:
                self._plays[play.media_content_id] = play

    async def async_unload(self) -> None:
        """Write the history now."""
        await self._store.async_save(self._data())

    @callback
    def record(self, item: QueueItem) -> bool:
        """Count one play of item; return whether it was counted."""
        if not countable(item):
            return False
        now = dt_util.utcnow().isoformat()
        play = self._plays.get(item.media_content_id)
        if play is None:
            self._plays[item.media_content_id] = Play(
                media_content_id=item.media_content_id,
                media_content_type=item.media_content_type,
                title=item.title,
                artist=item.artist,
                album=item.album,
                duration=item.duration,
                thumbnail=item.thumbnail,
                media_class=item.media_class,
                count=1,
                last_played=now,
            )
            self._prune()
        else:
            play.count += 1
            play.last_played = now
            play.title = item.title
            play.media_content_type = item.media_content_type
            play.duration = item.duration
            play.artist = item.artist or play.artist
            play.album = item.album or play.album
            play.thumbnail = item.thumbnail or play.thumbnail
            play.media_class = item.media_class or play.media_class
        self._save_within(HISTORY_SAVE_DELAY)
        return True

    def top(self, limit: int) -> list[Play]:
        """Return the most played tracks, the last played first among equals."""
        return sorted(self._plays.values(), key=_rank, reverse=True)[:limit]

    def entries(self, limit: int) -> list[dict[str, Any]]:
        """Return the top tracks as data for the API."""
        return [play.as_dict() for play in self.top(limit)]

    @callback
    def reset(self) -> None:
        """Forget every play."""
        self._plays.clear()
        self._save_within(SAVE_DELAY)

    @callback
    def flush_soon(self) -> None:
        """Write soon (a player stopped), unless a write is due sooner."""
        self._save_within(SAVE_DELAY)

    def _prune(self) -> None:
        if len(self._plays) <= HISTORY_MAX:
            return
        for play in sorted(self._plays.values(), key=_rank)[
            : len(self._plays) - HISTORY_MAX
        ]:
            del self._plays[play.media_content_id]

    def _save_within(self, delay: int) -> None:
        """Make sure a write happens within delay seconds, never postponing."""
        now = dt_util.utcnow()
        due = now + timedelta(seconds=delay)
        if self._due is not None and now < self._due <= due:
            return
        self._store.async_delay_save(self._data, delay)
        self._due = due

    def _data(self) -> dict[str, Any]:
        return {"tracks": [play.as_dict() for play in self._plays.values()]}
