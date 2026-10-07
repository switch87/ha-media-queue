"""Tests for titles from audio tags: the reader and the background enrichment."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest

from custom_components.media_queue import controller as controller_module, tags
from custom_components.media_queue.controller import Phase
from custom_components.media_queue.expand import AddRequest
from custom_components.media_queue.model import Mode, QueueItem
from custom_components.media_queue.tags import Tags, local_file, read_batch, read_tags

from .audio import write_mp3
from .common import (
    LOCAL,
    PLAYER,
    PlayerLog,
    async_manager_with,
    async_setup_library,
    state,
)

# ------------------------------------------------------------------ the reader


def test_read_tags(tmp_path: Path) -> None:
    """Title, artist, album and duration come from the tags."""
    path = write_mp3(
        tmp_path / "01 x.mp3", 3, title=" Soap Shop Rock ", artist="Amon Düül II"
    )
    found = read_tags(str(path))
    assert found is not None
    assert found.title == "Soap Shop Rock"
    assert found.artist == "Amon Düül II"
    assert found.album is None
    assert found.duration == pytest.approx(3, abs=0.1)


def test_read_tags_caps_long_titles(tmp_path: Path) -> None:
    """Tag values are capped like browse titles."""
    found = read_tags(str(write_mp3(tmp_path / "a.mp3", title="x" * 500)))
    assert found is not None
    assert found.title == "x" * 300


@pytest.mark.parametrize("tagged", [{}, {"title": "", "artist": " "}])
def test_without_tags_only_a_duration(tmp_path: Path, tagged: dict[str, str]) -> None:
    """A file without (usable) tags still has a length."""
    found = read_tags(str(write_mp3(tmp_path / "a.mp3", 2, **tagged)))
    assert found is not None
    assert found.duration == pytest.approx(2, abs=0.1)
    assert found == Tags(title=None, artist=None, album=None, duration=found.duration)


@pytest.mark.parametrize(
    ("name", "content"), [("a.mp3", b""), ("a.txt", b"just text, no audio")]
)
def test_not_audio(tmp_path: Path, name: str, content: bytes) -> None:
    """Broken audio and files mutagen does not know give nothing."""
    path = tmp_path / name
    path.write_bytes(content)
    assert read_tags(str(path)) is None


def test_missing_too_large_and_broken_files(tmp_path: Path) -> None:
    """Missing, huge and broken files are skipped, never raised."""
    path = write_mp3(tmp_path / "a.mp3", title="T")
    assert read_tags(str(tmp_path / "gone.mp3")) is None
    with patch.object(tags, "MAX_FILE_SIZE", 10):
        assert read_tags(str(path)) is None
    with patch(
        "custom_components.media_queue.tags.mutagen.File",
        side_effect=IndexError("broken"),
    ):
        assert read_tags(str(path)) is None


def test_zero_length_is_unknown(tmp_path: Path) -> None:
    """A length of 0 (or none at all) is no duration."""
    path = write_mp3(tmp_path / "a.mp3", title="T")
    fake = SimpleNamespace(info=SimpleNamespace(length=0), tags={"title": ["T"]})
    with patch("custom_components.media_queue.tags.mutagen.File", return_value=fake):
        found = read_tags(str(path))
    assert found == Tags(title="T", artist=None, album=None, duration=None)


def test_broken_tags_after_opening(tmp_path: Path) -> None:
    """Errors while reading the parsed tags are a file without tags too."""
    path = write_mp3(tmp_path / "a.mp3", title="T")

    class Broken(dict[str, list[str]]):
        def get(self, key: str, default: Any = None) -> Any:
            raise ValueError(key)

    fake = SimpleNamespace(info=SimpleNamespace(length=3), tags=Broken())
    with patch("custom_components.media_queue.tags.mutagen.File", return_value=fake):
        assert read_tags(str(path)) is None


def test_local_file() -> None:
    """Only items of a configured local media folder are read."""
    dirs = {"local": "/media"}
    assert local_file(dirs, f"{LOCAL}/A/b.mp3") == ("/media", "A/b.mp3")
    assert local_file(dirs, f"{LOCAL}/") is None
    assert local_file(dirs, "media-source://media_source/other/b.mp3") is None
    assert local_file(dirs, "media-source://radio_browser/x") is None
    assert local_file(dirs, "http://x/b.mp3") is None


def test_read_batch(tmp_path: Path) -> None:
    """Paths outside the folder are refused; unreadable files are left out."""
    (tmp_path / "lib").mkdir()
    write_mp3(tmp_path / "lib" / "a.mp3", title="A")
    write_mp3(tmp_path / "outside.mp3", title="Secret")
    (tmp_path / "lib" / "c.mp3").write_bytes(b"")
    root = str(tmp_path / "lib")
    count, found = read_batch(
        [
            ("1", root, "a.mp3"),
            ("2", root, "../outside.mp3"),
            ("3", root, "c.mp3"),
            ("4", root, "gone.mp3"),
        ],
        budget=10,
    )
    assert count == 4
    assert list(found) == ["1"]
    assert found["1"].title == "A"


def test_read_batch_stops_at_its_budget(tmp_path: Path) -> None:
    """A slow folder gives smaller batches; at least one file is read."""
    write_mp3(tmp_path / "a.mp3", title="A")
    ticks: Iterator[float] = iter([0.0, 5.0])
    count, found = read_batch(
        [("1", str(tmp_path), "a.mp3"), ("2", str(tmp_path), "a.mp3")],
        budget=2,
        clock=lambda: next(ticks),
    )
    assert count == 1
    assert list(found) == ["1"]


# ------------------------------------------------------- enrichment in the queue


@pytest.fixture
async def library(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Return a local library with a tagged album (media source set up)."""
    album = tmp_path / "Yeti"
    album.mkdir()
    for number, title in enumerate(["Soap Shop Rock", "Archangels", "Eye-Shaking"]):
        write_mp3(
            album / f"0{number + 1} {title}.mp3",
            3,
            title=title,
            artist="Amon Düül II",
            album="Yeti",
        )
    (album / "04 untagged.mp3").write_bytes(b"")
    hass.config.media_dirs = {"local": str(tmp_path)}
    hass.config.internal_url = "http://example.local:8123"
    assert await async_setup_component(hass, "media_source", {})
    return tmp_path


ALBUM = AddRequest(
    media_content_id=f"{LOCAL}/Yeti", media_content_type="", can_expand=True
)


def _rows(snapshot: dict[str, Any]) -> list[tuple[str, str | None]]:
    return [(item["title"], item["artist"]) for item in snapshot["items"]]


async def test_titles_come_from_the_tags_after_the_add(
    hass: HomeAssistant, library: Path
) -> None:
    """The add shows file names at once; the tags follow in one update."""
    manager = await async_manager_with(hass)
    seen: list[dict[str, Any]] = []
    manager.subscribe(PLAYER, seen.append)
    controller = manager.controller(PLAYER)

    await controller.async_add(ALBUM, Mode.ADD)
    assert _rows(controller.snapshot())[0] == ("01 Soap Shop Rock.mp3", None)

    await hass.async_block_till_done(wait_background_tasks=True)
    assert _rows(controller.snapshot()) == [
        ("Soap Shop Rock", "Amon Düül II"),
        ("Archangels", "Amon Düül II"),
        ("Eye-Shaking", "Amon Düül II"),
        ("04 untagged.mp3", None),
    ]
    first = controller.queue.items[0]
    assert first.album == "Yeti"
    assert first.duration == pytest.approx(3, abs=0.1)
    assert len(seen) == 2  # the add, then one batch of tags
    await manager.async_unload()


async def test_enrichment_in_batches_and_capped(
    hass: HomeAssistant, library: Path
) -> None:
    """Small batches each send an update; only the first items are read."""
    manager = await async_manager_with(hass)
    seen: list[dict[str, Any]] = []
    manager.subscribe(PLAYER, seen.append)
    controller = manager.controller(PLAYER)
    with (
        patch.object(controller_module, "TAG_BATCH", 1),
        patch.object(controller_module, "TAG_LIMIT", 2),
    ):
        await controller.async_add(ALBUM, Mode.ADD)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert [title for title, _ in _rows(controller.snapshot())] == [
        "Soap Shop Rock",
        "Archangels",
        "03 Eye-Shaking.mp3",
        "04 untagged.mp3",
    ]
    assert len(seen) == 3
    await manager.async_unload()


async def test_items_removed_meanwhile_and_other_sources(
    hass: HomeAssistant, library: Path
) -> None:
    """Removed items are not brought back; non-local items are not read."""
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    await controller.async_add(ALBUM, Mode.ADD)
    controller.clear()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert controller.queue.items == []

    radio = AddRequest(
        media_content_id="http://radio/stream",
        media_content_type="music",
        title="Radio",
        can_expand=False,
    )
    with patch.object(controller_module, "read_batch") as reader:
        await controller.async_add(radio, Mode.ADD)
        await hass.async_block_till_done(wait_background_tasks=True)
    reader.assert_not_called()
    await manager.async_unload()


async def test_a_hanging_folder_ends_the_enrichment(
    hass: HomeAssistant, library: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A batch that takes too long (a hung mount) leaves the file names."""
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    with patch.object(controller_module, "TAG_TIMEOUT", 0):
        await controller.async_add(ALBUM, Mode.ADD)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert controller.queue.items[0].title == "01 Soap Shop Rock.mp3"
    assert "reading tags" in caplog.text
    await manager.async_unload()


async def test_tag_duration_ends_an_item_the_player_does_not_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tmp_path: Path
) -> None:
    """Players without a duration still advance when the tags know it."""
    await async_setup_library(hass, tmp_path)
    log = PlayerLog(hass)
    state(hass, "idle")
    log.on_play = lambda call: state(
        hass,
        "playing",
        call.data["media_content_id"],
        media_position=0,
        media_position_updated_at=dt_util.utcnow(),
    )
    manager = await async_manager_with(hass)
    controller = manager.controller(PLAYER)
    timed = [
        QueueItem(
            media_content_id=f"{LOCAL}/Yeti/{name}.mp3",
            media_content_type="audio/mpeg",
            title=name,
            duration=100.0,
        )
        for name in ("a", "b")
    ]
    controller.queue.add(timed, Mode.ADD, limit=10)
    await controller.async_play(0)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert controller.phase is Phase.PLAYING

    freezer.tick(timedelta(seconds=100))
    current = hass.states.get(PLAYER)
    assert current is not None
    hass.states.async_set(PLAYER, "idle", current.attributes)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert log.played == ["a.mp3", "b.mp3"]
    await manager.async_unload()
