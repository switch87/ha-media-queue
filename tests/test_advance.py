"""Tests for following the player and advancing at the end of an item."""

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.media_queue.const import STORAGE_KEY
from custom_components.media_queue.controller import (
    STARTING_TIMEOUT,
    Phase,
    QueueController,
)
from custom_components.media_queue.manager import QueueManager

from .common import (
    PLAYER,
    PlayerLog,
    async_manager_with,
    async_setup_library,
    state,
    track,
)

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


def playing(hass: HomeAssistant, content_id: str | None, **attrs: Any) -> None:
    """Report playing content_id from position 0 now, unless attrs say else."""
    data: dict[str, Any] = {
        "media_duration": DURATION,
        "media_position": 0,
        "media_position_updated_at": dt_util.utcnow(),
    }
    data.update(attrs)
    state(hass, "playing", content_id, **data)


def _phase(controller: QueueController) -> Phase:
    """Return the phase (a call, so mypy does not narrow it between asserts)."""
    return controller.phase


def keep(hass: HomeAssistant, value: str) -> None:
    """Change only the state value, keeping the attributes (like players do)."""
    current = hass.states.get(PLAYER)
    assert current is not None
    hass.states.async_set(PLAYER, value, current.attributes)


async def _started(hass: HomeAssistant, *titles: str) -> QueueManager:
    manager = await async_manager_with(hass, *titles)
    await manager.controller(PLAYER).async_play(0)
    await hass.async_block_till_done()
    return manager


async def _end(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, value: str = "idle"
) -> None:
    freezer.tick(timedelta(seconds=DURATION))
    keep(hass, value)
    await hass.async_block_till_done()


@pytest.mark.parametrize("end_state", ["idle", "off", "on", "standby"])
async def test_natural_end_plays_next(
    hass: HomeAssistant,
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
    end_state: str,
) -> None:
    """Stopping at the end of the item, in any stopped state, plays the next."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    assert _phase(controller) is Phase.PLAYING
    assert controller.fingerprint == "id-a.mp3"

    await _end(hass, freezer, end_state)

    assert log.played == ["a.mp3", "b.mp3"]
    assert controller.queue.current == 1
    assert _phase(controller) is Phase.PLAYING
    assert controller.fingerprint == "id-b.mp3"
    await manager.async_unload()


async def test_stop_before_the_end_does_not_advance(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Someone pressing stop elsewhere stops the queue; play resumes following."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)

    freezer.tick(timedelta(seconds=30))
    keep(hass, "idle")
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STOPPED
    assert log.played == ["a.mp3"]

    playing(hass, "id-a.mp3")  # play pressed on the player: same item again
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING

    await _end(hass, freezer)
    assert log.played == ["a.mp3", "b.mp3"]
    await manager.async_unload()


async def test_pause_keeps_following_and_pause_at_end_advances(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """A pause halfway is no end; players that pause at the end do advance."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)

    freezer.tick(timedelta(seconds=50))
    keep(hass, "paused")
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING
    assert log.played == ["a.mp3"]

    freezer.tick(timedelta(seconds=500))
    playing(hass, "id-a.mp3", media_position=50)
    await hass.async_block_till_done()

    await _end(hass, freezer, "paused")
    assert log.played == ["a.mp3", "b.mp3"]
    await manager.async_unload()


async def test_stream_without_duration_never_ends(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Radio has no duration: stopping it is never a natural end."""
    log.on_play = lambda call: playing(
        hass, "radio", media_duration=None, media_position=None
    )
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)

    freezer.tick(timedelta(hours=3))
    keep(hass, "idle")
    await hass.async_block_till_done()

    assert log.played == ["a.mp3"]
    assert _phase(controller) is Phase.STOPPED
    await manager.async_unload()


async def test_zero_duration_is_unknown(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Some players report duration 0 for streams."""
    log.on_play = lambda call: playing(hass, "radio", media_duration=0)
    manager = await _started(hass, "a", "b")
    await _end(hass, freezer)
    assert log.played == ["a.mp3"]
    await manager.async_unload()


async def test_without_position_the_play_time_counts(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Players that report no position: time played (minus pauses) is used."""
    log.on_play = lambda call: playing(
        hass, call.data["media_content_id"], media_position=None
    )
    manager = await _started(hass, "a", "b", "c")
    controller = manager.controller(PLAYER)

    freezer.tick(timedelta(seconds=100))
    keep(hass, "paused")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1000))
    keep(hass, "playing")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=50))
    keep(hass, "idle")  # 150 s played of 200: stopped by someone
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STOPPED
    assert len(log.calls) == 1

    keep(hass, "playing")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=48))
    keep(hass, "idle")  # 198 s played: the end
    await hass.async_block_till_done()
    assert len(log.calls) == 2
    await manager.async_unload()


async def test_position_reported_as_text(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Positions set through the REST API carry ISO timestamps."""
    log.on_play = lambda call: playing(
        hass,
        "x",
        media_position=10,
        media_position_updated_at=dt_util.utcnow().isoformat(),
    )
    manager = await _started(hass, "a", "b")
    await _end(hass, freezer)
    assert len(log.calls) == 2
    await manager.async_unload()


@pytest.mark.parametrize("updated", ["2026-10-07T10:00:00", "not a date", 17])
async def test_unusable_timestamp_uses_the_bare_position(
    hass: HomeAssistant,
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
    updated: Any,
) -> None:
    """Without a usable timestamp, only the reported position counts."""
    log.on_play = lambda call: playing(
        hass, "x", media_position=10, media_position_updated_at=updated
    )
    manager = await _started(hass, "a", "b")
    await _end(hass, freezer)
    assert len(log.calls) == 1
    playing(hass, "x", media_position=198, media_position_updated_at=updated)
    await hass.async_block_till_done()
    keep(hass, "idle")
    await hass.async_block_till_done()
    assert len(log.calls) == 2
    await manager.async_unload()


async def test_something_else_on_the_player_detaches(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """When the player plays other media, the queue stops following it."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)

    playing(hass, "spotify:track:1")
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.IDLE
    assert controller.fingerprint is None

    await _end(hass, freezer)
    assert len(log.calls) == 1
    await manager.async_unload()


async def test_fingerprint_learned_later(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Players that report the content id late still get a fingerprint."""
    log.on_play = lambda call: playing(hass, None)
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    assert controller.fingerprint is None

    playing(hass, "late-id")
    await hass.async_block_till_done()
    assert controller.fingerprint == "late-id"
    playing(hass, None)  # an update without id changes nothing
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING
    await manager.async_unload()


async def test_transitions_during_our_call_are_ignored(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Our own jump stops the old item: that is not a natural end."""
    manager = await _started(hass, "a", "b", "c")
    controller = manager.controller(PLAYER)
    freezer.tick(timedelta(seconds=DURATION))

    def stop_then_play(call: ServiceCall) -> None:
        keep(hass, "idle")  # old item at its end, stopped by the jump
        playing(hass, "id-c")

    log.on_play = stop_then_play
    await controller.async_play(2)
    await hass.async_block_till_done()

    assert len(log.calls) == 2
    assert controller.queue.current == 2
    assert controller.fingerprint == "id-c"
    await manager.async_unload()


async def test_armed_by_a_later_event(hass: HomeAssistant, log: PlayerLog) -> None:
    """A player that still shows the old item after the call is armed later."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    log.on_play = None

    await controller.async_play(1)
    assert _phase(controller) is Phase.STARTING  # still shows id-a.mp3 at 0 s

    # The old item again, with a position but no timestamp: not the new one.
    state(hass, "playing", "id-a.mp3", media_position=3, media_duration=DURATION)
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STARTING

    keep(hass, "buffering")
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STARTING

    playing(hass, "id-a.mp3")  # buffering → playing: the new item started
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING
    await manager.async_unload()


async def test_same_item_again_is_armed_by_its_position(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Replaying the current item: a restarted position arms it."""
    manager = await _started(hass, "a")
    controller = manager.controller(PLAYER)
    freezer.tick(timedelta(seconds=100))
    playing(hass, "id-a.mp3", media_position=100)
    log.on_play = None

    await controller.async_play(0)
    assert _phase(controller) is Phase.STARTING

    freezer.tick(timedelta(seconds=1))
    playing(hass, "id-a.mp3", media_position=150)  # still the old playback
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STARTING

    playing(hass, "id-a.mp3", media_position=1)
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING
    await manager.async_unload()


async def test_end_of_queue(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """After the last item the queue stops following and keeps its place."""
    manager = await _started(hass, "a")
    controller = manager.controller(PLAYER)
    await _end(hass, freezer)
    assert len(log.calls) == 1
    assert _phase(controller) is Phase.IDLE
    assert controller.queue.current == 0
    await manager.async_unload()


async def test_failing_items_are_skipped(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """An item that cannot play is skipped during advancing."""
    manager = await _started(hass, "a", "b", "c")
    controller = manager.controller(PLAYER)
    log.fail = "b.mp3"
    await _end(hass, freezer)
    assert log.played == ["a.mp3", "b.mp3", "c.mp3"]
    assert controller.queue.current == 2
    assert _phase(controller) is Phase.PLAYING
    await manager.async_unload()


async def test_advancing_gives_up_after_failures(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Three failing items in a row stop the queue."""
    manager = await _started(hass, "a", "b", "c", "d", "e")
    controller = manager.controller(PLAYER)
    log.fail = ".mp3"
    await _end(hass, freezer)
    assert log.played == ["a.mp3", "b.mp3", "c.mp3", "d.mp3"]
    assert _phase(controller) is Phase.IDLE
    await manager.async_unload()


@pytest.mark.parametrize("value", ["unavailable", "unknown", "buffering"])
async def test_unclear_states_are_ignored(
    hass: HomeAssistant,
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
    value: str,
) -> None:
    """A player that drops away at the end is not taken as an end."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    await _end(hass, freezer, value)
    assert _phase(controller) is Phase.PLAYING
    keep(hass, "idle")  # back from unavailable: not from playing → stopped
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STOPPED
    assert len(log.calls) == 1
    await manager.async_unload()


async def test_stop_while_paused(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Paused, then stopped: stopped, no advance; a new pause changes nothing."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    keep(hass, "paused")
    await hass.async_block_till_done()
    keep(hass, "paused")
    hass.states.async_set(PLAYER, "paused", {"media_title": "x"})
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING
    await _end(hass, freezer)
    assert _phase(controller) is Phase.STOPPED
    assert len(log.calls) == 1
    await manager.async_unload()


async def test_stopped_then_other_media(hass: HomeAssistant, log: PlayerLog) -> None:
    """After a stop, other media on the player detaches the queue."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    keep(hass, "idle")
    await hass.async_block_till_done()
    keep(hass, "paused")  # not playing: still stopped
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STOPPED
    playing(hass, "other")
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.IDLE
    await manager.async_unload()


async def test_idle_queue_ignores_the_player(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """A queue that is not playing does nothing when the player stops."""
    manager = await async_manager_with(hass, "a", "b")
    playing(hass, "something")
    await _end(hass, freezer)
    assert log.calls == []
    await manager.async_unload()


async def test_removed_entity_is_ignored(hass: HomeAssistant, log: PlayerLog) -> None:
    """The player disappearing keeps the queue as it is."""
    manager = await _started(hass, "a", "b")
    hass.states.async_remove(PLAYER)
    await hass.async_block_till_done()
    assert _phase(manager.controller(PLAYER)) is Phase.PLAYING
    await manager.async_unload()


async def test_following_survives_a_restart(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A restored playing queue advances when the restored item ends."""
    hass.states.async_remove(PLAYER)
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "queues": {
                PLAYER: {
                    "items": [track("a").as_dict(), track("b").as_dict()],
                    "current": 0,
                    "phase": "playing",
                    "fingerprint": "id-a.mp3",
                }
            }
        },
    }
    manager = QueueManager(hass)
    await manager.async_load()
    playing(hass, "id-a.mp3", media_position=120)  # the player comes back
    await hass.async_block_till_done()
    await _end(hass, freezer)
    assert log.played == ["b.mp3"]
    await manager.async_unload()


async def test_restored_without_position_does_not_guess(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Without position and without known play time, a stop is not an end."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "queues": {
                PLAYER: {
                    "items": [track("a").as_dict(), track("b").as_dict()],
                    "current": 0,
                    "phase": "playing",
                    "fingerprint": "id-a.mp3",
                }
            }
        },
    }
    playing(hass, "id-a.mp3", media_position=None)
    manager = QueueManager(hass)
    await manager.async_load()
    await _end(hass, freezer)
    assert log.calls == []
    assert _phase(manager.controller(PLAYER)) is Phase.STOPPED
    await manager.async_unload()


async def test_unload_cancels_a_pending_advance(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Unloading while the next item is being started cancels that start."""
    manager = await _started(hass, "a", "b")
    release = asyncio.Event()

    async def slow(call: ServiceCall) -> None:
        log.calls.append(call)
        await release.wait()

    hass.services.async_register("media_player", "play_media", slow)
    await _end(hass, freezer)
    assert len(log.calls) == 2
    await manager.async_unload()
    release.set()
    await hass.async_block_till_done()
    assert _phase(manager.controller(PLAYER)) is Phase.STARTING


async def test_mpd_reports_strings_and_polls(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """MPD: duration as text, position polled every 10 s, off at the end."""

    def mpd_plays(call: ServiceCall) -> None:
        state(
            hass,
            "playing",
            call.data["media_content_id"],
            media_duration="200.493",
            media_position=0,
            media_position_updated_at=dt_util.utcnow(),
        )

    log.on_play = mpd_plays
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    first = log.calls[0].data["media_content_id"]
    for position in range(10, 200, 10):  # one poll every 10 s
        freezer.tick(timedelta(seconds=10))
        state(
            hass,
            "playing",
            first,
            media_duration="200.493",
            media_position=position,
            media_position_updated_at=dt_util.utcnow(),
        )
        await hass.async_block_till_done()
    assert len(log.calls) == 1
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(PLAYER, "off", {})  # stopped: MPD forgets the song
    await hass.async_block_till_done()
    assert log.played == ["a.mp3", "b.mp3"]
    assert _phase(controller) is Phase.PLAYING
    await manager.async_unload()


@pytest.mark.parametrize("duration", ["abc", "nan", "inf", "-inf", ""])
async def test_unusable_text_duration_is_unknown(
    hass: HomeAssistant,
    log: PlayerLog,
    freezer: FrozenDateTimeFactory,
    duration: str,
) -> None:
    """Text that is no finite number counts as an unknown duration."""
    log.on_play = lambda call: playing(hass, "x", media_duration=duration)
    manager = await _started(hass, "a", "b")
    await _end(hass, freezer)
    assert len(log.calls) == 1
    await manager.async_unload()


class MPDConnectionError(Exception):
    """Like mpd.ConnectionError: not a HomeAssistantError."""


async def test_any_player_exception_is_a_failed_play(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """A library error (MPD down) is wrapped, recorded and skipped."""
    manager = await _started(hass, "a", "b", "c")
    controller = manager.controller(PLAYER)
    log.fail = "b.mp3"
    log.error = MPDConnectionError("Connection refused")
    await _end(hass, freezer)
    assert log.played == ["a.mp3", "b.mp3", "c.mp3"]
    assert controller.queue.current == 2
    error = controller.snapshot()["last_error"]
    assert error["kind"] == "cannot_play"
    assert error["title"] == "b"
    assert error["message"] == "Connection refused"

    with pytest.raises(HomeAssistantError) as err:
        await controller.async_play(1)
    assert err.value.translation_key == "cannot_play"
    assert _phase(controller) is Phase.IDLE
    await manager.async_unload()


async def test_item_that_never_starts_is_skipped(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """play_media works but the player never plays: after a while, the next."""
    manager = await _started(hass, "a", "b", "c")
    controller = manager.controller(PLAYER)
    plays = log.on_play
    assert plays is not None

    def all_but_b(call: ServiceCall) -> None:
        if "b.mp3" not in call.data["media_content_id"]:
            plays(call)

    log.on_play = all_but_b
    await _end(hass, freezer)
    assert log.played == ["a.mp3", "b.mp3"]
    assert _phase(controller) is Phase.STARTING

    freezer.tick(timedelta(seconds=STARTING_TIMEOUT + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert log.played == ["a.mp3", "b.mp3", "c.mp3"]
    assert _phase(controller) is Phase.PLAYING
    error = controller.snapshot()["last_error"]
    assert error["kind"] == "did_not_start"
    assert error["title"] == "b"
    await manager.async_unload()


async def test_nothing_starts_gives_up(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Three items in a row that never start stop the queue."""
    manager = await _started(hass, "a", "b", "c", "d", "e")
    controller = manager.controller(PLAYER)
    log.on_play = None
    await _end(hass, freezer)
    for _ in range(3):
        freezer.tick(timedelta(seconds=STARTING_TIMEOUT + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert log.played == ["a.mp3", "b.mp3", "c.mp3", "d.mp3"]
    assert _phase(controller) is Phase.IDLE
    await manager.async_unload()


async def test_started_item_cancels_the_watchdog(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """An item that starts late (but in time) is followed, nothing skipped."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    log.on_play = None
    freezer.tick(timedelta(seconds=1))
    await controller.async_play(1)
    assert _phase(controller) is Phase.STARTING
    freezer.tick(timedelta(seconds=10))
    playing(hass, "id-b")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=STARTING_TIMEOUT))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(log.calls) == 2
    assert _phase(controller) is Phase.PLAYING
    assert controller.snapshot()["last_error"] is None
    await manager.async_unload()


async def test_unload_cancels_the_watchdog(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """No skipping after unloading."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    log.on_play = None
    await controller.async_play(1)
    await manager.async_unload()
    freezer.tick(timedelta(seconds=STARTING_TIMEOUT + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(log.calls) == 2


async def test_watchdog_after_the_item_was_removed(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """The item that did not start was removed meanwhile: no title, go on."""
    manager = await _started(hass, "a", "b", "c")
    controller = manager.controller(PLAYER)
    log.on_play = None
    freezer.tick(timedelta(seconds=1))
    await controller.async_play(1)
    controller.remove(1)
    freezer.tick(timedelta(seconds=STARTING_TIMEOUT + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert controller.snapshot()["last_error"]["title"] == ""
    assert log.played[-1] == "c.mp3"
    await manager.async_unload()


async def test_position_from_before_our_play_is_ignored(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """A position timestamp older than our play (the demo player) is not ours."""
    started_long_ago = dt_util.utcnow()
    freezer.tick(timedelta(hours=1))
    log.on_play = lambda call: playing(
        hass, "new", media_position=45, media_position_updated_at=started_long_ago
    )
    manager = await _started(hass, "a", "b")
    freezer.tick(timedelta(seconds=30))
    keep(hass, "idle")  # 30 s played of 200: a stop, not the end
    await hass.async_block_till_done()
    assert len(log.calls) == 1
    assert _phase(manager.controller(PLAYER)) is Phase.STOPPED
    await manager.async_unload()


async def test_old_content_after_a_transition_does_not_arm(
    hass: HomeAssistant, log: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Idle → playing with the previous item's id (and old position) is not ours."""
    manager = await _started(hass, "a", "b")
    controller = manager.controller(PLAYER)
    log.on_play = lambda call: keep(hass, "idle")  # the old item stops first
    freezer.tick(timedelta(seconds=50))
    await controller.async_play(1)
    assert _phase(controller) is Phase.STARTING

    keep(hass, "playing")  # the old item resumes, same id, old timestamp
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.STARTING

    playing(hass, "id-b")
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING
    await manager.async_unload()


async def test_players_without_content_id_arm_on_the_transition(
    hass: HomeAssistant, log: PlayerLog
) -> None:
    """Without any content id, a transition into playing is the only sign."""
    log.on_play = lambda call: None
    manager = await async_manager_with(hass, "a")
    controller = manager.controller(PLAYER)
    await controller.async_play(0)
    assert _phase(controller) is Phase.STARTING
    state(hass, "playing", media_duration=DURATION)
    await hass.async_block_till_done()
    assert _phase(controller) is Phase.PLAYING
    await manager.async_unload()
