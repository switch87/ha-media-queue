"""Tests for the automatic "Most played" playlist."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.media_queue import library as library_module
from custom_components.media_queue.history import ListeningHistory
from custom_components.media_queue.library import MOST_PLAYED_ID, PlaylistLibrary
from custom_components.media_queue.model import QueueItem

LOCAL = "media-source://media_source/local"


def _track(name: str) -> QueueItem:
    return QueueItem(
        media_content_id=f"{LOCAL}/Album/{name}.mp3",
        media_content_type="audio/mpeg",
        title=name.upper(),
        artist="Band",
        duration=100.0,
    )


async def _library(hass: HomeAssistant, *plays: str) -> PlaylistLibrary:
    history = ListeningHistory(hass)
    await history.async_load()
    for name in plays:
        history.record(_track(name))
    library = PlaylistLibrary(hass, history)
    await library.async_load()
    return library


def _key(err: pytest.ExceptionInfo[ServiceValidationError]) -> str | None:
    return err.value.translation_key


async def test_hidden_while_nothing_was_played(hass: HomeAssistant) -> None:
    """No plays, no "Most played"."""
    library = await _library(hass)
    assert library.summaries() == []
    with pytest.raises(ServiceValidationError) as err:
        library.get(MOST_PLAYED_ID)
    assert _key(err) == "unknown_playlist"
    await library.async_unload()


async def test_listed_first_and_read_only(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """It comes before the saved playlists and says it is read-only."""
    freezer.move_to("2026-10-07 10:00:00+00:00")
    library = await _library(hass, "a", "b", "a")
    library.save("Another", [_track("x")], overwrite=False)
    summaries = library.summaries()
    assert summaries[0] == {
        "id": MOST_PLAYED_ID,
        "name": "Most played",
        "count": 2,
        "duration": 200.0,
        "created": "2026-10-07T10:00:00+00:00",
        "updated": "2026-10-07T10:00:00+00:00",
        "readonly": True,
    }
    assert summaries[1]["name"] == "Another"
    assert summaries[1]["readonly"] is False
    assert library.count == 1  # stored playlists only
    await library.async_unload()


async def test_dutch_name(hass: HomeAssistant) -> None:
    """Dutch installations call it "Meest beluisterd"."""
    hass.config.language = "nl-BE"
    library = await _library(hass, "a")
    assert library.summaries()[0]["name"] == "Meest beluisterd"
    assert library.named("meest beluisterd").playlist_id == MOST_PLAYED_ID
    await library.async_unload()


async def test_tracks_by_count_then_last_played_and_capped(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Most played first; ties: the last played first; at most the cap."""
    history = ListeningHistory(hass)
    await history.async_load()
    for name in ("a", "b", "b", "c"):
        freezer.tick(timedelta(minutes=1))
        history.record(_track(name))
    library = PlaylistLibrary(hass, history)
    await library.async_load()

    playlist = library.get(MOST_PLAYED_ID)
    assert [item.title for item in playlist.items] == ["B", "C", "A"]
    with patch.object(library_module, "MOST_PLAYED_MAX", 2):
        assert [i.title for i in library.get(MOST_PLAYED_ID).items] == ["B", "C"]

    # It follows the history: a new play changes it right away.
    history.record(_track("a"))
    history.record(_track("a"))
    assert library.get(MOST_PLAYED_ID).items[0].title == "A"
    await library.async_unload()


async def test_one_track_of_it_can_be_loaded(hass: HomeAssistant) -> None:
    """Item ids stay the same between two looks, so a track can be picked."""
    library = await _library(hass, "a", "b")
    second = library.get(MOST_PLAYED_ID).items[1]
    assert library.load(MOST_PLAYED_ID, second.item_id) == [second]
    await library.async_unload()


@pytest.mark.parametrize("overwrite", [False, True])
async def test_cannot_be_overwritten(hass: HomeAssistant, overwrite: bool) -> None:
    """Saving under its name is refused, also with overwrite."""
    library = await _library(hass, "a")
    with pytest.raises(ServiceValidationError) as err:
        library.save("MOST PLAYED", [_track("x")], overwrite=overwrite)
    assert _key(err) == "playlist_readonly"
    await library.async_unload()


async def test_cannot_be_renamed_or_deleted(hass: HomeAssistant) -> None:
    """Rename and delete are refused; another playlist cannot take its name."""
    library = await _library(hass, "a")
    with pytest.raises(ServiceValidationError) as err:
        library.rename(MOST_PLAYED_ID, "Mine")
    assert _key(err) == "playlist_readonly"
    with pytest.raises(ServiceValidationError) as err:
        library.delete(MOST_PLAYED_ID)
    assert _key(err) == "playlist_readonly"
    other = library.save("Other", [_track("x")], overwrite=False)
    with pytest.raises(ServiceValidationError) as err:
        library.rename(other.playlist_id, "most played")
    assert _key(err) == "playlist_exists"
    assert library.get(MOST_PLAYED_ID).name == "Most played"
    await library.async_unload()


async def test_not_stored_with_the_playlists(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """It is built from the history, never written as a playlist."""
    library = await _library(hass, "a")
    await library.async_unload()
    assert hass_storage["media_queue.playlists"]["data"] == {"playlists": []}
