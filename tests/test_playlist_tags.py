"""Tests for completing the tags of saved playlists (the Pi's 58-minute playlist)."""

from datetime import timedelta
from pathlib import Path
import threading
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.media_queue import enrich, tags
from custom_components.media_queue.const import SAVE_DELAY
from custom_components.media_queue.history import ListeningHistory
from custom_components.media_queue.library import PLAYLIST_STORAGE_KEY, PlaylistLibrary
from custom_components.media_queue.manager import QueueManager
from custom_components.media_queue.model import Mode, QueueItem
from custom_components.media_queue.tags import Tags

from .audio import write_mp3
from .common import PLAYER

LOCAL = "media-source://media_source/local"
STAMP = "2026-10-07T12:00:00+00:00"


@pytest.fixture
def album(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Tagged files a, b, c (2 s each) in a local media folder."""
    folder = tmp_path / "Album"
    folder.mkdir()
    for name in ("a", "b", "c"):
        write_mp3(folder / f"{name}.mp3", title=name.upper(), artist="Band", album="LP")
    hass.config.media_dirs = {"local": str(tmp_path)}
    return folder


def _item(name: str, **extra: Any) -> QueueItem:
    return QueueItem(
        media_content_id=f"{LOCAL}/Album/{name}.mp3",
        media_content_type="audio/mpeg",
        title=f"{name}.mp3",
        item_id=f"id-{name}",
        **extra,
    )


def _store(hass_storage: dict[str, Any], *items: QueueItem) -> None:
    hass_storage[PLAYLIST_STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": PLAYLIST_STORAGE_KEY,
        "data": {
            "playlists": [
                {
                    "id": "p1",
                    "name": "Mix",
                    "items": [item.as_dict() for item in items],
                    "created": STAMP,
                    "updated": STAMP,
                }
            ]
        },
    }


async def _loaded(hass: HomeAssistant) -> QueueManager:
    manager = QueueManager(hass)
    await manager.async_load()
    await hass.async_block_till_done(wait_background_tasks=True)
    return manager


async def test_stored_playlists_are_completed_at_setup(
    hass: HomeAssistant,
    album: Path,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Items without artist or duration get their tags; the store follows."""
    radio = QueueItem(
        media_content_id="http://radio.example/stream",
        media_content_type="music",
        title="Radio",
        item_id="id-radio",
    )
    _store(
        hass_storage,
        _item("a"),
        _item("b", artist="Band"),
        _item("c", artist="Kept", duration=99.0),
        _item("gone"),
        radio,
    )
    manager = await _loaded(hass)

    items = {item.item_id: item for item in manager.library.get("p1").items}
    assert (items["id-a"].title, items["id-a"].artist) == ("A", "Band")
    assert items["id-a"].album == "LP"
    assert items["id-a"].duration == pytest.approx(2.0, abs=0.1)
    assert items["id-b"].duration == pytest.approx(2.0, abs=0.1)
    # Complete items are left alone (not read: the title stays the file name).
    assert (items["id-c"].title, items["id-c"].artist) == ("c.mp3", "Kept")
    assert items["id-gone"] == _item("gone")
    assert items["id-radio"] == radio

    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    stored = hass_storage[PLAYLIST_STORAGE_KEY]["data"]["playlists"][0]["items"]
    assert stored[0]["artist"] == "Band"
    await manager.async_unload()


async def test_a_queue_saved_before_its_tags_were_read_is_completed(
    hass: HomeAssistant, album: Path
) -> None:
    """Saving right after an add stores file names; the library reads on."""
    manager = await _loaded(hass)
    queue = manager.controller(PLAYER).queue
    queue.add([_item("a"), _item("b")], Mode.ADD, limit=10)  # tags not read yet

    playlist = manager.library.save("Fresh", queue.items, overwrite=False)
    await hass.async_block_till_done(wait_background_tasks=True)

    saved = manager.library.get(playlist.playlist_id)
    assert [item.artist for item in saved.items] == ["Band", "Band"]
    assert saved.summary()["duration"] == pytest.approx(4.0, abs=0.2)
    await manager.async_unload()


async def test_loading_a_playlist_completes_it(
    hass: HomeAssistant, album: Path, hass_storage: dict[str, Any]
) -> None:
    """A file that appears later (a mount back online) is read at the load."""
    _store(hass_storage, _item("late"))
    manager = await _loaded(hass)
    assert manager.library.get("p1").items[0].artist is None
    write_mp3(album / "late.mp3", title="Late", artist="Band")

    items = manager.library.load("p1", None)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert items == [_item("late")]  # what is loaded now is what was there
    assert manager.library.get("p1").items[0].artist == "Band"
    await manager.async_unload()


async def test_each_item_is_read_once_and_rounds_do_not_overlap(
    hass: HomeAssistant, album: Path, hass_storage: dict[str, Any]
) -> None:
    """Files without an artist tag are not read again at every save."""
    write_mp3(album / "plain.mp3")  # no tags at all
    _store(hass_storage, _item("plain"))
    asked: list[list[str]] = []
    real = tags.read_batch

    def spy(files: list[tuple[str, str, str]], budget: float) -> Any:
        asked.append([relative for _, _, relative in files])
        return real(files, budget)

    with patch.object(enrich, "read_batch", spy):
        manager = await _loaded(hass)
        library = manager.library
        library.save("One", [_item("a")], overwrite=False)
        library.save("Two", [_item("b")], overwrite=False)  # while One is read
        library.repair()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert asked[0] == ["Album/plain.mp3"]
    assert sorted(name for batch in asked[1:] for name in batch) == [
        "Album/a.mp3",
        "Album/b.mp3",
    ]
    await manager.async_unload()


async def test_a_hung_mount_pauses_the_library_and_is_retried(
    hass: HomeAssistant,
    album: Path,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A batch that times out pauses the library; later the items are read."""
    _store(hass_storage, _item("a"))
    released = threading.Event()

    def hung(files: list[tuple[str, str, str]], budget: float) -> Any:
        released.wait(5)  # a mount that does not answer
        return len(files), {}

    with (
        patch.object(enrich, "read_batch", hung),
        patch.object(enrich, "TAG_TIMEOUT", 0),  # the blocked batch cannot be done
    ):
        manager = QueueManager(hass)
        await manager.async_load()
    released.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    library = manager.library
    assert library.get("p1").items[0].artist is None

    library.repair()  # paused: nothing happens
    await hass.async_block_till_done(wait_background_tasks=True)
    assert library.get("p1").items[0].artist is None

    freezer.tick(enrich.TAG_PAUSE + timedelta(seconds=1))
    library.repair()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert library.get("p1").items[0].artist == "Band"
    await manager.async_unload()


async def test_items_of_a_deleted_playlist_are_not_read(
    hass: HomeAssistant, album: Path, hass_storage: dict[str, Any]
) -> None:
    """A playlist deleted while its tags are read: the rest is skipped."""
    _store(hass_storage, _item("a"), _item("b"))
    asked: list[str] = []
    started = threading.Event()
    go_on = threading.Event()

    def spy(files: list[tuple[str, str, str]], budget: float) -> Any:
        asked.extend(relative for _, _, relative in files)
        started.set()
        go_on.wait(5)
        return len(files), {}

    with patch.object(enrich, "read_batch", spy), patch.object(enrich, "TAG_BATCH", 1):
        manager = QueueManager(hass)
        await manager.async_load()
        await hass.async_add_executor_job(started.wait, 5)
        manager.library.delete("p1")
        go_on.set()
        await hass.async_block_till_done(wait_background_tasks=True)
    assert asked == ["Album/a.mp3"]
    await manager.async_unload()


async def test_tags_without_a_title_keep_the_title(
    hass: HomeAssistant, album: Path, hass_storage: dict[str, Any]
) -> None:
    """Only what the tags say replaces what the item had."""
    _store(hass_storage, _item("a"))
    found = {"id-a": Tags(title=None, artist="X", album=None, duration=5.0)}
    with patch.object(enrich, "read_batch", return_value=(1, found)):
        manager = await _loaded(hass)
    item = manager.library.get("p1").items[0]
    assert (item.title, item.artist, item.duration) == ("a.mp3", "X", 5.0)
    assert manager.library.apply_tags({"unknown": found["id-a"]}) is False
    await manager.async_unload()


async def test_unload_stops_a_repair(
    hass: HomeAssistant, album: Path, hass_storage: dict[str, Any]
) -> None:
    """Unloading cancels a repair round that is still running."""
    _store(hass_storage, _item("a"))
    manager = QueueManager(hass)
    await manager.async_load()
    await manager.async_unload()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert manager.library.get("p1").items[0].artist is None


async def test_a_library_that_never_loaded_unloads(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Unloading without a repair round (nothing loaded yet) just saves."""
    library = PlaylistLibrary(hass, ListeningHistory(hass))
    await library.async_unload()
    assert hass_storage[PLAYLIST_STORAGE_KEY]["data"] == {"playlists": []}
