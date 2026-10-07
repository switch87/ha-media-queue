"""The queue of one media player: pure list logic, no Home Assistant calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class Mode(StrEnum):
    """How new items enter the queue."""

    REPLACE = "replace"
    ADD = "add"
    NEXT = "next"
    PLAY = "play"


def _new_id() -> str:
    return uuid4().hex


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


@dataclass(frozen=True, slots=True, kw_only=True)
class QueueItem:
    """One playable item in a queue."""

    media_content_id: str
    media_content_type: str
    title: str
    media_class: str | None = None
    thumbnail: str | None = None
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
        start = len(self.items) if mode is Mode.ADD else self.next_position
        self.items[start:start] = new
        return AddResult(start=start, added=len(new), truncated=len(items) > room)

    def remove(self, index: int) -> QueueItem:
        """Remove the item at index and return it."""
        self._check(index)
        item = self.items.pop(index)
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
        """Remove every item."""
        self.items = []
        self.current = None
        self._gap = None

    def as_dict(self) -> dict[str, Any]:
        """Return the queue as JSON-serialisable data."""
        return {
            "items": [item.as_dict() for item in self.items],
            "current": self.current,
            "next": self._gap,
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
        return queue

    def _check(self, index: int) -> None:
        if not 0 <= index < len(self.items):
            raise IndexError(index)


def _follow(position: int, source: int, target: int) -> int:
    """Return where the item at position is after moving source to target."""
    if position == source:
        return target
    if source < position <= target:
        return position - 1
    if target <= position < source:
        return position + 1
    return position
