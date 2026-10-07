"""Helpers shared by the controller tests."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.media_queue.manager import QueueManager
from custom_components.media_queue.model import Mode, QueueItem

PLAYER = "media_player.living_room"
LOCAL = "media-source://media_source/local"
BASE_URL = "http://example.local:8123"


def track(title: str, *, folder: str = "Yeti") -> QueueItem:
    """Return a queue item for a file of the test library."""
    return QueueItem(
        media_content_id=f"{LOCAL}/{folder}/{title}.mp3",
        media_content_type="audio/mpeg",
        title=title,
    )


async def async_setup_library(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Create a local library with files a…e and set up the media source."""
    album = tmp_path / "Yeti"
    album.mkdir()
    for title in ("a", "b", "c", "d", "e"):
        (album / f"{title}.mp3").write_bytes(b"")
    (tmp_path / "Clips").mkdir()
    (tmp_path / "Clips" / "clip.mp4").write_bytes(b"")
    (album / "cover.jpg").write_bytes(b"")
    hass.config.media_dirs = {"local": str(tmp_path)}
    hass.config.internal_url = BASE_URL
    assert await async_setup_component(hass, "media_source", {})
    return tmp_path


class PlayerLog:
    """Record play_media calls; optionally act like the player on each call."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Register the fake play_media service."""
        self.hass = hass
        self.calls: list[ServiceCall] = []
        self.on_play: Callable[[ServiceCall], None] | None = None
        self.fail: str | None = None
        hass.services.async_register("media_player", "play_media", self._handle)

    async def _handle(self, call: ServiceCall) -> None:
        self.calls.append(call)
        if self.fail is not None and self.fail in call.data["media_content_id"]:
            raise HomeAssistantError("player refused")
        if self.on_play is not None:
            self.on_play(call)

    @property
    def played(self) -> list[str]:
        """Return the played content ids without the URL signature."""
        return [
            call.data["media_content_id"].split("?")[0].rsplit("/", 1)[-1]
            for call in self.calls
        ]


async def async_manager_with(
    hass: HomeAssistant, *titles: str, current: int | None = None
) -> QueueManager:
    """Return a loaded manager whose PLAYER queue holds the given tracks."""
    manager = QueueManager(hass)
    await manager.async_load()
    controller = manager.controller(PLAYER)
    controller.queue.add([track(t) for t in titles], Mode.ADD, limit=100)
    if current is not None:
        controller.queue.set_current(current)
    return manager


def state(
    hass: HomeAssistant, value: str, content_id: str | None = None, **attrs: Any
) -> None:
    """Set the state of the test player."""
    if content_id is not None:
        attrs["media_content_id"] = content_id
    hass.states.async_set(PLAYER, value, attrs)
