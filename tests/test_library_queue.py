"""Tests for saving a queue as a playlist and loading it into a queue."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.media_queue import controller as controller_module, enrich
from custom_components.media_queue.const import QUEUE_LIMIT
from custom_components.media_queue.library import PLAYLIST_STORAGE_KEY
from custom_components.media_queue.model import Mode, QueueItem

from .common import PLAYER, PlayerLog, async_manager_with, async_setup_library, track

OTHER = "media_player.kitchen"


@pytest.fixture
async def log(hass: HomeAssistant, tmp_path: Path) -> PlayerLog:
    """Set up the library folder and record play_media calls."""
    await async_setup_library(hass, tmp_path)
    hass.states.async_set(PLAYER, "idle")
    hass.states.async_set(OTHER, "idle")
    return PlayerLog(hass)


def _timed(title: str) -> QueueItem:
    return QueueItem(
        media_content_id=f"http://radio/{title}",
        media_content_type="music",
        title=title,
        artist="Band",
        duration=100.0,
    )


async def test_save_a_queue_and_load_it_elsewhere(
    hass: HomeAssistant, log: PlayerLog
) -> None:
    """The library belongs to the manager; any player can load a playlist."""
    manager = await async_manager_with(hass, "a", "b", "c")
    source = manager.controller(PLAYER)
    playlist = manager.library.save("Mix", source.queue.items, overwrite=False)

    target = manager.controller(OTHER)
    result = await target.async_add_items(playlist.items, Mode.REPLACE)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result == {"added": 3, "truncated": False, "limit": QUEUE_LIMIT}
    assert [item.title for item in target.queue.items] == ["a", "b", "c"]
    assert {item.item_id for item in target.queue.items}.isdisjoint(
        item.item_id for item in playlist.items
    )
    assert target.queue.current == 0
    assert log.played == ["a.mp3"]
    assert log.calls[0].data["entity_id"] == OTHER
    await manager.async_unload()


@pytest.mark.parametrize(
    ("mode", "titles", "played"),
    [
        (Mode.ADD, ["x", "y", "p", "q"], []),
        (Mode.NEXT, ["x", "p", "q", "y"], []),
        (Mode.PLAY, ["x", "p", "q", "y"], ["p"]),
    ],
)
async def test_load_modes(
    hass: HomeAssistant,
    log: PlayerLog,
    mode: Mode,
    titles: list[str],
    played: list[str],
) -> None:
    """Loading follows the add modes; titles, artists and durations stay."""
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    controller.queue.add([_timed("x"), _timed("y")], Mode.ADD, limit=10)
    controller.queue.set_current(0)
    await controller.async_add_items([_timed("p"), _timed("q")], mode)
    assert [item.title for item in controller.queue.items] == titles
    assert controller.queue.items[1].artist == "Band"
    assert controller.queue.items[1].duration == 100.0
    assert log.played == played
    await manager.async_unload()


async def test_only_items_without_duration_are_read_again(
    hass: HomeAssistant, log: PlayerLog
) -> None:
    """Tagged items keep their tags; file-name items get their tags read."""
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    asked: list[str] = []

    def spy(files: list[tuple[str, str, str]], budget: float) -> Any:
        asked.extend(relative for _, _, relative in files)
        return len(files), {}

    tagged = QueueItem(
        media_content_id=track("a").media_content_id,
        media_content_type="audio/mpeg",
        title="A",
        duration=3.0,
    )
    with patch.object(enrich, "read_batch", spy):
        await controller.async_add_items([tagged, track("b")], Mode.ADD)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert asked == ["Yeti/b.mp3"]
    await manager.async_unload()


async def test_load_into_a_full_queue(hass: HomeAssistant, log: PlayerLog) -> None:
    """A full queue takes nothing more (replace still works)."""
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    with patch.object(controller_module, "QUEUE_LIMIT", 1):
        controller.queue.add([_timed("x")], Mode.ADD, limit=1)
        with pytest.raises(ServiceValidationError) as err:
            await controller.async_add_items([_timed("p")], Mode.ADD)
        assert err.value.translation_key == "queue_full"
        result = await controller.async_add_items(
            [_timed("p"), _timed("q")], Mode.REPLACE
        )
    assert result["truncated"] is True
    assert [item.title for item in controller.queue.items] == ["p"]
    await manager.async_unload()


async def test_one_track_of_a_playlist(hass: HomeAssistant, log: PlayerLog) -> None:
    """A single track is picked by its id within the playlist."""
    manager = await async_manager_with(hass)
    playlist = manager.library.save("Mix", [_timed("p"), _timed("q")], overwrite=False)
    second = playlist.items[1]
    assert playlist.pick(None) == playlist.items
    assert playlist.pick(second.item_id) == [second]
    with pytest.raises(ServiceValidationError) as err:
        playlist.pick("nope")
    assert err.value.translation_key == "unknown_item"
    await manager.async_unload()


async def test_unload_saves_the_library(
    hass: HomeAssistant, hass_storage: dict[str, Any], log: PlayerLog
) -> None:
    """The manager loads and flushes the library with the queues."""
    manager = await async_manager_with(hass)
    manager.library.save("Mix", [_timed("p")], overwrite=False)
    await manager.async_unload()
    assert hass_storage[PLAYLIST_STORAGE_KEY]["data"]["playlists"][0]["name"] == "Mix"
