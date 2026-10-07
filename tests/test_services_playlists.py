"""Tests for the playlist actions."""

from pathlib import Path

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized, UnknownUser
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
import voluptuous as vol

from custom_components.media_queue.const import DOMAIN

from .common import LOCAL, PLAYER, PlayerLog, async_setup_library

OTHER = "media_player.kitchen"


@pytest.fixture
async def log(hass: HomeAssistant, tmp_path: Path) -> PlayerLog:
    """Set up the integration with two players; record play_media."""
    await async_setup_library(hass, tmp_path)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set(PLAYER, "idle")
    hass.states.async_set(OTHER, "idle")
    return PlayerLog(hass)


async def _call(
    hass: HomeAssistant,
    service: str,
    *,
    response: bool = False,
    context: Context | None = None,
    **data: object,
) -> object:
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=response, context=context
    )


async def test_save_load_rename_delete(hass: HomeAssistant, log: PlayerLog) -> None:
    """Automations work with playlists by name."""
    await _call(
        hass,
        "add",
        entity_id=PLAYER,
        media_content_id=f"{LOCAL}/Yeti",
        media_content_type="",
    )
    saved = await _call(
        hass, "save_playlist", response=True, entity_id=PLAYER, name="Morning"
    )
    assert isinstance(saved, dict)
    assert saved["name"] == "Morning"
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "save_playlist", entity_id=PLAYER, name="morning")
    assert err.value.translation_key == "playlist_exists"
    await _call(hass, "save_playlist", entity_id=PLAYER, name="morning", overwrite=True)

    result = await _call(
        hass,
        "load_playlist",
        response=True,
        entity_id=OTHER,
        name="MORNING",
        mode="replace",
    )
    assert result == {"added": 5, "truncated": False, "limit": 1000}
    assert log.played == ["a.mp3"]

    await _call(hass, "rename_playlist", name="morning", new_name="Evening")
    listed = await _call(hass, "get_playlists", response=True)
    assert isinstance(listed, dict)
    assert [p["name"] for p in listed["playlists"]] == ["Evening"]
    await _call(hass, "delete_playlist", name="evening")
    listed = await _call(hass, "get_playlists", response=True)
    assert listed == {"playlists": []}
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "delete_playlist", name="evening")
    assert err.value.translation_key == "unknown_playlist"
    with pytest.raises(vol.Invalid):
        await _call(hass, "rename_playlist", name="x")


async def test_permissions(
    hass: HomeAssistant,
    log: PlayerLog,
    hass_read_only_user: MockUser,
    hass_admin_user: MockUser,
) -> None:
    """Read-only users may list playlists but not change them; admins may."""
    reader = Context(user_id=hass_read_only_user.id)
    listed = await _call(hass, "get_playlists", response=True, context=reader)
    assert listed == {"playlists": []}
    data: dict[str, str]
    for service, data in (
        ("rename_playlist", {"name": "a", "new_name": "b"}),
        ("delete_playlist", {"name": "a"}),
        ("save_playlist", {"entity_id": PLAYER, "name": "a"}),
        ("load_playlist", {"entity_id": PLAYER, "name": "a"}),
    ):
        with pytest.raises(Unauthorized):
            await hass.services.async_call(
                DOMAIN, service, data, blocking=True, context=reader
            )
    admin = Context(user_id=hass_admin_user.id)
    await _call(
        hass,
        "add",
        entity_id=PLAYER,
        media_content_id=f"{LOCAL}/Yeti",
        media_content_type="",
    )
    await _call(hass, "save_playlist", entity_id=PLAYER, name="a")
    await _call(hass, "rename_playlist", context=admin, name="a", new_name="b")
    with pytest.raises(UnknownUser):
        await _call(
            hass, "delete_playlist", context=Context(user_id="nobody"), name="a"
        )
