"""Tests for the actions (services) for automations and scripts."""

from pathlib import Path

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized, UnknownUser
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
import voluptuous as vol

from custom_components.media_queue.const import DOMAIN

from .common import LOCAL, PLAYER, PlayerLog, async_setup_library


@pytest.fixture
async def log(hass: HomeAssistant, tmp_path: Path) -> PlayerLog:
    """Set up the library and the integration; record play_media."""
    await async_setup_library(hass, tmp_path)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return PlayerLog(hass)


async def _call(
    hass: HomeAssistant, service: str, *, response: bool = False, **data: object
) -> object:
    return await hass.services.async_call(
        DOMAIN,
        service,
        {"entity_id": PLAYER, **data},
        blocking=True,
        return_response=response,
    )


async def test_add_and_control(hass: HomeAssistant, log: PlayerLog) -> None:
    """An automation can fill the queue and steer it."""
    result = await _call(
        hass,
        "add",
        response=True,
        media_content_id=f"{LOCAL}/Yeti",
        media_content_type="",
        mode="replace",
    )
    assert result == {"added": 5, "truncated": False, "limit": 1000}
    await _call(
        hass,
        "add",
        media_content_id=f"{LOCAL}/Yeti/a.mp3",
        media_content_type="audio/mpeg",
        title="a again",
    )
    await _call(hass, "next")
    await _call(hass, "previous")
    await _call(hass, "play_index", index=4)
    await _call(hass, "remove", index=0)
    await _call(hass, "move", from_index=0, to_index=1)
    assert log.played == ["a.mp3", "b.mp3", "a.mp3", "e.mp3"]

    queue = await _call(hass, "get_queue", response=True)
    assert isinstance(queue, dict)
    assert [item["title"] for item in queue["items"]] == [
        "c.mp3",
        "b.mp3",
        "d.mp3",
        "e.mp3",
        "a again",
    ]
    assert queue["current"] == 3

    await _call(hass, "clear")
    queue = await _call(hass, "get_queue", response=True)
    assert isinstance(queue, dict)
    assert queue["items"] == []


async def test_errors(hass: HomeAssistant, log: PlayerLog) -> None:
    """Bad input is refused with translated errors."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "remove", index=2)
    assert err.value.translation_key == "invalid_index"
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "clear", {"entity_id": "light.kitchen"}, blocking=True
        )


async def test_permissions(
    hass: HomeAssistant, log: PlayerLog, hass_read_only_user: MockUser
) -> None:
    """Users who may not control the player cannot change its queue."""
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "clear",
            {"entity_id": PLAYER},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    with pytest.raises(UnknownUser):
        await hass.services.async_call(
            DOMAIN,
            "clear",
            {"entity_id": PLAYER},
            blocking=True,
            context=Context(user_id="nobody"),
        )
    queue = await hass.services.async_call(
        DOMAIN,
        "get_queue",
        {"entity_id": PLAYER},
        blocking=True,
        return_response=True,
        context=Context(user_id=hass_read_only_user.id),
    )
    assert queue is not None
    assert queue["items"] == []


async def test_by_item_id(hass: HomeAssistant, log: PlayerLog) -> None:
    """Actions accept an item id instead of a position."""
    await _call(hass, "add", media_content_id=f"{LOCAL}/Yeti", media_content_type="")
    queue = await _call(hass, "get_queue", response=True)
    assert isinstance(queue, dict)
    ids = [item["id"] for item in queue["items"]]
    await _call(hass, "remove", item_id=ids[0])
    await _call(hass, "move", item_id=ids[4], to_index=0)
    await _call(hass, "play_index", item_id=ids[2])
    queue = await _call(hass, "get_queue", response=True)
    assert isinstance(queue, dict)
    assert [item["id"] for item in queue["items"]] == [ids[4], ids[1], ids[2], ids[3]]
    assert log.played == ["c.mp3"]
    with pytest.raises(vol.Invalid):
        await _call(hass, "remove")
