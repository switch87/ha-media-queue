"""Tests for repeat and shuffle in the controller."""

from datetime import timedelta
from pathlib import Path
import random
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.media_queue.controller import (
    STARTING_TIMEOUT,
    Phase,
    QueueController,
)
from custom_components.media_queue.manager import QueueManager
from custom_components.media_queue.model import Repeat

from .common import PLAYER, PlayerLog, async_manager_with, async_setup_library, state

DURATION = 200


def _name(call: ServiceCall) -> str:
    return str(call.data["media_content_id"]).split("?")[0].rsplit("/", 1)[-1]


def _playing(hass: HomeAssistant, content_id: str) -> None:
    state(
        hass,
        "playing",
        content_id,
        media_duration=DURATION,
        media_position=0,
        media_position_updated_at=dt_util.utcnow(),
    )


@pytest.fixture
async def player(hass: HomeAssistant, tmp_path: Path) -> PlayerLog:
    """Return a player that starts playing whatever it is asked to play."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    state(hass, "idle")
    log.on_play = lambda call: _playing(hass, f"id-{_name(call)}")
    return log


async def _started(
    hass: HomeAssistant, *titles: str, at: int = 0, repeat: Repeat = Repeat.OFF
) -> tuple[QueueManager, QueueController]:
    manager = await async_manager_with(hass, *titles)
    controller = manager.controller(PLAYER)
    controller.set_repeat(repeat)
    await controller.async_play(at)
    await hass.async_block_till_done()
    return manager, controller


async def _end(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=DURATION))
    current = hass.states.get(PLAYER)
    assert current is not None
    hass.states.async_set(PLAYER, "idle", current.attributes)
    await hass.async_block_till_done()


def _phase(controller: QueueController) -> Phase:
    return controller.phase


async def test_repeat_one_replays_the_item(
    hass: HomeAssistant, player: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """At its natural end the item plays again; next still moves on."""
    manager, controller = await _started(hass, "a", "b", repeat=Repeat.ONE)

    await _end(hass, freezer)
    await _end(hass, freezer)
    assert player.played == ["a.mp3", "a.mp3", "a.mp3"]
    assert controller.queue.current == 0
    assert _phase(controller) is Phase.PLAYING

    await controller.async_next()
    await hass.async_block_till_done()
    assert player.played[-1] == "b.mp3"
    assert controller.queue.repeat is Repeat.ONE
    await manager.async_unload()


async def test_repeat_one_after_removing_the_current_item(
    hass: HomeAssistant, player: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """The removed item is not repeated: the queue goes on."""
    manager, controller = await _started(hass, "a", "b", repeat=Repeat.ONE)
    controller.remove(0)
    await _end(hass, freezer)
    assert player.played == ["a.mp3", "b.mp3"]
    await manager.async_unload()


async def test_repeat_one_does_not_retry_an_item_that_does_not_start(
    hass: HomeAssistant, player: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """An item that never starts is skipped, not repeated."""
    manager, _controller = await _started(hass, "a", "b", "c", repeat=Repeat.ONE)
    plays = player.on_play
    assert plays is not None
    player.on_play = None
    await _end(hass, freezer)  # a again: it does not start this time
    assert player.played == ["a.mp3", "a.mp3"]
    player.on_play = plays
    freezer.tick(timedelta(seconds=STARTING_TIMEOUT + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert player.played == ["a.mp3", "a.mp3", "b.mp3"]
    await manager.async_unload()


async def test_repeat_all_starts_again(
    hass: HomeAssistant, player: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """After the last item the first plays; the snapshot shows it as next."""
    manager, controller = await _started(hass, "a", "b", repeat=Repeat.ALL)
    assert controller.snapshot()["next"] == 1
    await _end(hass, freezer)
    assert controller.snapshot()["next"] == 0
    assert controller.playback()["next"] == 0
    await _end(hass, freezer)
    assert player.played == ["a.mp3", "b.mp3", "a.mp3"]
    assert controller.queue.current == 0
    await manager.async_unload()


async def test_next_wraps_with_repeat_all(
    hass: HomeAssistant, player: PlayerLog
) -> None:
    """The next button on the last item goes to the top with repeat all."""
    manager, controller = await _started(hass, "a", "b", at=1)
    with pytest.raises(ServiceValidationError):
        await controller.async_next()
    controller.set_repeat(Repeat.ALL)
    await controller.async_next()
    assert player.played == ["b.mp3", "a.mp3"]
    await manager.async_unload()


async def test_next_on_an_empty_queue_with_repeat_all(
    hass: HomeAssistant, player: PlayerLog
) -> None:
    """Nothing to wrap to."""
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    controller.set_repeat(Repeat.ALL)
    with pytest.raises(ServiceValidationError):
        await controller.async_next()
    await manager.async_unload()


async def test_repeat_all_shuffled_mixes_again(
    hass: HomeAssistant, player: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """At the end a shuffled queue is mixed again and the panel gets it all."""
    manager, controller = await _started(hass, *"abcdefgh", repeat=Repeat.ALL)
    controller.queue.rng = random.Random(3)
    controller.set_shuffle(True)
    seen: list[dict[str, Any]] = []
    manager.subscribe(PLAYER, seen.append)
    first_round = [item.title for item in controller.queue.items]
    last = first_round[-1]
    await controller.async_play(len(first_round) - 1)
    await hass.async_block_till_done()
    assert controller.snapshot()["next"] is None  # drawn when it wraps

    await _end(hass, freezer)

    second_round = [item.title for item in controller.queue.items]
    assert sorted(second_round) == sorted(first_round)
    assert second_round != first_round
    assert second_round[0] != last
    assert player.played[-1] == f"{second_round[0]}.mp3"
    assert controller.queue.current == 0
    assert any(not update.get("playback") for update in seen)
    await manager.async_unload()


async def test_repeat_all_gives_up_when_nothing_plays(
    hass: HomeAssistant, player: PlayerLog, freezer: FrozenDateTimeFactory
) -> None:
    """Failing items wrap around too, but at most three are tried."""
    manager, controller = await _started(hass, "a", "b", at=1, repeat=Repeat.ALL)
    player.fail = ".mp3"
    await _end(hass, freezer)
    assert player.played == ["b.mp3", "a.mp3", "b.mp3", "a.mp3"]
    assert _phase(controller) is Phase.IDLE
    await manager.async_unload()


async def test_settings_change_the_snapshot(
    hass: HomeAssistant, player: PlayerLog
) -> None:
    """Shuffle and repeat are in the snapshot; changes go out in full."""
    manager, controller = await _started(hass, *"abcdef", at=2)
    seen: list[dict[str, Any]] = []
    manager.subscribe(PLAYER, seen.append)
    assert controller.snapshot()["shuffle"] is False
    assert controller.snapshot()["repeat"] == "off"
    assert manager.snapshot("media_player.none")["repeat"] == "off"

    controller.set_shuffle(True)
    controller.set_shuffle(True)
    controller.set_repeat(Repeat.ONE)
    controller.set_repeat(Repeat.ONE)

    assert len(seen) == 2
    assert seen[-1]["shuffle"] is True
    assert seen[-1]["repeat"] == "one"
    assert seen[-1]["current"] == 0
    assert seen[-1]["items"][0]["title"] == "c"
    await manager.async_unload()
