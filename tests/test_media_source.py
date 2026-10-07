"""Tests for the playlists as a media source in HA's own media browser."""

from pathlib import Path

from homeassistant.components import media_source
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_source import Unresolvable
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.media_queue.const import DOMAIN
from custom_components.media_queue.media_source import async_get_media_source
from custom_components.media_queue.model import QueueItem

from .common import async_setup_library

ROOT = f"media-source://{DOMAIN}"


@pytest.fixture
async def entry(hass: HomeAssistant, tmp_path: Path) -> MockConfigEntry:
    """Set up the media source and the integration."""
    await async_setup_library(hass, tmp_path)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _items() -> list[QueueItem]:
    return [
        QueueItem(
            media_content_id="media-source://media_source/local/Yeti/a.mp3",
            media_content_type="audio/mpeg",
            title="Soap Shop Rock",
            artist="Amon Düül II",
            thumbnail="/api/brands/x.png",
        ),
        QueueItem(
            media_content_id="http://radio/stream",
            media_content_type="music",
            title="Radio",
        ),
    ]


async def test_playlists_in_the_media_browser(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Playlists list their tracks, each playable with its original id."""
    library = entry.runtime_data.library
    mix = library.save("Mix", _items(), overwrite=False)
    library.save("Another", _items()[1:], overwrite=False)

    root = await media_source.async_browse_media(hass, ROOT)
    assert root.title == "Playlists (Media queue)"
    assert root.can_play is False
    assert [child.title for child in root.children or []] == ["Another", "Mix"]
    node = (root.children or [])[1]
    assert node.media_content_id == f"{ROOT}/{mix.playlist_id}"
    assert node.can_expand is True
    assert node.can_play is False

    listed = await media_source.async_browse_media(hass, node.media_content_id)
    assert listed.title == "Mix"
    children = listed.children or []
    assert [(c.title, c.media_content_id, c.can_play) for c in children] == [
        (
            "Soap Shop Rock – Amon Düül II",
            "media-source://media_source/local/Yeti/a.mp3",
            True,
        ),
        ("Radio", "http://radio/stream", True),
    ]
    assert children[0].thumbnail == "/api/brands/x.png"


async def test_the_source_is_listed_with_the_others(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """HA's media browser shows the source next to the other sources."""
    root = await media_source.async_browse_media(hass, None)
    assert ROOT in [child.media_content_id for child in root.children or []]


async def test_a_playlist_is_not_played_from_here(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Playing a whole playlist is the Muziek page's job."""
    playlist = entry.runtime_data.library.save("Mix", _items(), overwrite=False)
    with pytest.raises(Unresolvable):
        await media_source.async_resolve_media(
            hass, f"{ROOT}/{playlist.playlist_id}", None
        )


async def test_unknown_playlist_and_not_loaded(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A deleted playlist or an unloaded integration cannot be browsed."""
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(hass, f"{ROOT}/nope")
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(hass, ROOT)


async def test_dutch_name(hass: HomeAssistant) -> None:
    """Dutch installations see the Dutch name."""
    hass.config.language = "nl"
    source = await async_get_media_source(hass)
    assert source.name == "Afspeellijsten (Muziek)"
