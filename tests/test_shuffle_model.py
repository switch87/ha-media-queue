"""Tests for shuffle and repeat in the pure queue model."""

import random
from typing import Any

import pytest

from custom_components.media_queue.model import Mode, Queue, QueueItem, Repeat


class Unshuffled(random.Random):
    """A random source whose shuffle leaves the order as it is."""

    def shuffle(self, x: list[Any]) -> None:  # type: ignore[override]
        """Keep x as it is."""


def _items(*titles: str) -> list[QueueItem]:
    return [
        QueueItem(
            media_content_id=f"media-source://media_source/local/{title}.mp3",
            media_content_type="audio/mpeg",
            title=title,
            item_id=f"id-{title}",
        )
        for title in titles
    ]


def _titles(queue: Queue) -> list[str]:
    return [item.title for item in queue.items]


def _queue(*titles: str, current: int | None = None, seed: int = 1) -> Queue:
    queue = Queue()
    queue.rng = random.Random(seed)
    queue.add(_items(*titles), Mode.ADD, limit=100)
    if current is not None:
        queue.set_current(current)
    return queue


TEN = tuple("abcdefghij")


def test_defaults() -> None:
    """A new queue plays in order and does not repeat."""
    queue = Queue()
    assert queue.shuffle is False
    assert queue.repeat is Repeat.OFF
    assert [r.value for r in Repeat] == ["off", "all", "one"]


def test_shuffle_on_keeps_the_current_item_on_top() -> None:
    """The current item moves to the top and stays current; the rest is mixed."""
    queue = _queue(*TEN, current=4)

    assert queue.set_shuffle(True) is True

    assert queue.shuffle is True
    assert queue.current == 0
    assert _titles(queue)[0] == "e"
    assert sorted(_titles(queue)) == list(TEN)
    assert _titles(queue)[1:] != [t for t in TEN if t != "e"]
    assert queue.set_shuffle(True) is False


def test_shuffle_on_without_current_mixes_everything() -> None:
    """Never played: the whole queue is mixed and the top plays next."""
    queue = _queue(*TEN)
    queue.set_shuffle(True)
    assert queue.current is None
    assert sorted(_titles(queue)) == list(TEN)
    assert _titles(queue) != list(TEN)
    assert queue.next_position == 0


def test_shuffle_on_after_removing_the_current_item() -> None:
    """With a gap (current removed) the top of the mix plays next."""
    queue = _queue(*TEN, current=3)
    queue.remove(3)
    queue.set_shuffle(True)
    assert queue.current is None
    assert queue.next_position == 0
    assert sorted(_titles(queue)) == sorted(t for t in TEN if t != "d")


def test_shuffle_off_restores_the_order_and_keeps_current() -> None:
    """Back in album order; the item that plays stays current."""
    queue = _queue(*TEN, current=2)
    queue.set_shuffle(True)
    queue.set_current(5)
    playing = queue.items[5].title

    assert queue.set_shuffle(False) is True

    assert queue.shuffle is False
    assert _titles(queue) == list(TEN)
    assert queue.items[queue.current or 0].title == playing
    assert queue.set_shuffle(False) is False


def test_shuffle_off_keeps_what_plays_next() -> None:
    """Without a current item the item that was next stays next."""
    queue = _queue(*TEN, current=0)
    queue.set_shuffle(True)
    queue.remove(0)  # the gap is at 0: items[0] plays next
    following = queue.items[0].title
    queue.set_shuffle(False)
    assert queue.current is None
    assert queue.items[queue.next_position].title == following


def test_shuffle_off_with_the_gap_at_the_end() -> None:
    """Nothing left to play next stays so."""
    queue = _queue("a", "b", current=1)
    queue.set_shuffle(True)  # b (current) on top, then a
    queue.set_current(1)
    queue.remove(1)  # a was current and last: the gap is at the end
    assert queue.next_position == 1
    queue.set_shuffle(False)
    assert queue.next_position == 1


def test_shuffle_off_without_any_position() -> None:
    """A queue never played stays without a current item."""
    queue = _queue(*TEN)
    queue.set_shuffle(True)
    queue.set_shuffle(False)
    assert _titles(queue) == list(TEN)
    assert queue.current is None
    assert queue.next_position == 0


def test_add_while_shuffled_mixes_new_items_into_what_comes() -> None:
    """Add scatters the new items after the current one; the order remembers."""
    queue = _queue(*TEN, current=0)
    queue.set_shuffle(True)
    before = _titles(queue)
    result = queue.add(_items("x", "y", "z"), Mode.ADD, limit=100)

    assert result.added == 3
    assert result.start == 1
    assert queue.current == 0
    assert _titles(queue)[0] == before[0]
    assert [t for t in _titles(queue) if t not in "xyz"] == before
    assert set(_titles(queue)[1:]) >= {"x", "y", "z"}
    assert _titles(queue)[-3:] != ["x", "y", "z"]
    queue.set_shuffle(False)
    assert _titles(queue) == [*TEN, "x", "y", "z"]


def test_add_while_shuffled_without_current() -> None:
    """Never played: the new items may land anywhere."""
    queue = _queue("a", "b")
    queue.set_shuffle(True)
    queue.add(_items("x"), Mode.ADD, limit=100)
    assert sorted(_titles(queue)) == ["a", "b", "x"]
    queue.set_shuffle(False)
    assert _titles(queue) == ["a", "b", "x"]


@pytest.mark.parametrize("mode", [Mode.NEXT, Mode.PLAY])
def test_next_while_shuffled_comes_right_after_current(mode: Mode) -> None:
    """The new block follows the current item, mixed among itself."""
    queue = _queue(*TEN, current=3)
    queue.set_shuffle(True)
    result = queue.add(_items("p", "q", "r", "s", "t", "u"), mode, limit=100)
    assert result.start == 1
    assert sorted(_titles(queue)[1:7]) == ["p", "q", "r", "s", "t", "u"]
    assert _titles(queue)[1:7] != ["p", "q", "r", "s", "t", "u"]
    queue.set_shuffle(False)
    assert _titles(queue) == [
        "a",
        "b",
        "c",
        "d",
        "p",
        "q",
        "r",
        "s",
        "t",
        "u",
        *TEN[4:],
    ]


def test_next_while_shuffled_without_current() -> None:
    """Without current, the block goes before what plays next, also in order."""
    queue = _queue("a", "b", "c", current=1)
    queue.set_shuffle(True)
    queue.rng = Unshuffled()
    queue.remove(0)  # b was current (on top); the gap is at 0
    following = queue.items[0].title
    queue.add(_items("x"), Mode.NEXT, limit=100)
    assert _titles(queue)[0] == "x"
    queue.set_shuffle(False)
    titles = _titles(queue)
    assert titles.index("x") == titles.index(following) - 1


def test_next_while_shuffled_with_nothing_left() -> None:
    """With nothing left to play, the block goes to the end of the order."""
    queue = _queue("a", "b", current=1)
    queue.set_shuffle(True)
    queue.remove(0)
    queue.remove(0)  # empty, the gap at 0 == len
    queue.add(_items("x"), Mode.NEXT, limit=100)
    queue.set_shuffle(False)
    assert _titles(queue) == ["x"]


def test_replace_while_shuffled() -> None:
    """Replace mixes the new items and remembers their own order."""
    queue = _queue("a", "b", current=0)
    queue.set_shuffle(True)
    queue.add(_items(*TEN), Mode.REPLACE, limit=100)
    assert queue.shuffle is True
    assert sorted(_titles(queue)) == list(TEN)
    assert _titles(queue) != list(TEN)
    queue.set_shuffle(False)
    assert _titles(queue) == list(TEN)


def test_remove_and_move_while_shuffled() -> None:
    """Removed items leave the remembered order; moving only changes play order."""
    queue = _queue(*TEN, current=0)
    queue.set_shuffle(True)
    queue.remove(queue.index_of("id-c") or 0)
    queue.move(len(queue.items) - 1, 1)
    queue.set_shuffle(False)
    assert _titles(queue) == [t for t in TEN if t != "c"]


def test_clear_keeps_the_settings() -> None:
    """Shuffle and repeat belong to the player, not to the items."""
    queue = _queue("a", "b", current=0)
    queue.set_shuffle(True)
    queue.repeat = Repeat.ALL
    queue.clear()
    assert queue.shuffle is True
    assert queue.repeat is Repeat.ALL
    queue.add(_items("x", "y"), Mode.ADD, limit=100)
    queue.set_shuffle(False)
    assert sorted(_titles(queue)) == ["x", "y"]


def test_rewind_in_order() -> None:
    """Starting again without shuffle: the top plays next, the order stays."""
    queue = _queue("a", "b", "c", current=2)
    queue.rewind()
    assert queue.current is None
    assert queue.next_position == 0
    assert _titles(queue) == ["a", "b", "c"]


def test_rewind_shuffled_never_repeats_the_last_item_first() -> None:
    """A new mix; the item that just played does not come first again."""
    queue = _queue("a", "b", "c", current=0)
    queue.set_shuffle(True)
    last = queue.items[0]
    queue.rng = Unshuffled()  # the mix would keep it on top
    queue.rewind(avoid=last.item_id)
    assert queue.items[0] != last
    assert queue.next_position == 0
    assert sorted(_titles(queue)) == ["a", "b", "c"]


def test_rewind_shuffled_mixes_again() -> None:
    """With shuffle on the queue is mixed again."""
    queue = _queue(*TEN, current=0)
    queue.set_shuffle(True)
    before = _titles(queue)
    queue.rewind(avoid="unknown")
    assert _titles(queue) != before
    assert sorted(_titles(queue)) == list(TEN)


def test_rewind_shuffled_single_item() -> None:
    """One item: it is the first again."""
    queue = _queue("a", current=0)
    queue.set_shuffle(True)
    queue.rewind(avoid="id-a")
    assert _titles(queue) == ["a"]


@pytest.mark.parametrize(
    ("titles", "current", "repeat", "shuffle", "upcoming"),
    [
        ((), None, Repeat.ALL, False, None),
        (("a", "b"), 0, Repeat.OFF, False, 1),
        (("a", "b"), 1, Repeat.OFF, False, None),
        (("a", "b"), 1, Repeat.ONE, False, None),
        (("a", "b"), 1, Repeat.ALL, False, 0),
        (("a", "b"), 1, Repeat.ALL, True, None),
    ],
)
def test_upcoming(
    titles: tuple[str, ...],
    current: int | None,
    repeat: Repeat,
    shuffle: bool,
    upcoming: int | None,
) -> None:
    """What the next button plays: wraps for repeat all (unknown when mixed)."""
    queue = _queue(*titles, current=current)
    if shuffle:
        queue.set_shuffle(True)
        queue.set_current(len(titles) - 1)
    queue.repeat = repeat
    assert queue.upcoming == upcoming


def test_round_trip_with_settings() -> None:
    """Shuffle, repeat and the remembered order survive serialisation."""
    queue = _queue(*TEN, current=2)
    queue.set_shuffle(True)
    queue.repeat = Repeat.ONE
    data = queue.as_dict()
    assert data["shuffle"] is True
    assert data["repeat"] == "one"
    assert data["original"] == [f"id-{t}" for t in TEN]

    restored = Queue.from_dict(data)
    assert restored.shuffle is True
    assert restored.repeat is Repeat.ONE
    assert _titles(restored) == _titles(queue)
    restored.set_shuffle(False)
    assert _titles(restored) == list(TEN)
    assert Queue().as_dict()["original"] is None


def _stored(**extra: Any) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": f"id-{t}",
                "media_content_id": t,
                "media_content_type": "m",
                "title": t,
            }
            for t in "abc"
        ],
        **extra,
    }


@pytest.mark.parametrize(
    ("extra", "shuffle", "repeat", "unshuffled"),
    [
        ({}, False, Repeat.OFF, ["a", "b", "c"]),
        ({"shuffle": "yes", "repeat": "twice"}, False, Repeat.OFF, ["a", "b", "c"]),
        ({"shuffle": True, "repeat": "all"}, True, Repeat.ALL, ["a", "b", "c"]),
        (
            {"shuffle": True, "original": ["id-c", "x", 3, "id-c", "id-a"]},
            True,
            Repeat.OFF,
            ["c", "a", "b"],
        ),
        ({"shuffle": True, "original": "id-a"}, True, Repeat.OFF, ["a", "b", "c"]),
        ({"shuffle": False, "original": ["id-c"]}, False, Repeat.OFF, ["a", "b", "c"]),
    ],
)
def test_settings_from_bad_data(
    extra: dict[str, Any], shuffle: bool, repeat: Repeat, unshuffled: list[str]
) -> None:
    """Stored settings that do not fit are repaired; the order is completed."""
    queue = Queue.from_dict(_stored(**extra))
    assert queue.shuffle is shuffle
    assert queue.repeat is repeat
    queue.set_shuffle(False)
    assert _titles(queue) == unshuffled
