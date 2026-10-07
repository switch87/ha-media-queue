"""Tests for the playlist commands of the websocket API."""

from pathlib import Path

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.media_queue.const import DOMAIN
from custom_components.media_queue.websocket import can_manage_playlists

from .common import LOCAL, PLAYER, PlayerLog, async_setup_library
from .test_websocket import Client

OTHER = "media_player.kitchen"
FOLDER = {
    "media_content_id": f"{LOCAL}/Yeti",
    "media_content_type": "",
    "can_expand": True,
}


@pytest.fixture
async def entry(hass: HomeAssistant, tmp_path: Path) -> MockConfigEntry:
    """Set up the library folder, two players and the integration."""
    await async_setup_library(hass, tmp_path)
    hass.states.async_set(PLAYER, "idle")
    hass.states.async_set(OTHER, "idle")
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def client(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, entry: MockConfigEntry
) -> Client:
    """Return a websocket client; play_media is recorded."""
    PlayerLog(hass)
    return Client(await hass_ws_client(hass))


async def _saved(client: Client, name: str = "Yeti mix") -> str:
    await client.call("add", entity_id=PLAYER, mode="add", **FOLDER)
    reply = await client.call("playlists/save", entity_id=PLAYER, name=name)
    assert reply["success"], reply
    playlist_id: str = reply["result"]["id"]
    return playlist_id


async def test_save_list_get(client: Client) -> None:
    """Save a player's queue; list and get it."""
    playlist_id = await _saved(client)
    listed = (await client.call("playlists/list"))["result"]["playlists"]
    assert [(p["id"], p["name"], p["count"]) for p in listed] == [
        (playlist_id, "Yeti mix", 5)
    ]
    playlist = (await client.call("playlists/get", playlist_id=playlist_id))["result"]
    assert [item["title"] for item in playlist["items"]] == [
        f"{t}.mp3" for t in "abcde"
    ]


async def test_save_existing_name(client: Client) -> None:
    """An existing name is refused until overwrite is set."""
    playlist_id = await _saved(client)
    reply = await client.call("playlists/save", entity_id=PLAYER, name="YETI MIX")
    assert reply["error"]["translation_key"] == "playlist_exists"
    reply = await client.call(
        "playlists/save", entity_id=PLAYER, name="YETI MIX", overwrite=True
    )
    assert reply["result"]["id"] == playlist_id
    assert reply["result"]["name"] == "YETI MIX"


async def test_save_an_empty_or_unknown_queue(client: Client) -> None:
    """A player without items gives a clear error."""
    reply = await client.call("playlists/save", entity_id=OTHER, name="x")
    assert reply["error"]["translation_key"] == "playlist_empty"


async def test_load_rename_delete(client: Client) -> None:
    """Load into another player with a mode; one track; rename; delete."""
    playlist_id = await _saved(client)
    reply = await client.call(
        "playlists/load", entity_id=OTHER, playlist_id=playlist_id, mode="add"
    )
    assert reply["result"] == {"added": 5, "truncated": False, "limit": 1000}
    playlist = (await client.call("playlists/get", playlist_id=playlist_id))["result"]
    reply = await client.call(
        "playlists/load",
        entity_id=OTHER,
        playlist_id=playlist_id,
        item_id=playlist["items"][2]["id"],
    )
    assert reply["result"]["added"] == 1
    queue = (await client.call("get", entity_id=OTHER))["result"]
    assert [item["title"] for item in queue["items"]][-1] == "c.mp3"

    reply = await client.call(
        "playlists/rename", playlist_id=playlist_id, name=" Yeti 2 "
    )
    assert reply["result"]["name"] == "Yeti 2"
    assert (await client.call("playlists/delete", playlist_id=playlist_id))["success"]
    reply = await client.call("playlists/get", playlist_id=playlist_id)
    assert reply["error"]["translation_key"] == "unknown_playlist"
    assert (await client.call("playlists/list"))["result"]["playlists"] == []


async def test_bad_input(client: Client) -> None:
    """Names that are too long and unknown modes are refused by the schema."""
    reply = await client.call("playlists/save", entity_id=PLAYER, name="x" * 300)
    assert reply["error"]["code"] == "invalid_format"
    reply = await client.call(
        "playlists/load", entity_id=PLAYER, playlist_id="p", mode="shuffle"
    )
    assert reply["error"]["code"] == "invalid_format"


async def test_read_only_user(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
    client: Client,
) -> None:
    """Read-only users see the playlists but change nothing."""
    playlist_id = await _saved(client)
    reader = Client(await hass_ws_client(hass, hass_read_only_access_token))
    assert (await reader.call("playlists/list"))["success"]
    assert (await reader.call("playlists/get", playlist_id=playlist_id))["success"]
    for command, data in (
        ("playlists/save", {"entity_id": PLAYER, "name": "x"}),
        ("playlists/load", {"entity_id": PLAYER, "playlist_id": playlist_id}),
        ("playlists/rename", {"playlist_id": playlist_id, "name": "x"}),
        ("playlists/delete", {"playlist_id": playlist_id}),
    ):
        reply = await reader.call(command, **data)
        assert reply["error"]["code"] == "unauthorized", command


async def test_who_may_manage_playlists(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    hass_read_only_user: MockUser,
) -> None:
    """Admins, and users who may control at least one media player."""
    user_group = await hass.auth.async_get_group(GROUP_ID_USER)
    user = MockUser(groups=[user_group]).add_to_hass(hass)
    assert can_manage_playlists(hass, hass_admin_user)
    assert not can_manage_playlists(hass, user)  # no media players at all
    assert not can_manage_playlists(hass, hass_read_only_user)
    hass.states.async_set(PLAYER, "idle")
    assert can_manage_playlists(hass, user)
    assert not can_manage_playlists(hass, hass_read_only_user)
