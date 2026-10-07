"""Tests for the pure queue model."""

from typing import Any

import pytest

from custom_components.media_queue.model import Mode, Queue, QueueItem


def _items(*titles: str) -> list[QueueItem]:
    return [
        QueueItem(
            media_content_id=f"media-source://media_source/local/{title}.mp3",
            media_content_type="audio/mpeg",
            title=title,
        )
        for title in titles
    ]


def _titles(queue: Queue) -> list[str]:
    return [item.title for item in queue.items]


def _queue(*titles: str, current: int | None = None) -> Queue:
    queue = Queue()
    queue.add(_items(*titles), Mode.ADD, limit=100)
    if current is not None:
        queue.set_current(current)
    return queue


def test_items_get_unique_ids() -> None:
    """Every item has its own id, also for the same media."""
    first, second = _items("a", "a")
    assert first.item_id != second.item_id
    assert len(first.item_id) == 32


def test_add_to_empty_queue() -> None:
    """Adding appends and does not make anything current."""
    queue = Queue()
    result = queue.add(_items("a", "b"), Mode.ADD, limit=100)
    assert _titles(queue) == ["a", "b"]
    assert queue.current is None
    assert result.start == 0
    assert result.added == 2
    assert result.truncated is False


def test_add_appends_after_current() -> None:
    """Add puts the items at the end of the queue."""
    queue = _queue("a", "b", "c", current=0)
    result = queue.add(_items("x"), Mode.ADD, limit=100)
    assert _titles(queue) == ["a", "b", "c", "x"]
    assert result.start == 3
    assert queue.current == 0


def test_replace_clears_and_starts_at_zero() -> None:
    """Replace drops the old queue; the caller plays index 0."""
    queue = _queue("a", "b", current=1)
    result = queue.add(_items("x", "y"), Mode.REPLACE, limit=100)
    assert _titles(queue) == ["x", "y"]
    assert queue.current is None
    assert result.start == 0
    assert queue.next_position == 0


@pytest.mark.parametrize("mode", [Mode.NEXT, Mode.PLAY])
def test_next_and_play_insert_after_current(mode: Mode) -> None:
    """Play next / play insert right after the current item."""
    queue = _queue("a", "b", "c", current=1)
    result = queue.add(_items("x", "y"), mode, limit=100)
    assert _titles(queue) == ["a", "b", "x", "y", "c"]
    assert result.start == 2
    assert queue.current == 1


def test_next_without_current_inserts_at_front() -> None:
    """Nothing played yet: play next goes before everything."""
    queue = _queue("a", "b")
    result = queue.add(_items("x"), Mode.NEXT, limit=100)
    assert _titles(queue) == ["x", "a", "b"]
    assert result.start == 0


def test_limit_truncates_new_items() -> None:
    """The queue never grows beyond the limit; the result says so."""
    queue = _queue("a", "b")
    result = queue.add(_items("x", "y", "z"), Mode.ADD, limit=4)
    assert _titles(queue) == ["a", "b", "x", "y"]
    assert result.added == 2
    assert result.truncated is True


def test_limit_counts_from_empty_on_replace() -> None:
    """Replace may use the full limit."""
    queue = _queue("a", "b", "c")
    result = queue.add(_items("x", "y", "z"), Mode.REPLACE, limit=3)
    assert result.added == 3
    assert result.truncated is False


def test_full_queue_adds_nothing() -> None:
    """A full queue reports truncation and keeps its items."""
    queue = _queue("a", "b")
    result = queue.add(_items("x"), Mode.NEXT, limit=2)
    assert _titles(queue) == ["a", "b"]
    assert result.added == 0
    assert result.truncated is True


def test_set_current_validates() -> None:
    """Only existing indexes can become current."""
    queue = _queue("a")
    with pytest.raises(IndexError):
        queue.set_current(1)
    with pytest.raises(IndexError):
        queue.set_current(-1)


def test_next_and_previous_positions() -> None:
    """Next follows current; previous goes back, never below 0."""
    queue = _queue("a", "b", "c", current=1)
    assert queue.next_position == 2
    assert queue.previous_position == 0
    queue.set_current(0)
    assert queue.previous_position == 0
    assert Queue().previous_position is None


def test_previous_without_current_uses_the_gap() -> None:
    """After removing the current item, previous is the item before the gap."""
    queue = _queue("a", "b", "c", current=2)
    queue.remove(2)
    assert queue.previous_position == 1
    queue = _queue("a", "b", current=0)
    queue.remove(0)
    assert queue.previous_position == 0
    assert _queue("a").previous_position == 0


def test_remove_before_current_shifts_current() -> None:
    """Removing an earlier item keeps the same current item."""
    queue = _queue("a", "b", "c", current=2)
    removed = queue.remove(0)
    assert removed.title == "a"
    assert queue.current == 1
    assert queue.items[queue.current].title == "c"


def test_remove_after_current_keeps_current() -> None:
    """Removing a later item leaves current alone."""
    queue = _queue("a", "b", "c", current=0)
    queue.remove(2)
    assert queue.current == 0
    assert _titles(queue) == ["a", "b"]


def test_remove_current_keeps_what_comes_next() -> None:
    """The item after a removed current item still plays next."""
    queue = _queue("a", "b", "c", current=1)
    queue.remove(1)
    assert queue.current is None
    assert queue.next_position == 1
    assert queue.items[queue.next_position].title == "c"


def test_remove_moves_the_gap() -> None:
    """Removing items before the gap moves it; after it does not."""
    queue = _queue("a", "b", "c", "d", "e", current=2)
    queue.remove(2)
    queue.remove(0)
    assert queue.next_position == 1
    queue.remove(2)
    assert queue.next_position == 1
    assert _titles(queue) == ["b", "d"]


def test_insert_at_gap_plays_next() -> None:
    """Play next after removing the current item fills the gap."""
    queue = _queue("a", "b", "c", current=1)
    queue.remove(1)
    queue.add(_items("x"), Mode.NEXT, limit=100)
    assert _titles(queue) == ["a", "x", "c"]
    assert queue.next_position == 1


def test_add_after_removing_the_last_current_plays_next() -> None:
    """Items appended at the gap play next."""
    queue = _queue("a", "b", current=1)
    queue.remove(1)
    queue.add(_items("x"), Mode.ADD, limit=100)
    assert queue.next_position == 1
    assert queue.items[1].title == "x"


def test_remove_and_move_in_a_queue_never_played() -> None:
    """Without current or gap, the queue just changes order."""
    queue = _queue("a", "b", "c")
    queue.remove(0)
    queue.move(0, 1)
    assert _titles(queue) == ["c", "b"]
    assert queue.current is None
    assert queue.next_position == 0


def test_remove_validates_index() -> None:
    """Removing a missing index raises IndexError."""
    with pytest.raises(IndexError):
        _queue("a").remove(1)
    with pytest.raises(IndexError):
        _queue("a").remove(-1)


@pytest.mark.parametrize(
    ("source", "target", "titles", "current"),
    [
        (0, 2, ["b", "c", "a", "d"], 0),  # earlier item moved past current
        (3, 0, ["d", "a", "b", "c"], 2),  # later item moved before current
        (1, 3, ["a", "c", "d", "b"], 3),  # current itself moves
        (2, 3, ["a", "b", "d", "c"], 1),  # both after current
        (0, 0, ["a", "b", "c", "d"], 1),  # no-op
    ],
)
def test_move_keeps_current_on_its_item(
    source: int, target: int, titles: list[str], current: int
) -> None:
    """Moving items never changes which item is current."""
    queue = _queue("a", "b", "c", "d", current=1)
    queue.move(source, target)
    assert _titles(queue) == titles
    assert queue.current == current


@pytest.mark.parametrize(
    ("source", "target", "gap"),
    [
        (0, 3, 1),  # earlier item moved behind the gap
        (3, 0, 3),  # later item moved before the gap
        (3, 2, 2),  # dropped exactly at the gap: plays next
        (3, 1, 3),  # dropped before the gap
    ],
)
def test_move_shifts_the_gap(source: int, target: int, gap: int) -> None:
    """The gap left by a removed current item follows the moves."""
    queue = _queue("a", "b", "x", "c", "d", current=2)
    queue.remove(2)  # a b c d, gap at 2 (c plays next)
    queue.move(source, target)
    assert queue.next_position == gap


def test_move_validates_indexes() -> None:
    """Both indexes must exist."""
    queue = _queue("a", "b")
    for source, target in ((2, 0), (0, 2), (-1, 0), (0, -1)):
        with pytest.raises(IndexError):
            queue.move(source, target)


def test_clear() -> None:
    """Clear empties the queue and forgets the position."""
    queue = _queue("a", "b", current=1)
    queue.clear()
    assert queue.items == []
    assert queue.current is None
    assert queue.next_position == 0


def test_item_round_trip() -> None:
    """Items survive serialisation, including optional fields."""
    item = QueueItem(
        media_content_id="x",
        media_content_type="music",
        title="X",
        media_class="track",
        thumbnail="/t.jpg",
        item_id="abc",
    )
    assert QueueItem.from_dict(item.as_dict()) == item
    assert item.as_dict() == {
        "id": "abc",
        "media_content_id": "x",
        "media_content_type": "music",
        "title": "X",
        "media_class": "track",
        "thumbnail": "/t.jpg",
    }


@pytest.mark.parametrize(
    "data",
    [
        None,
        "x",
        {},
        {"id": "a", "media_content_id": 1, "media_content_type": "m", "title": "t"},
        {"id": "a", "media_content_id": "x", "media_content_type": None, "title": "t"},
        {"id": "a", "media_content_id": "x", "media_content_type": "m", "title": 3},
        {"id": 5, "media_content_id": "x", "media_content_type": "m", "title": "t"},
        {"id": "a", "media_content_id": "", "media_content_type": "m", "title": "t"},
    ],
)
def test_item_from_bad_data(data: Any) -> None:
    """Malformed stored items are dropped."""
    assert QueueItem.from_dict(data) is None


def test_item_from_dict_ignores_bad_optionals() -> None:
    """Optional fields of the wrong type become None."""
    item = QueueItem.from_dict(
        {
            "id": "a",
            "media_content_id": "x",
            "media_content_type": "m",
            "title": "t",
            "media_class": 3,
            "thumbnail": ["no"],
        }
    )
    assert item is not None
    assert item.media_class is None
    assert item.thumbnail is None


def test_queue_round_trip() -> None:
    """The queue with current and gap survives serialisation."""
    queue = _queue("a", "b", "c", current=1)
    restored = Queue.from_dict(queue.as_dict())
    assert _titles(restored) == ["a", "b", "c"]
    assert restored.current == 1
    queue.remove(1)
    restored = Queue.from_dict(queue.as_dict())
    assert restored.current is None
    assert restored.next_position == 1


@pytest.mark.parametrize(
    ("data", "titles", "current", "next_position"),
    [
        (None, [], None, 0),
        ({"items": "x"}, [], None, 0),
        (
            {
                "items": [
                    {
                        "id": "a",
                        "media_content_id": "x",
                        "media_content_type": "m",
                        "title": "t",
                    },
                    "bad",
                ],
                "current": 4,
                "next": 9,
            },
            ["t"],
            None,
            0,
        ),
        (
            {
                "items": [
                    {
                        "id": "a",
                        "media_content_id": "x",
                        "media_content_type": "m",
                        "title": "t",
                    }
                ],
                "current": "0",
                "next": True,
            },
            ["t"],
            None,
            0,
        ),
        (
            {
                "items": [
                    {
                        "id": "a",
                        "media_content_id": "x",
                        "media_content_type": "m",
                        "title": "t",
                    }
                ],
                "next": 1,
            },
            ["t"],
            None,
            1,
        ),
    ],
)
def test_queue_from_bad_data(
    data: Any, titles: list[str], current: int | None, next_position: int
) -> None:
    """Stored data that does not fit is repaired, never fatal."""
    queue = Queue.from_dict(data)
    assert _titles(queue) == titles
    assert queue.current == current
    assert queue.next_position == next_position
