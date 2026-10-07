"""The queue of one media player: pure list logic, no Home Assistant calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
import random
from typing import Any
from uuid import uuid4


class Mode(StrEnum):
    """How new items enter the queue."""

    REPLACE = "replace"
    ADD = "add"
    NEXT = "next"
    PLAY = "play"


class Repeat(StrEnum):
    """What happens at the end of an item or of the queue."""

    OFF = "off"
    ALL = "all"
    ONE = "one"


def _new_id() -> str:
    return uuid4().hex


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _duration(value: Any) -> float | None:
    """Return a positive finite number of seconds, else None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


@dataclass(frozen=True, slots=True, kw_only=True)
class QueueItem:
    """One playable item in a queue."""

    media_content_id: str
    media_content_type: str
    title: str
    media_class: str | None = None
    thumbnail: str | None = None
    artist: str | None = None
    album: str | None = None
    duration: float | None = None
    item_id: str = field(default_factory=_new_id)

    def as_dict(self) -> dict[str, Any]:
        """Return the item as JSON-serialisable data."""
        return {
            "id": self.item_id,
            "media_content_id": self.media_content_id,
            "media_content_type": self.media_content_type,
            "title": self.title,
            "media_class": self.media_class,
            "thumbnail": self.thumbnail,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: Any) -> QueueItem | None:
        """Return the item stored in data, or None when it is malformed."""
        if not isinstance(data, dict):
            return None
        required = [
            data.get(key)
            for key in ("id", "media_content_id", "media_content_type", "title")
        ]
        if not all(isinstance(value, str) for value in required) or not required[1]:
            return None
        return cls(
            item_id=data["id"],
            media_content_id=data["media_content_id"],
            media_content_type=data["media_content_type"],
            title=data["title"],
            media_class=_optional_str(data.get("media_class")),
            thumbnail=_optional_str(data.get("thumbnail")),
            artist=_optional_str(data.get("artist")),
            album=_optional_str(data.get("album")),
            duration=_duration(data.get("duration")),
        )


@dataclass(frozen=True, slots=True)
class AddResult:
    """What an add did: where the new items start and whether some were cut."""

    start: int
    added: int
    truncated: bool


def _index(value: Any, upper: int) -> int | None:
    """Return value when it is an int in 0..upper, else None."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= upper else None


class Queue:
    """Items, the current item and, after removing it, where to continue.

    ``current`` is the index of the item that is (or was last) played.  When the
    current item is removed, ``_gap`` remembers the position of the item that
    plays next, so removing what plays now does not lose the place.
    """

    def __init__(self) -> None:
        """Create an empty queue."""
        self.items: list[QueueItem] = []
        self.current: int | None = None
        self._gap: int | None = None
        self.shuffle = False
        self.repeat = Repeat.OFF
        self.rng = random.Random()
        # While shuffled: the item ids in their unshuffled order.
        self._original: list[str] = []

    @property
    def upcoming(self) -> int | None:
        """Return the index the next button plays, None when unknown or none.

        With repeat all the queue wraps to the top; when shuffled it is mixed
        again first, so what comes then is not known yet.
        """
        position = self.next_position
        if position < len(self.items):
            return position
        if self.repeat is Repeat.ALL and self.items and not self.shuffle:
            return 0
        return None

    def set_shuffle(self, on: bool) -> bool:
        """Turn shuffle on or off; return whether it changed.

        On: the current item goes to the top (and stays current), the rest is
        mixed. Off: the remembered order returns; the current item, or else
        the item that plays next, stays where the queue is.
        """
        if on == self.shuffle:
            return False
        self.shuffle = on
        if on:
            self._original = [item.item_id for item in self.items]
            self._mix()
        else:
            self._unmix()
        return True

    def rewind(self, avoid: str | None = None) -> None:
        """Start again at the top; shuffled, mix again (avoid is not first)."""
        self.current = None
        self._gap = None
        if not self.shuffle:
            return
        self.rng.shuffle(self.items)
        if len(self.items) > 1 and self.items[0].item_id == avoid:
            swap = self.rng.randrange(1, len(self.items))
            self.items[0], self.items[swap] = self.items[swap], self.items[0]

    def _mix(self) -> None:
        if self.current is not None:
            playing = self.items.pop(self.current)
            self.rng.shuffle(self.items)
            self.items.insert(0, playing)
            self.current = 0
            return
        self.rng.shuffle(self.items)
        if self._gap is not None:
            self._gap = 0

    def _unmix(self) -> None:
        rank = {item_id: number for number, item_id in enumerate(self._original)}
        playing = self.items[self.current] if self.current is not None else None
        gap = self._gap
        following = (
            self.items[gap] if gap is not None and gap < len(self.items) else None
        )
        self.items.sort(key=lambda item: rank[item.item_id])
        self._original = []
        if playing is not None:
            self.current = self.index_of(playing.item_id)
        elif following is not None:
            self._gap = self.index_of(following.item_id)

    def _remember(self, new: list[QueueItem], mode: Mode) -> None:
        """Put new items in the unshuffled order where they would have gone."""
        ids = [item.item_id for item in new]
        if mode in (Mode.ADD, Mode.REPLACE):
            self._original.extend(ids)
            return
        if self.current is not None:
            at = self._original.index(self.items[self.current].item_id) + 1
        elif self.next_position < len(self.items):
            at = self._original.index(self.items[self.next_position].item_id)
        else:
            at = len(self._original)
        self._original[at:at] = ids

    @property
    def next_position(self) -> int:
        """Return the index that plays after the current one (may be len)."""
        if self.current is not None:
            return self.current + 1
        return self._gap if self._gap is not None else 0

    @property
    def previous_position(self) -> int | None:
        """Return the index of the item before the current one, at least 0."""
        if not self.items:
            return None
        position = self.current if self.current is not None else self.next_position
        return max(position - 1, 0)

    def index_of(self, item_id: str) -> int | None:
        """Return the position of the item with item_id, or None."""
        for index, item in enumerate(self.items):
            if item.item_id == item_id:
                return index
        return None

    def set_current(self, index: int) -> None:
        """Make index the current item."""
        self._check(index)
        self.current = index
        self._gap = None

    def add(self, items: list[QueueItem], mode: Mode, *, limit: int) -> AddResult:
        """Insert items as mode says, never growing beyond limit."""
        if mode is Mode.REPLACE:
            self.clear()
        room = max(limit - len(self.items), 0)
        new = items[:room]
        result = AddResult(
            start=len(self.items) if mode is Mode.ADD else self.next_position,
            added=len(new),
            truncated=len(items) > room,
        )
        if not self.shuffle:
            self.items[result.start : result.start] = new
            return result
        self._remember(new, mode)
        if mode is Mode.ADD:
            # Mixed into what comes after the current item.
            start = self.next_position
            for item in new:
                self.items.insert(self.rng.randint(start, len(self.items)), item)
            return AddResult(
                start=start, added=result.added, truncated=result.truncated
            )
        block = list(new)
        self.rng.shuffle(block)
        self.items[result.start : result.start] = block
        return result

    def remove(self, index: int) -> QueueItem:
        """Remove the item at index and return it."""
        self._check(index)
        item = self.items.pop(index)
        if self.shuffle:
            self._original.remove(item.item_id)
        if self.current is not None:
            if index == self.current:
                self.current = None
                self._gap = index
            elif index < self.current:
                self.current -= 1
        elif self._gap is not None and index < self._gap:
            self._gap -= 1
        return item

    def move(self, source: int, target: int) -> None:
        """Move the item at source to target; current stays on its item."""
        self._check(source)
        self._check(target)
        item = self.items.pop(source)
        self.items.insert(target, item)
        if self.current is not None:
            self.current = _follow(self.current, source, target)
        elif self._gap is not None:
            gap = self._gap - 1 if source < self._gap else self._gap
            self._gap = gap + 1 if target < gap else gap

    def clear(self) -> None:
        """Remove every item (shuffle and repeat stay as they are)."""
        self.items = []
        self.current = None
        self._gap = None
        self._original = []

    def as_dict(self) -> dict[str, Any]:
        """Return the queue as JSON-serialisable data."""
        return {
            "items": [item.as_dict() for item in self.items],
            "current": self.current,
            "next": self._gap,
            "shuffle": self.shuffle,
            "repeat": self.repeat.value,
            "original": list(self._original) if self.shuffle else None,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Queue:
        """Return the queue stored in data, repairing what does not fit."""
        queue = cls()
        if not isinstance(data, dict):
            return queue
        raw_items = data.get("items")
        if isinstance(raw_items, list):
            for raw in raw_items:
                if (item := QueueItem.from_dict(raw)) is not None:
                    queue.items.append(item)
        count = len(queue.items)
        queue.current = _index(data.get("current"), count - 1)
        if queue.current is None:
            queue._gap = _index(data.get("next"), count)
        repeat = data.get("repeat")
        queue.repeat = (
            Repeat(repeat) if repeat in tuple(r.value for r in Repeat) else Repeat.OFF
        )
        queue.shuffle = data.get("shuffle") is True
        if queue.shuffle:
            queue._original = _order(data.get("original"), queue.items)
        return queue

    def _check(self, index: int) -> None:
        if not 0 <= index < len(self.items):
            raise IndexError(index)


def _order(raw: Any, items: list[QueueItem]) -> list[str]:
    """Return the stored unshuffled order, repaired to hold every item once."""
    known = {item.item_id for item in items}
    order: list[str] = []
    seen: set[str] = set()
    for item_id in raw if isinstance(raw, list) else []:
        if isinstance(item_id, str) and item_id in known and item_id not in seen:
            order.append(item_id)
            seen.add(item_id)
    order.extend(item.item_id for item in items if item.item_id not in seen)
    return order


def _follow(position: int, source: int, target: int) -> int:
    """Return where the item at position is after moving source to target."""
    if position == source:
        return target
    if source < position <= target:
        return position - 1
    if target <= position < source:
        return position + 1
    return position
