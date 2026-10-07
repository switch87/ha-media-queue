"""Tests for playing a queue item on the real player."""

from pathlib import Path

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest

from custom_components.media_queue.controller import Phase
from custom_components.media_queue.model import Mode, QueueItem

from .common import (
    BASE_URL,
    LOCAL,
    PLAYER,
    PlayerLog,
    async_manager_with,
    async_setup_library,
    state,
)


async def test_media_source_item_is_resolved(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """A media-source item is resolved for the player and played as a URL."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    manager = await async_manager_with(hass, "a", "b")
    controller = manager.controller(PLAYER)
    seen: list[int | None] = []
    manager.subscribe(PLAYER, lambda data: seen.append(data["current"]))
    context = Context()

    await controller.async_play(1, context=context)

    [call] = log.calls
    assert call.data["entity_id"] == PLAYER
    assert call.data["media_content_type"] == "music"
    url = call.data["media_content_id"]
    assert url.startswith(f"{BASE_URL}/media/local/Yeti/b.mp3?authSig=")
    assert "enqueue" not in call.data
    assert call.context is context
    assert controller.queue.current == 1
    assert controller.phase is Phase.STARTING
    assert seen == [1]
    await manager.async_unload()


async def test_video_is_played_as_video(hass: HomeAssistant, tmp_path: Path) -> None:
    """The content type follows the resolved mime type."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    controller.queue.add(
        [
            QueueItem(
                media_content_id=f"{LOCAL}/Yeti/clip.mp4",
                media_content_type="video/mp4",
                title="Clip",
            )
        ],
        Mode.ADD,
        limit=10,
    )
    await controller.async_play(0)
    assert log.calls[0].data["media_content_type"] == "video"
    await manager.async_unload()


async def test_other_ids_are_played_as_they_are(hass: HomeAssistant) -> None:
    """Ids from the player's own library go to play_media unchanged."""
    log = PlayerLog(hass)
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    controller.queue.add(
        [
            QueueItem(
                media_content_id="A:ALBUM/Yeti",
                media_content_type="album",
                title="Yeti",
            )
        ],
        Mode.ADD,
        limit=10,
    )
    await controller.async_play(0)
    assert log.calls[0].data["media_content_id"] == "A:ALBUM/Yeti"
    assert log.calls[0].data["media_content_type"] == "album"
    await manager.async_unload()


async def test_unresolvable_item(hass: HomeAssistant, tmp_path: Path) -> None:
    """An item of a source that is gone gives a translated error."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    controller.queue.add(
        [
            QueueItem(
                media_content_id="media-source://removed_source/x",
                media_content_type="music",
                title="gone",
            )
        ],
        Mode.ADD,
        limit=10,
    )

    with pytest.raises(HomeAssistantError) as err:
        await controller.async_play(0)

    assert err.value.translation_key == "cannot_play"
    assert err.value.translation_placeholders is not None
    assert err.value.translation_placeholders["title"] == "gone"
    assert log.calls == []
    assert controller.phase is Phase.IDLE
    assert controller.queue.current == 0
    await manager.async_unload()


async def test_player_error(hass: HomeAssistant, tmp_path: Path) -> None:
    """An error of the player is reported as cannot_play."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    log.fail = "a.mp3"
    manager = await async_manager_with(hass, "a")
    controller = manager.controller(PLAYER)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_play(0)
    assert err.value.translation_key == "cannot_play"
    assert err.value.translation_placeholders == {
        "title": "a",
        "error": "player refused",
    }
    await manager.async_unload()


async def test_image_is_played_as_image(hass: HomeAssistant, tmp_path: Path) -> None:
    """An image added on purpose is shown as an image."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    controller.queue.add(
        [
            QueueItem(
                media_content_id=f"{LOCAL}/Yeti/cover.jpg",
                media_content_type="image/jpeg",
                title="Cover",
            )
        ],
        Mode.ADD,
        limit=10,
    )
    await controller.async_play(0)
    assert log.calls[0].data["media_content_type"] == "image"
    controller.async_stop()  # stopping twice is harmless
    await manager.async_unload()


@pytest.mark.parametrize("index", [-1, 2])
async def test_play_missing_index(hass: HomeAssistant, index: int) -> None:
    """Only existing items can be played."""
    PlayerLog(hass)
    manager = await async_manager_with(hass, "a", "b")
    with pytest.raises(ServiceValidationError) as err:
        await manager.controller(PLAYER).async_play(index)
    assert err.value.translation_key == "invalid_index"
    assert err.value.translation_placeholders == {"index": str(index), "count": "2"}
    await manager.async_unload()


async def test_arms_when_the_player_already_shows_the_new_item(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """A player that reports the new item during the call is followed at once."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    state(hass, "idle")
    log.on_play = lambda call: state(hass, "playing", "x-b")
    manager = await async_manager_with(hass, "a", "b")
    controller = manager.controller(PLAYER)

    await controller.async_play(1)

    assert controller.phase is Phase.PLAYING
    assert controller.fingerprint == "x-b"
    await manager.async_unload()
