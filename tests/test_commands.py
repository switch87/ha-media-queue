"""Tests for the queue commands of a controller."""

from collections.abc import Callable
from pathlib import Path

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.media_queue import controller as controller_module
from custom_components.media_queue.controller import Phase, QueueController
from custom_components.media_queue.expand import AddRequest
from custom_components.media_queue.manager import QueueManager
from custom_components.media_queue.model import Mode

from .common import (
    LOCAL,
    PLAYER,
    PlayerLog,
    async_manager_with,
    async_setup_library,
)


def _folder() -> AddRequest:
    return AddRequest(
        media_content_id=f"{LOCAL}/Yeti", media_content_type="", can_expand=True
    )


def _titles(manager: QueueManager) -> list[str]:
    return [item.title for item in manager.controller(PLAYER).queue.items]


@pytest.fixture
async def log(hass: HomeAssistant, tmp_path: Path) -> PlayerLog:
    """Return the play_media log with the test library set up."""
    await async_setup_library(hass, tmp_path)
    return PlayerLog(hass)


async def test_replace_plays_the_first_item(
    hass: HomeAssistant, log: PlayerLog
) -> None:
    """Replace swaps the queue for the folder and plays its first track."""
    manager = await async_manager_with(hass, "x", current=0)
    controller = manager.controller(PLAYER)
    context = Context()

    result = await controller.async_add(_folder(), Mode.REPLACE, context=context)

    assert result == {"added": 5, "truncated": False, "limit": 1000}
    assert _titles(manager) == ["a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3"]
    assert log.played == ["a.mp3"]
    assert log.calls[0].context is context
    assert controller.queue.current == 0
    await manager.async_unload()


async def test_play_inserts_and_plays(hass: HomeAssistant, log: PlayerLog) -> None:
    """Play puts the items after the current one and starts the first."""
    manager = await async_manager_with(hass, "x", "y", current=0)
    controller = manager.controller(PLAYER)
    await controller.async_add(
        AddRequest(
            media_content_id=f"{LOCAL}/Yeti/c.mp3",
            media_content_type="audio/mpeg",
            title="c",
            can_expand=False,
        ),
        Mode.PLAY,
    )
    assert _titles(manager) == ["x", "c", "y"]
    assert controller.queue.current == 1
    assert log.played == ["c.mp3"]
    await manager.async_unload()


@pytest.mark.parametrize(
    ("mode", "titles"),
    [
        (Mode.ADD, ["x", "y", "a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3"]),
        (Mode.NEXT, ["x", "a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3", "y"]),
    ],
)
async def test_add_and_next_do_not_play(
    hass: HomeAssistant, log: PlayerLog, mode: Mode, titles: list[str]
) -> None:
    """Add and play next only change the queue, and tell subscribers."""
    manager = await async_manager_with(hass, "x", "y", current=0)
    seen: list[int] = []
    manager.subscribe(PLAYER, lambda data: seen.append(len(data["items"])))
    await manager.controller(PLAYER).async_add(_folder(), mode)
    assert _titles(manager) == titles
    assert log.calls == []
    assert seen == [7]
    await manager.async_unload()


async def test_add_is_capped(
    hass: HomeAssistant, log: PlayerLog, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The queue limit cuts long folders and says so."""
    monkeypatch.setattr(controller_module, "QUEUE_LIMIT", 4)
    manager = await async_manager_with(hass, "x")
    controller = manager.controller(PLAYER)

    result = await controller.async_add(_folder(), Mode.ADD)
    assert result == {"added": 3, "truncated": True, "limit": 4}

    with pytest.raises(ServiceValidationError) as err:
        await controller.async_add(_folder(), Mode.ADD)
    assert err.value.translation_key == "queue_full"
    assert err.value.translation_placeholders == {"limit": "4"}

    result = await controller.async_add(_folder(), Mode.REPLACE)
    assert result == {"added": 4, "truncated": True, "limit": 4}
    await manager.async_unload()


async def test_add_nothing_playable(hass: HomeAssistant, log: PlayerLog) -> None:
    """An empty folder is reported instead of silently doing nothing."""
    (Path(hass.config.media_dirs["local"]) / "Empty").mkdir()
    manager = await async_manager_with(hass, "x")
    with pytest.raises(ServiceValidationError) as err:
        await manager.controller(PLAYER).async_add(
            AddRequest(
                media_content_id=f"{LOCAL}/Empty",
                media_content_type="",
                title="Empty",
            ),
            Mode.REPLACE,
        )
    assert err.value.translation_key == "nothing_to_add"
    assert err.value.translation_placeholders == {"item": "Empty"}
    assert _titles(manager) == ["x"]
    await manager.async_unload()


async def test_next_and_previous(hass: HomeAssistant, log: PlayerLog) -> None:
    """Next and previous walk the queue; previous on the first replays it."""
    manager = await async_manager_with(hass, "a", "b", current=0)
    controller = manager.controller(PLAYER)

    await controller.async_next()
    assert controller.queue.current == 1
    with pytest.raises(ServiceValidationError) as err:
        await controller.async_next()
    assert err.value.translation_key == "end_of_queue"

    await controller.async_previous()
    await controller.async_previous()
    assert controller.queue.current == 0
    assert log.played == ["b.mp3", "a.mp3", "a.mp3"]
    await manager.async_unload()


async def test_previous_on_empty_queue(hass: HomeAssistant, log: PlayerLog) -> None:
    """Nothing to go back to in an empty queue."""
    manager = await async_manager_with(hass)
    with pytest.raises(ServiceValidationError) as err:
        await manager.controller(PLAYER).async_previous()
    assert err.value.translation_key == "queue_empty"
    await manager.async_unload()


async def test_remove_move_clear(hass: HomeAssistant, log: PlayerLog) -> None:
    """Editing the queue keeps current on its item and notifies subscribers."""
    manager = await async_manager_with(hass, "a", "b", "c", current=1)
    controller = manager.controller(PLAYER)
    seen: list[int | None] = []
    manager.subscribe(PLAYER, lambda data: seen.append(data["current"]))

    controller.remove(0)
    controller.move(0, 1)
    assert _titles(manager) == ["c", "b"]
    assert controller.queue.current == 1

    controller.clear()
    assert _titles(manager) == []
    assert seen == [0, 1, None]
    await manager.async_unload()


@pytest.mark.parametrize(
    "action",
    [
        lambda c: c.remove(3),
        lambda c: c.move(0, 3),
        lambda c: c.move(-1, 0),
    ],
)
async def test_edits_validate_indexes(
    hass: HomeAssistant,
    log: PlayerLog,
    action: Callable[[QueueController], object],
) -> None:
    """Indexes outside the queue give a translated error."""
    manager = await async_manager_with(hass, "a", "b", "c")
    with pytest.raises(ServiceValidationError) as err:
        action(manager.controller(PLAYER))
    assert err.value.translation_key == "invalid_index"
    assert err.value.translation_placeholders is not None
    assert err.value.translation_placeholders["count"] == "3"
    await manager.async_unload()


async def test_clear_while_playing_keeps_following(
    hass: HomeAssistant, log: PlayerLog
) -> None:
    """Clearing does not stop the player; new items play after the current one."""
    manager = await async_manager_with(hass, "a")
    controller = manager.controller(PLAYER)
    controller.phase = Phase.PLAYING
    controller.clear()
    assert controller.phase is Phase.PLAYING
    assert controller.queue.next_position == 0
    await manager.async_unload()
