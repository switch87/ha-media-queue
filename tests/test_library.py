"""Tests for the playlist library: validation, limits and storage."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.media_queue import library as library_module
from custom_components.media_queue.const import SAVE_DELAY
from custom_components.media_queue.library import (
    PLAYLIST_STORAGE_KEY,
    Playlist,
    PlaylistLibrary,
)
from custom_components.media_queue.model import QueueItem


def _items(*titles: str, duration: float | None = None) -> list[QueueItem]:
    return [
        QueueItem(
            media_content_id=f"media-source://media_source/local/{title}.mp3",
            media_content_type="audio/mpeg",
            title=title,
            artist="Band",
            duration=duration,
        )
        for title in titles
    ]


async def _library(hass: HomeAssistant) -> PlaylistLibrary:
    library = PlaylistLibrary(hass)
    await library.async_load()
    return library


def _key(err: pytest.ExceptionInfo[ServiceValidationError]) -> str | None:
    return err.value.translation_key


async def test_save_get_and_list(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A saved playlist has its own item ids, a summary and timestamps."""
    library = await _library(hass)
    items = _items("a", "b", duration=60)
    saved = library.save("  Zondag ochtend ", items, overwrite=False)

    assert saved.name == "Zondag ochtend"
    assert [item.title for item in saved.items] == ["a", "b"]
    assert {item.item_id for item in saved.items}.isdisjoint(
        item.item_id for item in items
    )
    assert library.get(saved.playlist_id) is saved
    now = dt_util.utcnow().isoformat()
    assert library.summaries() == [
        {
            "id": saved.playlist_id,
            "name": "Zondag ochtend",
            "count": 2,
            "duration": 120.0,
            "created": now,
            "updated": now,
        }
    ]
    data = saved.as_dict()
    assert data["items"][0]["title"] == "a"
    assert data["name"] == "Zondag ochtend"
    assert library.count == 1
    assert library.item_count == 2


async def test_summaries_sorted_and_duration_unknown(hass: HomeAssistant) -> None:
    """Playlists are listed by name regardless of case; no durations: None."""
    library = await _library(hass)
    library.save("beta", _items("a"), overwrite=False)
    library.save("Alfa", _items("b"), overwrite=False)
    library.save("gamma", _items("c", duration=10) + _items("d"), overwrite=False)
    summaries = library.summaries()
    assert [s["name"] for s in summaries] == ["Alfa", "beta", "gamma"]
    assert summaries[0]["duration"] is None
    assert summaries[2]["duration"] == 10.0


async def test_existing_name_needs_overwrite(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The same name (any case) is refused, unless overwrite keeps its id."""
    library = await _library(hass)
    first = library.save("Rock", _items("a"), overwrite=False)
    created = first.created
    with pytest.raises(ServiceValidationError) as err:
        library.save("ROCK", _items("b"), overwrite=False)
    assert _key(err) == "playlist_exists"

    freezer.tick(timedelta(minutes=1))
    again = library.save("ROCK", _items("b", "c"), overwrite=True)
    assert again.playlist_id == first.playlist_id
    assert again.name == "ROCK"
    assert [item.title for item in again.items] == ["b", "c"]
    assert again.created == created
    assert again.updated != created
    assert library.count == 1


@pytest.mark.parametrize("name", ["", "   ", "x" * 101, None, 5])
async def test_invalid_names(hass: HomeAssistant, name: Any) -> None:
    """Names are 1 to 100 characters after trimming."""
    library = await _library(hass)
    with pytest.raises(ServiceValidationError) as err:
        library.save(name, _items("a"), overwrite=False)
    assert _key(err) == "invalid_name"


async def test_limits(hass: HomeAssistant) -> None:
    """Empty and too long playlists and too many playlists are refused."""
    library = await _library(hass)
    with pytest.raises(ServiceValidationError) as err:
        library.save("x", [], overwrite=False)
    assert _key(err) == "playlist_empty"
    with (
        patch.object(library_module, "PLAYLIST_ITEMS", 2),
        pytest.raises(ServiceValidationError) as err,
    ):
        library.save("x", _items("a", "b", "c"), overwrite=False)
    assert _key(err) == "playlist_too_long"
    with patch.object(library_module, "PLAYLISTS_MAX", 1):
        library.save("one", _items("a"), overwrite=False)
        library.save("ONE", _items("b"), overwrite=True)  # overwriting is fine
        with pytest.raises(ServiceValidationError) as err:
            library.save("two", _items("a"), overwrite=False)
    assert _key(err) == "too_many_playlists"


async def test_rename_and_delete(hass: HomeAssistant) -> None:
    """Rename keeps the id (own name in another case is fine); delete removes."""
    library = await _library(hass)
    rock = library.save("Rock", _items("a"), overwrite=False)
    jazz = library.save("Jazz", _items("b"), overwrite=False)
    library.rename(rock.playlist_id, " Hard rock ")
    assert library.get(rock.playlist_id).name == "Hard rock"
    library.rename(rock.playlist_id, "HARD ROCK")
    assert library.get(rock.playlist_id).name == "HARD ROCK"
    with pytest.raises(ServiceValidationError) as err:
        library.rename(rock.playlist_id, "jazz")
    assert _key(err) == "playlist_exists"

    library.delete(jazz.playlist_id)
    assert [s["name"] for s in library.summaries()] == ["HARD ROCK"]
    for action in (
        lambda: library.get("nope"),
        lambda: library.delete("nope"),
        lambda: library.rename("nope", "x"),
    ):
        with pytest.raises(ServiceValidationError) as err:
            action()
        assert _key(err) == "unknown_playlist"


async def test_find_by_name(hass: HomeAssistant) -> None:
    """Automations name playlists; the case does not matter."""
    library = await _library(hass)
    rock = library.save("Rock", _items("a"), overwrite=False)
    assert library.named(" rock ") is rock
    with pytest.raises(ServiceValidationError) as err:
        library.named("Pop")
    assert _key(err) == "unknown_playlist"


async def test_saved_delayed_and_restored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Changes are written after the delay and come back on load."""
    library = await _library(hass)
    rock = library.save("Rock", _items("a", "b", duration=5), overwrite=False)
    assert PLAYLIST_STORAGE_KEY not in hass_storage
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()
    stored = hass_storage[PLAYLIST_STORAGE_KEY]
    assert stored["version"] == 1
    assert stored["data"]["playlists"][0]["name"] == "Rock"

    restored = await _library(hass)
    again = restored.get(rock.playlist_id)
    assert again.name == "Rock"
    assert again.items == rock.items
    assert again.created == rock.created


async def test_unload_saves_now(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Unloading writes pending changes."""
    library = await _library(hass)
    library.save("Rock", _items("a"), overwrite=False)
    await library.async_unload()
    assert len(hass_storage[PLAYLIST_STORAGE_KEY]["data"]["playlists"]) == 1


def _stored_playlist(playlist_id: Any, name: Any, **extra: Any) -> dict[str, Any]:
    return {
        "id": playlist_id,
        "name": name,
        "items": [
            {
                "id": "i1",
                "media_content_id": "http://radio/stream",
                "media_content_type": "music",
                "title": "Radio",
            },
            "bad",
        ],
        "created": "2026-10-07T10:00:00+00:00",
        "updated": "2026-10-07T10:00:00+00:00",
        **extra,
    }


@pytest.mark.parametrize(
    ("data", "names"),
    [
        (None, []),
        ({"playlists": "x"}, []),
        (
            {
                "playlists": [
                    _stored_playlist("p1", "Radio"),
                    _stored_playlist("p2", "radio"),  # same name: dropped
                    _stored_playlist("p1", "Other"),  # same id: dropped
                    _stored_playlist("p3", 7),  # bad name
                    _stored_playlist("p4", "Empty", items=[]),
                    _stored_playlist("p5", "No list", items="x"),
                    _stored_playlist(5, "Bad id"),
                    _stored_playlist("p6", "No times", created=3),
                    "junk",
                ]
            },
            ["Radio"],
        ),
    ],
)
async def test_bad_stored_data(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    data: Any,
    names: list[str],
) -> None:
    """Stored data that does not fit is dropped, never fatal."""
    hass_storage[PLAYLIST_STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": PLAYLIST_STORAGE_KEY,
        "data": data,
    }
    library = await _library(hass)
    assert [s["name"] for s in library.summaries()] == names
    if names:
        assert [item.title for item in library.get("p1").items] == ["Radio"]


def test_playlist_from_dict_round_trip() -> None:
    """A playlist survives serialisation."""
    playlist = Playlist(
        playlist_id="p",
        name="N",
        items=_items("a"),
        created="c",
        updated="u",
    )
    assert Playlist.from_dict(playlist.as_dict()) == playlist
