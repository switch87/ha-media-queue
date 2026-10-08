"""Tests for the listening history: what counts, the store, the top list."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.media_queue import history as history_module
from custom_components.media_queue.const import SAVE_DELAY
from custom_components.media_queue.history import (
    HISTORY_SAVE_DELAY,
    HISTORY_STORAGE_KEY,
    ListeningHistory,
    countable,
    played_enough,
)
from custom_components.media_queue.model import QueueItem

LOCAL = "media-source://media_source/local"


def _track(name: str, duration: float | None = 200.0, **extra: Any) -> QueueItem:
    return QueueItem(
        media_content_id=f"{LOCAL}/Album/{name}.mp3",
        media_content_type="audio/mpeg",
        title=name.upper(),
        duration=duration,
        **extra,
    )


@pytest.mark.parametrize(
    ("content_id", "duration", "expected"),
    [
        (f"{LOCAL}/Album/a.mp3", 200.0, True),
        ("media-source://dlna_dms/server/:track", 180.0, True),
        ("spotify:track:abc", 180.0, True),
        (f"{LOCAL}/Album/a.mp3", None, False),
        ("http://radio.example/stream", None, False),
        ("https://radio.example/stream.mp3", 180.0, False),
        ("HTTP://radio.example/stream.mp3", 180.0, False),
    ],
)
def test_only_real_tracks_count(
    content_id: str, duration: float | None, expected: bool
) -> None:
    """A known duration and no bare stream URL."""
    item = QueueItem(
        media_content_id=content_id,
        media_content_type="music",
        title="T",
        duration=duration,
    )
    assert countable(item) is expected


@pytest.mark.parametrize(
    ("seconds", "duration", "expected"),
    [
        (29.9, 300.0, False),
        (30.0, 300.0, True),
        (20.0, 40.0, True),  # half of a short track comes first
        (19.9, 40.0, False),
        (29.0, None, False),
        (30.0, None, True),
        (0.0, 0.0, False),
    ],
)
def test_played_enough(seconds: float, duration: float | None, expected: bool) -> None:
    """30 seconds or half the duration, whichever comes first."""
    assert played_enough(seconds, duration) is expected


async def _history(hass: HomeAssistant) -> ListeningHistory:
    history = ListeningHistory(hass)
    await history.async_load()
    return history


async def test_record_counts_and_orders(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Most played first; equal counts: the one played last first."""
    history = await _history(hass)
    freezer.move_to("2026-10-07 10:00:00+00:00")
    assert history.record(_track("a"))
    freezer.tick(timedelta(minutes=5))
    assert history.record(_track("b"))
    freezer.tick(timedelta(minutes=5))
    assert history.record(_track("a", artist="Band"))
    freezer.tick(timedelta(minutes=5))
    assert history.record(_track("c"))

    top = history.top(10)
    assert [entry.title for entry in top] == ["A", "C", "B"]
    assert top[0].count == 2
    assert top[0].artist == "Band"  # the latest that is known
    assert top[0].last_played == "2026-10-07T10:10:00+00:00"
    assert history.track_count == 3
    assert history.play_count == 4
    assert [entry.title for entry in history.top(1)] == ["A"]
    await history.async_unload()


async def test_known_details_are_kept_when_a_play_lacks_them(
    hass: HomeAssistant,
) -> None:
    """A later play with only a file name keeps the artist known before."""
    history = await _history(hass)
    history.record(_track("a", artist="Band", album="LP", thumbnail="/media/a.jpg"))
    history.record(_track("a"))
    entry = history.top(1)[0]
    assert (entry.artist, entry.album, entry.thumbnail) == (
        "Band",
        "LP",
        "/media/a.jpg",
    )
    await history.async_unload()


async def test_streams_are_not_recorded(hass: HomeAssistant) -> None:
    """Record ignores what is not a real track."""
    history = await _history(hass)
    assert not history.record(_track("radio", duration=None))
    assert history.track_count == 0
    await history.async_unload()


async def test_the_least_played_are_dropped_beyond_the_limit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """At most HISTORY_MAX tracks: the least and longest ago played go."""
    history = await _history(hass)
    with patch.object(history_module, "HISTORY_MAX", 2):
        history.record(_track("a"))
        history.record(_track("a"))
        freezer.tick(timedelta(minutes=1))
        history.record(_track("b"))
        freezer.tick(timedelta(minutes=1))
        history.record(_track("c"))
    assert [entry.title for entry in history.top(10)] == ["A", "C"]
    await history.async_unload()


async def test_items_have_stable_ids(hass: HomeAssistant) -> None:
    """The same track gets the same item id every time (loading one track)."""
    history = await _history(hass)
    history.record(_track("a"))
    first = history.top(1)[0].as_item()
    second = history.top(1)[0].as_item()
    assert first == second
    assert first.media_content_id == f"{LOCAL}/Album/a.mp3"
    assert (first.title, first.duration) == ("A", 200.0)
    assert len(first.item_id) == 32
    await history.async_unload()


async def test_writes_are_rare_and_flushed_at_a_stop(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """One write per HISTORY_SAVE_DELAY while playing; soon after a stop."""
    history = await _history(hass)
    history.record(_track("a"))
    freezer.tick(timedelta(seconds=HISTORY_SAVE_DELAY - 60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert HISTORY_STORAGE_KEY not in hass_storage

    history.record(_track("b"))  # does not postpone the pending write
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    stored = hass_storage[HISTORY_STORAGE_KEY]["data"]["tracks"]
    assert len(stored) == 2

    history.record(_track("c"))
    history.flush_soon()
    history.flush_soon()  # a soon write is pending already
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(hass_storage[HISTORY_STORAGE_KEY]["data"]["tracks"]) == 3
    await history.async_unload()


async def test_unload_writes_now(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Nothing is lost at a restart."""
    history = await _history(hass)
    history.record(_track("a"))
    await history.async_unload()
    stored = hass_storage[HISTORY_STORAGE_KEY]
    assert stored["version"] == 1
    entry = stored["data"]["tracks"][0]
    assert entry["media_content_id"] == f"{LOCAL}/Album/a.mp3"
    assert entry["count"] == 1


async def test_load_restores_and_skips_what_is_unusable(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Malformed entries are dropped, good ones restored."""
    good = {
        "media_content_id": f"{LOCAL}/Album/a.mp3",
        "media_content_type": "audio/mpeg",
        "title": "A",
        "artist": "Band",
        "album": None,
        "duration": 200.0,
        "thumbnail": None,
        "media_class": "music",
        "count": 3,
        "last_played": "2026-10-07T10:00:00+00:00",
    }
    hass_storage[HISTORY_STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": HISTORY_STORAGE_KEY,
        "data": {
            "tracks": [
                good,
                good,  # twice: once
                {**good, "media_content_id": "x", "count": 0},
                {**good, "media_content_id": "y", "count": True},
                {**good, "media_content_id": "z", "last_played": 5},
                {**good, "media_content_id": ""},
                {**good, "media_content_id": "w", "title": None},
                "nonsense",
            ]
        },
    }
    history = await _history(hass)
    assert history.track_count == 1
    entry = history.top(1)[0]
    assert (entry.title, entry.artist, entry.count) == ("A", "Band", 3)
    await history.async_unload()


@pytest.mark.parametrize("data", [None, [], {"tracks": "x"}])
async def test_load_tolerates_bad_data(
    hass: HomeAssistant, hass_storage: dict[str, Any], data: Any
) -> None:
    """Anything that is not a list of tracks is an empty history."""
    hass_storage[HISTORY_STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": HISTORY_STORAGE_KEY,
        "data": data,
    }
    history = await _history(hass)
    assert history.track_count == 0
    await history.async_unload()


async def test_reset_forgets_everything(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A reset empties the history and is written soon."""
    history = await _history(hass)
    history.record(_track("a"))
    history.reset()
    assert history.top(10) == []
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[HISTORY_STORAGE_KEY]["data"] == {"tracks": []}
    await history.async_unload()


async def test_entries_for_the_api(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The API gets plain dictionaries, most played first."""
    freezer.move_to("2026-10-07 10:00:00+00:00")
    history = await _history(hass)
    history.record(_track("a", artist="Band"))
    assert history.entries(5) == [
        {
            "media_content_id": f"{LOCAL}/Album/a.mp3",
            "media_content_type": "audio/mpeg",
            "title": "A",
            "artist": "Band",
            "album": None,
            "duration": 200.0,
            "thumbnail": None,
            "media_class": None,
            "count": 1,
            "last_played": "2026-10-07T10:00:00+00:00",
        }
    ]
    await history.async_unload()
