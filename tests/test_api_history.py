"""Tests for reading and resetting the listening history (websocket, actions)."""

from pathlib import Path
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized, UnknownUser
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.media_queue.const import DOMAIN
from custom_components.media_queue.history import ListeningHistory
from custom_components.media_queue.model import QueueItem

from .common import LOCAL, PLAYER, async_setup_library
from .test_websocket import Client


@pytest.fixture
async def history(hass: HomeAssistant, tmp_path: Path) -> ListeningHistory:
    """Set up the integration with a player; return its history with plays."""
    await async_setup_library(hass, tmp_path)
    hass.states.async_set(PLAYER, "idle")
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    history: ListeningHistory = entry.runtime_data.history
    for name in ("a", "b", "a"):
        history.record(
            QueueItem(
                media_content_id=f"{LOCAL}/Yeti/{name}.mp3",
                media_content_type="audio/mpeg",
                title=name.upper(),
                duration=100.0,
            )
        )
    return history


async def test_websocket_list_and_reset(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    history: ListeningHistory,
) -> None:
    """List the most played (with a limit), then reset."""
    client = Client(await hass_ws_client(hass))
    reply = await client.call("history/list")
    assert reply["success"], reply
    result = reply["result"]
    assert [t["title"] for t in result["tracks"]] == ["A", "B"]
    assert (result["track_count"], result["play_count"]) == (2, 3)
    assert result["tracks"][0]["count"] == 2

    limited = await client.call("history/list", limit=1)
    assert [t["title"] for t in limited["result"]["tracks"]] == ["A"]
    assert (await client.call("history/list", limit=0))["error"][
        "code"
    ] == "invalid_format"

    assert (await client.call("history/reset"))["success"]
    assert history.track_count == 0


async def test_websocket_read_only_user(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
    history: ListeningHistory,
) -> None:
    """Read-only users may read the history, not reset it."""
    reader = Client(await hass_ws_client(hass, hass_read_only_access_token))
    assert (await reader.call("history/list"))["success"]
    assert (await reader.call("history/reset"))["error"]["code"] == "unauthorized"
    assert history.track_count == 2


async def test_actions(
    hass: HomeAssistant,
    history: ListeningHistory,
    hass_read_only_user: MockUser,
    hass_admin_user: MockUser,
) -> None:
    """get_history answers everyone; reset_history needs a manager."""
    reader = Context(user_id=hass_read_only_user.id)
    response = await hass.services.async_call(
        DOMAIN,
        "get_history",
        {"limit": 1},
        blocking=True,
        return_response=True,
        context=reader,
    )
    assert response is not None
    result: dict[str, Any] = dict(response)
    assert [t["title"] for t in result["tracks"]] == ["A"]
    assert result["play_count"] == 3

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, "reset_history", {}, blocking=True, context=reader
        )
    with pytest.raises(UnknownUser):
        await hass.services.async_call(
            DOMAIN,
            "reset_history",
            {},
            blocking=True,
            context=Context(user_id="nobody"),
        )
    await hass.services.async_call(
        DOMAIN,
        "reset_history",
        {},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    assert history.track_count == 0
