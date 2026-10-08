"""Probes for the hang the Pi reported: ws_get while a subscription is active."""

import asyncio
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.media_queue import controller as controller_module
from custom_components.media_queue.const import DOMAIN

from .common import LOCAL, PLAYER, PlayerLog, async_setup_library

OTHER = "media_player.bedroom"
FOLDER = {
    "media_content_id": f"{LOCAL}/Yeti",
    "media_content_type": "",
    "title": "Yeti",
    "can_expand": True,
}


@pytest.fixture
async def entry(hass: HomeAssistant, tmp_path: Path) -> MockConfigEntry:
    """Set up the library and the integration."""
    await async_setup_library(hass, tmp_path)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def log(hass: HomeAssistant, entry: MockConfigEntry) -> PlayerLog:
    """Record play_media calls."""
    return PlayerLog(hass)


class Panel:
    """A websocket client with a subscription, like an open Muziek page."""

    def __init__(self, ws: Any) -> None:
        """Wrap the test client."""
        self.ws = ws
        self.updates: list[dict[str, Any]] = []

    async def subscribe(self, entity_id: str) -> None:
        """Start a media_queue/subscribe subscription."""
        await self.ws.send_json_auto_id(
            {"type": "media_queue/subscribe", "entity_id": entity_id}
        )
        reply = await self.ws.receive_json()
        assert reply["success"]
        event = await self.ws.receive_json()
        self.updates.append(event["event"])

    async def call(self, command: str, **data: Any) -> dict[str, Any]:
        """Send a command and return its reply, keeping subscription events."""
        await self.ws.send_json_auto_id({"type": f"media_queue/{command}", **data})
        while True:
            reply: dict[str, Any] = await self.ws.receive_json()
            if reply["type"] == "result":
                return reply
            self.updates.append(reply["event"])


async def test_get_answers_while_subscriptions_are_active(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, log: PlayerLog
) -> None:
    """A second client keeps getting answers while two panels are subscribed."""
    panel = Panel(await hass_ws_client(hass))
    await panel.subscribe(PLAYER)
    second = Panel(await hass_ws_client(hass))
    await second.subscribe(PLAYER)
    reader = Panel(await hass_ws_client(hass))

    async with asyncio.timeout(10):
        for _ in range(20):
            for entity_id in (PLAYER, OTHER):
                reply = await reader.call("get", entity_id=entity_id)
                assert reply["success"], reply


async def test_get_answers_while_tags_are_read(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, log: PlayerLog
) -> None:
    """Adding a folder (tags read in the background) does not block get."""
    panel = Panel(await hass_ws_client(hass))
    await panel.subscribe(PLAYER)
    reader = Panel(await hass_ws_client(hass))

    async with asyncio.timeout(10):
        assert (await panel.call("add", entity_id=PLAYER, mode="add", **FOLDER))[
            "success"
        ]
        for _ in range(20):
            assert (await reader.call("get", entity_id=PLAYER))["success"]
    await hass.async_block_till_done()


async def test_get_answers_while_a_playlist_is_saved_and_loaded(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, log: PlayerLog
) -> None:
    """Saving and loading a playlist does not block get on either player."""
    panel = Panel(await hass_ws_client(hass))
    await panel.subscribe(PLAYER)
    reader = Panel(await hass_ws_client(hass))
    assert (await panel.call("add", entity_id=PLAYER, mode="add", **FOLDER))["success"]

    async with asyncio.timeout(10):
        saved = await panel.call(
            "playlists/save", entity_id=PLAYER, name="Probe", overwrite=False
        )
        assert saved["success"], saved
        for _ in range(5):
            assert (await reader.call("get", entity_id=PLAYER))["success"]
            loaded = await panel.call(
                "playlists/load",
                entity_id=OTHER,
                playlist_id=saved["result"]["id"],
                mode="add",
            )
            assert loaded["success"], loaded
            assert (await reader.call("get", entity_id=OTHER))["success"]
    await hass.async_block_till_done()


async def test_commands_do_not_hang_on_a_player_that_never_answers(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    log: PlayerLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A play_media that never returns must not block the player's queue.

    Regression (Pi, 0.3.0): the queue lock was held across the blocking
    play_media call, so next/previous/play/add/load on that player waited
    forever and the Muziek page seemed to hang.
    """
    monkeypatch.setattr(controller_module, "PLAY_TIMEOUT", 0.2, raising=False)
    panel = Panel(await hass_ws_client(hass))
    await panel.subscribe(PLAYER)
    assert (await panel.call("add", entity_id=PLAYER, mode="add", **FOLDER))["success"]
    blocked = asyncio.Event()

    async def never_answer(call: Any) -> None:
        blocked.set()
        await asyncio.sleep(3600)

    hass.services.async_remove("media_player", "play_media")
    hass.services.async_register("media_player", "play_media", never_answer)
    playing = asyncio.create_task(panel.call("next", entity_id=PLAYER))
    await blocked.wait()

    second = Panel(await hass_ws_client(hass))
    async with asyncio.timeout(5):
        assert (await second.call("get", entity_id=PLAYER))["success"]
        reply = await second.call("next", entity_id=PLAYER)
        first = await playing
    assert not first["success"]
    assert not reply["success"]
    assert "did not answer" in reply["error"]["message"]
