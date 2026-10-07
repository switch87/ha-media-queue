"""Tests for the websocket API used by the panel."""

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.media_queue.const import DOMAIN

from .common import LOCAL, PLAYER, PlayerLog, async_setup_library

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
    """Record play_media calls (registered after media_player's own service)."""
    return PlayerLog(hass)


class Client:
    """A websocket client that numbers its messages."""

    def __init__(self, ws: Any) -> None:
        """Wrap the test client."""
        self.ws = ws

        self.events: list[dict[str, Any]] = []

    async def call(self, command: str, **data: Any) -> dict[str, Any]:
        """Send a media_queue command and return the reply; keep events."""
        await self.ws.send_json_auto_id({"type": f"media_queue/{command}", **data})
        while True:
            reply: dict[str, Any] = await self.ws.receive_json()
            if reply["type"] == "result":
                return reply
            self.events.append(reply)


@pytest.fixture
async def client(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, log: PlayerLog
) -> Client:
    """Return a websocket client of an ordinary user."""
    return Client(await hass_ws_client(hass))


async def test_get_empty(client: Client) -> None:
    """A player without a queue has an empty one."""
    reply = await client.call("get", entity_id=PLAYER)
    assert reply["success"]
    assert reply["result"] == {
        "entity_id": PLAYER,
        "items": [],
        "current": None,
        "next": None,
        "shuffle": False,
        "repeat": "off",
        "phase": "idle",
        "last_error": None,
    }


async def test_add_play_and_edit(client: Client, log: PlayerLog) -> None:
    """The panel's whole flow: add, jump, remove, move, next, previous, clear."""
    reply = await client.call("add", entity_id=PLAYER, mode="replace", **FOLDER)
    assert reply["result"] == {"added": 5, "truncated": False, "limit": 1000}
    assert log.played == ["a.mp3"]

    reply = await client.call(
        "add",
        entity_id=PLAYER,
        media_content_id=f"{LOCAL}/Yeti/e.mp3",
        media_content_type="audio/mpeg",
        title="e again",
        media_class="music",
        thumbnail=None,
        can_expand=False,
        mode="next",
    )
    assert reply["result"]["added"] == 1

    assert (await client.call("play_index", entity_id=PLAYER, index=3))["success"]
    assert (await client.call("remove", entity_id=PLAYER, index=0))["success"]
    assert (await client.call("move", entity_id=PLAYER, from_index=0, to_index=4))[
        "success"
    ]
    assert (await client.call("next", entity_id=PLAYER))["success"]
    assert (await client.call("previous", entity_id=PLAYER))["success"]

    reply = await client.call("get", entity_id=PLAYER)
    titles = [item["title"] for item in reply["result"]["items"]]
    assert titles == ["b.mp3", "c.mp3", "d.mp3", "e.mp3", "e again"]
    assert reply["result"]["current"] == 1
    assert log.played == ["a.mp3", "c.mp3", "d.mp3", "c.mp3"]

    assert (await client.call("clear", entity_id=PLAYER))["success"]
    reply = await client.call("get", entity_id=PLAYER)
    assert reply["result"]["items"] == []


async def test_add_defaults_to_add_mode(client: Client, log: PlayerLog) -> None:
    """Without a mode, items are appended and nothing plays."""
    reply = await client.call(
        "add",
        entity_id=PLAYER,
        media_content_id=f"{LOCAL}/Yeti/a.mp3",
        media_content_type="audio/mpeg",
    )
    assert reply["result"]["added"] == 1
    assert log.calls == []


async def test_subscribe(
    hass: HomeAssistant, client: Client, entry: MockConfigEntry
) -> None:
    """Subscribers get the queue now and on every change, until they stop."""
    reply = await client.call("subscribe", entity_id=PLAYER)
    subscription = reply["id"]
    assert reply["success"]
    event = await client.ws.receive_json()
    assert event["id"] == subscription
    assert event["event"]["items"] == []

    await client.call("add", entity_id=PLAYER, mode="add", **FOLDER)
    [event] = client.events
    assert event["id"] == subscription
    assert len(event["event"]["items"]) == 5

    await client.ws.send_json_auto_id(
        {"type": "unsubscribe_events", "subscription": subscription}
    )
    assert (await client.ws.receive_json())["success"]
    reply = await client.call("clear", entity_id=PLAYER)
    assert reply["success"]
    assert len(client.events) == 1  # no event after unsubscribing


async def test_errors_are_translated(hass: HomeAssistant, client: Client) -> None:
    """Command errors carry the translation key for the panel."""
    hass.states.async_set(PLAYER, "idle")
    reply = await client.call("remove", entity_id=PLAYER, index=4)
    assert not reply["success"]
    assert reply["error"]["code"] == "home_assistant_error"
    assert reply["error"]["translation_key"] == "invalid_index"
    assert reply["error"]["translation_domain"] == DOMAIN

    reply = await client.call("next", entity_id=PLAYER)
    assert reply["error"]["translation_key"] == "end_of_queue"


async def test_only_media_players(client: Client) -> None:
    """Entity ids of other domains are refused."""
    reply = await client.call("get", entity_id="light.kitchen")
    assert reply["error"]["code"] == "invalid_format"


async def test_not_loaded(
    hass: HomeAssistant, client: Client, entry: MockConfigEntry
) -> None:
    """Without a loaded entry the commands say so."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    reply = await client.call("get", entity_id=PLAYER)
    assert reply["error"]["translation_key"] == "not_loaded"


async def test_read_only_user(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
    log: PlayerLog,
) -> None:
    """A user who may only read entities sees the queue but cannot change it."""
    client = Client(await hass_ws_client(hass, hass_read_only_access_token))
    assert (await client.call("get", entity_id=PLAYER))["success"]
    reply = await client.call("add", entity_id=PLAYER, mode="add", **FOLDER)
    assert reply["error"]["code"] == "unauthorized"
    reply = await client.call("clear", entity_id=PLAYER)
    assert reply["error"]["code"] == "unauthorized"


async def test_reload_closes_and_resubscribe_works(
    hass: HomeAssistant, client: Client, entry: MockConfigEntry
) -> None:
    """A reload ends the subscription with a closed event; a new one works."""
    reply = await client.call("subscribe", entity_id=PLAYER)
    subscription = reply["id"]
    await client.ws.receive_json()  # the initial snapshot
    assert await hass.config_entries.async_reload(entry.entry_id)
    event = await client.ws.receive_json(timeout=5)
    assert event["id"] == subscription
    assert event["event"] == {"entity_id": PLAYER, "closed": True}

    reply = await client.call("subscribe", entity_id=PLAYER)
    assert reply["success"]
    await client.call("add", entity_id=PLAYER, mode="add", **FOLDER)
    assert client.events[-1]["id"] == reply["id"]


async def test_commands_by_item_id(client: Client, log: PlayerLog) -> None:
    """The panel names items by id, so a queue changed meanwhile is no problem."""
    await client.call("add", entity_id=PLAYER, mode="add", **FOLDER)
    items = (await client.call("get", entity_id=PLAYER))["result"]["items"]
    ids = [item["id"] for item in items]
    await client.call("remove", entity_id=PLAYER, index=0)  # someone else

    assert (await client.call("remove", entity_id=PLAYER, item_id=ids[2]))["success"]
    assert (await client.call("move", entity_id=PLAYER, item_id=ids[4], to_index=0))[
        "success"
    ]
    assert (await client.call("play_index", entity_id=PLAYER, item_id=ids[3]))[
        "success"
    ]
    result = (await client.call("get", entity_id=PLAYER))["result"]
    assert [item["id"] for item in result["items"]] == [ids[4], ids[1], ids[3]]
    assert result["current"] == 2
    assert log.played == ["d.mp3"]

    reply = await client.call("remove", entity_id=PLAYER, item_id=ids[0])
    assert reply["error"]["translation_key"] == "unknown_item"
    reply = await client.call("remove", entity_id=PLAYER)
    assert reply["error"]["code"] == "invalid_format"


async def test_unknown_player_is_refused_without_creating_a_queue(
    hass: HomeAssistant, client: Client, entry: MockConfigEntry
) -> None:
    """Commands other than add need a player that exists (or has a queue)."""
    for command, data in (
        ("clear", {}),
        ("next", {}),
        ("previous", {}),
        ("remove", {"index": 0}),
        ("move", {"from_index": 0, "to_index": 0}),
        ("play_index", {"index": 0}),
    ):
        reply = await client.call(command, entity_id="media_player.ghost", **data)
        assert reply["error"]["translation_key"] == "unknown_player", command
    assert entry.runtime_data.entity_ids == []

    hass.states.async_set("media_player.ghost", "idle")
    assert (await client.call("clear", entity_id="media_player.ghost"))["success"]
