"""Tests for counting plays: what really played, on any player."""

from datetime import timedelta
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.media_queue.const import SAVE_DELAY
from custom_components.media_queue.history import HISTORY_STORAGE_KEY
from custom_components.media_queue.manager import QueueManager
from custom_components.media_queue.model import Mode, QueueItem, Repeat

from .common import PLAYER, PlayerLog, async_manager_with, async_setup_library, state

DURATION = 200


@pytest.fixture
async def log(hass: HomeAssistant, tmp_path: Path) -> PlayerLog:
    """Return a player that starts playing whatever it is asked to play."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    state(hass, "idle")

    def plays(call: ServiceCall) -> None:
        name = call.data["media_content_id"].split("?")[0].rsplit("/", 1)[-1]
        playing(hass, f"id-{name}")

    log.on_play = plays
    return log


def playing(
    hass: HomeAssistant, content_id: str | None, duration: float | None = DURATION
) -> None:
    """Report playing content_id from position 0 now."""
    attrs: dict[str, Any] = {
        "media_position": 0,
        "media_position_updated_at": dt_util.utcnow(),
    }
    if duration is not None:
        attrs["media_duration"] = duration
    state(hass, "playing", content_id, **attrs)


def keep(hass: HomeAssistant, value: str) -> None:
    """Change only the state value, keeping the attributes."""
    current = hass.states.get(PLAYER)
    assert current is not None
    hass.states.async_set(PLAYER, value, current.attributes)


async def _after(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float, value: str
) -> None:
    freezer.tick(timedelta(seconds=seconds))
    keep(hass, value)
    await hass.async_block_till_done()


async def _started(hass: HomeAssistant, *titles: str) -> QueueManager:
    manager = await async_manager_with(hass, *titles)
    await manager.controller(PLAYER).async_play(0)
    await hass.async_block_till_done()
    return manager


def _counts(manager: QueueManager) -> dict[str, int]:
    return {play.title: play.count for play in manager.history.top(100)}


async def test_a_stop_after_30_seconds_counts(
    hass: HomeAssistant,
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """30 s of playing count; the stop writes the history soon."""
    manager = await _started(hass, "a", "b")
    await _after(hass, freezer, 31, "idle")

    assert _counts(manager) == {"a": 1}
    # The player told the duration; the file-name item had none.
    assert manager.history.top(1)[0].duration == DURATION
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(hass_storage[HISTORY_STORAGE_KEY]["data"]["tracks"]) == 1
    await manager.async_unload()


async def test_a_stop_before_30_seconds_does_not_count(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """A skip or stop early on is no play."""
    manager = await _started(hass, "a", "b")
    await _after(hass, freezer, 20, "idle")
    assert _counts(manager) == {}
    await manager.async_unload()


async def test_half_of_a_short_track_counts(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Half the duration counts when that comes before 30 s."""
    manager = await async_manager_with(hass, "a")
    log.on_play = lambda call: playing(hass, "id-a.mp3", duration=40)
    await manager.controller(PLAYER).async_play(0)
    await hass.async_block_till_done()
    await _after(hass, freezer, 21, "paused")
    assert _counts(manager) == {"a": 1}
    await manager.async_unload()


async def test_pauses_add_up_and_count_once(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Time paused does not count; the playing time adds up; one play."""
    manager = await _started(hass, "a")
    await _after(hass, freezer, 20, "paused")
    freezer.tick(timedelta(minutes=10))  # paused: not playing
    keep(hass, "playing")
    await hass.async_block_till_done()
    assert _counts(manager) == {}
    await _after(hass, freezer, 15, "paused")
    assert _counts(manager) == {"a": 1}
    keep(hass, "playing")
    await hass.async_block_till_done()
    await _after(hass, freezer, 40, "idle")
    assert _counts(manager) == {"a": 1}
    await manager.async_unload()


async def test_a_natural_end_counts_and_the_next_skipped_early_does_not(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """The ended item counts once; the next, skipped after 10 s, does not."""
    manager = await _started(hass, "a", "b", "c")
    controller = manager.controller(PLAYER)
    await _after(hass, freezer, DURATION, "idle")
    await hass.async_block_till_done()
    assert log.played == ["a.mp3", "b.mp3"]

    freezer.tick(timedelta(seconds=10))
    await controller.async_next()
    await hass.async_block_till_done()
    assert log.played == ["a.mp3", "b.mp3", "c.mp3"]
    assert _counts(manager) == {"a": 1}

    freezer.tick(timedelta(seconds=35))  # skipping after 35 s: a play
    await controller.async_previous()
    await hass.async_block_till_done()
    assert _counts(manager) == {"a": 1, "c": 1}
    await manager.async_unload()


async def test_repeat_one_counts_every_repetition(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Each time the item plays again it is a new play."""
    manager = await _started(hass, "a")
    manager.controller(PLAYER).set_repeat(Repeat.ONE)
    await _after(hass, freezer, DURATION, "idle")
    await hass.async_block_till_done()
    await _after(hass, freezer, DURATION, "idle")
    await hass.async_block_till_done()
    assert _counts(manager) == {"a": 2}
    await manager.async_unload()


async def test_streams_never_count(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """A radio stream (a URL without a duration) is never counted."""
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    radio = QueueItem(
        media_content_id="http://radio.example/stream",
        media_content_type="music",
        title="Radio",
    )
    log.on_play = lambda call: playing(hass, "http://radio.example/stream", None)
    await controller.async_add_items([radio], Mode.REPLACE)
    await hass.async_block_till_done()
    await _after(hass, freezer, 3600, "idle")
    assert _counts(manager) == {}
    await manager.async_unload()


async def test_playing_something_else_counts_what_played(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Another app taking over after 40 s: the item played, it counts."""
    manager = await _started(hass, "a", "b")
    freezer.tick(timedelta(seconds=40))
    playing(hass, "something-else")
    await hass.async_block_till_done()
    assert _counts(manager) == {"a": 1}
    await manager.async_unload()


async def test_the_end_of_the_queue_writes_soon(
    hass: HomeAssistant,
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """When the last item ends, the history is written within seconds."""
    manager = await _started(hass, "a")
    await _after(hass, freezer, DURATION, "idle")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[HISTORY_STORAGE_KEY]["data"]["tracks"][0]["count"] == 1
    await manager.async_unload()


async def test_every_player_counts_into_one_history(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Plays on two players add up for the same track."""
    manager = await _started(hass, "a")
    await _after(hass, freezer, 31, "idle")
    other = "media_player.kitchen"
    controller = manager.controller(other)
    controller.queue.add(
        list(manager.controller(PLAYER).queue.items), Mode.ADD, limit=9
    )

    def other_plays(call: ServiceCall) -> None:
        hass.states.async_set(
            other,
            "playing",
            {
                "media_content_id": "id-a.mp3",
                "media_duration": DURATION,
                "media_position": 0,
                "media_position_updated_at": dt_util.utcnow(),
            },
        )

    log.on_play = other_plays
    await controller.async_play(0)
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=31))
    current = hass.states.get(other)
    assert current is not None
    hass.states.async_set(other, "idle", current.attributes)
    await hass.async_block_till_done()
    assert _counts(manager) == {"a": 2}
    await manager.async_unload()
