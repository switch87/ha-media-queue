"""Tests for adding stream URLs to a queue and saving them as favourites."""

from pathlib import Path
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.media_queue import controller as controller_module
from custom_components.media_queue.const import DOMAIN
from custom_components.media_queue.manager import QueueManager

from .common import PLAYER, PlayerLog, async_setup_library
from .test_websocket import Client

RADIO = "http://radio.example/live"
M3U = "http://radio.example/list.m3u"


@pytest.fixture
async def manager(hass: HomeAssistant, tmp_path: Path) -> QueueManager:
    """Set up the integration with a player."""
    await async_setup_library(hass, tmp_path)
    hass.states.async_set(PLAYER, "idle")
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result: QueueManager = entry.runtime_data
    return result


@pytest.fixture
def log(hass: HomeAssistant, manager: QueueManager) -> PlayerLog:
    """Record play_media calls."""
    return PlayerLog(hass)


@pytest.fixture
async def client(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, log: PlayerLog
) -> Client:
    """Return a websocket client of an ordinary user."""
    return Client(await hass_ws_client(hass))


def _titles(manager: QueueManager) -> list[str]:
    return [item.title for item in manager.controller(PLAYER).queue.items]


async def test_play_a_stream_url(
    client: Client, manager: QueueManager, log: PlayerLog
) -> None:
    """Play puts the URL in the queue and sends it to the player as it is."""
    reply = await client.call(
        "add_url", entity_id=PLAYER, url=f"  {RADIO} ", mode="replace", title="Live"
    )
    assert reply["success"], reply
    assert reply["result"] == {"added": 1, "truncated": False, "limit": 1000}
    assert _titles(manager) == ["Live"]
    call = log.calls[0].data
    assert (call["media_content_id"], call["media_content_type"]) == (RADIO, "music")


async def test_next_and_add_modes(client: Client, manager: QueueManager) -> None:
    """The usual modes: add appends, next goes after the current item."""
    for url, mode in (
        ("http://a.example/1", "add"),
        ("http://a.example/2", "add"),
        ("http://a.example/3", "next"),
    ):
        reply = await client.call("add_url", entity_id=PLAYER, url=url, mode=mode)
        assert reply["success"], reply
    assert _titles(manager) == ["3", "1", "2"]


async def test_an_m3u_url_is_expanded(
    client: Client, manager: QueueManager, aioclient_mock: AiohttpClientMocker
) -> None:
    """A remote playlist becomes its streams."""
    aioclient_mock.get(M3U, text="#EXTINF:-1,One\nhttp://one/\nhttp://two/x\n")
    reply = await client.call("add_url", entity_id=PLAYER, url=M3U)
    assert reply["result"]["added"] == 2
    assert _titles(manager) == ["One", "x"]


async def test_bad_urls_are_explained(client: Client, manager: QueueManager) -> None:
    """A refused URL gives the translated message; the queue stays as it was."""
    reply = await client.call("add_url", entity_id=PLAYER, url="file:///etc/passwd")
    assert not reply["success"]
    assert "http://" in reply["error"]["message"]
    assert _titles(manager) == []


async def test_a_full_queue(
    client: Client, manager: QueueManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is fetched or added when the queue is full."""
    monkeypatch.setattr(controller_module, "QUEUE_LIMIT", 1)
    assert (await client.call("add_url", entity_id=PLAYER, url=RADIO))["success"]
    reply = await client.call("add_url", entity_id=PLAYER, url=M3U)
    assert reply["error"]["code"] == "home_assistant_error"
    assert "full" in reply["error"]["message"]


async def test_read_only_users_add_nothing(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
    log: PlayerLog,
) -> None:
    """Adding needs control of the player; saving a favourite a manager."""
    reader = Client(await hass_ws_client(hass, hass_read_only_access_token))
    for command, data in (
        ("add_url", {"entity_id": PLAYER, "url": RADIO}),
        ("streams/save", {"url": RADIO, "name": "Radio"}),
    ):
        reply = await reader.call(command, **data)
        assert reply["error"]["code"] == "unauthorized", command


async def test_save_a_favourite(
    client: Client, manager: QueueManager, aioclient_mock: AiohttpClientMocker
) -> None:
    """A favourite is a saved playlist of the stream(s)."""
    reply = await client.call("streams/save", url=RADIO, name="Radio 1")
    assert reply["success"], reply
    assert (reply["result"]["name"], reply["result"]["count"]) == ("Radio 1", 1)
    playlist = manager.library.named("radio 1")
    assert playlist.items[0].media_content_id == RADIO
    assert playlist.items[0].title == "Radio 1"

    again = await client.call("streams/save", url=RADIO, name="Radio 1")
    assert not again["success"]
    aioclient_mock.get(M3U, text="http://one/\nhttp://two/\n")
    replaced = await client.call(
        "streams/save", url=M3U, name="Radio 1", overwrite=True
    )
    assert replaced["result"]["count"] == 2
    bad = await client.call("streams/save", url="ftp://x/y", name="X")
    assert not bad["success"]


async def test_the_action(
    hass: HomeAssistant,
    manager: QueueManager,
    log: PlayerLog,
    hass_read_only_user: MockUser,
) -> None:
    """media_queue.add_url for automations, with the add count as response."""
    response: Any = await hass.services.async_call(
        DOMAIN,
        "add_url",
        {"entity_id": PLAYER, "url": RADIO, "mode": "play"},
        blocking=True,
        return_response=True,
    )
    assert response["added"] == 1
    assert log.calls[0].data["media_content_id"] == RADIO
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "add_url", {"entity_id": PLAYER, "url": "nope"}, blocking=True
        )
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "add_url",
            {"entity_id": PLAYER, "url": RADIO},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
