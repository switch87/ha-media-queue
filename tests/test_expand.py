"""Tests for expanding browse items into queue items."""

from pathlib import Path

from homeassistant.components.media_player.const import (
    MediaClass,
    MediaPlayerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
import pytest

from custom_components.media_queue import expand
from custom_components.media_queue.expand import AddRequest, async_expand
from custom_components.media_queue.model import QueueItem

from .fakes import FakePlayer, async_add_players, folder, node

PLAYER = "media_player.fake"
LOCAL = "media-source://media_source"


def _titles(items: list[QueueItem]) -> list[str]:
    return [item.title for item in items]


@pytest.fixture
async def library(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Set up the media source with a small local library."""
    album = tmp_path / "Amon Düül II" / "Yeti"
    (album / "CD 2").mkdir(parents=True)
    for path in (
        album / "02 Archangels Thunderbird.mp3",
        album / "01 Soap Shop Rock.mp3",
        album / "cover.jpg",
        album / "Yeti.m3u",
        album / "CD 2" / "01 Sandoz in the Rain.flac",
        tmp_path / "Empty" / ".keep",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    hass.config.media_dirs = {"local": str(tmp_path)}
    assert await async_setup_component(hass, "media_source", {})
    return tmp_path


async def test_leaf_is_queued_as_given(hass: HomeAssistant) -> None:
    """A known leaf is not browsed and keeps the caller's details."""
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(
            media_content_id="http://radio/stream",
            media_content_type="music",
            title="Radio",
            media_class="channel",
            thumbnail="https://radio.example/logo.png",
            can_expand=False,
        ),
        limit=10,
    )
    assert result.truncated is False
    [item] = result.items
    assert item.media_content_id == "http://radio/stream"
    assert item.media_content_type == "music"
    assert item.title == "Radio"
    assert item.media_class == "channel"
    assert item.thumbnail == "https://radio.example/logo.png"


async def test_media_source_folder_is_expanded(
    hass: HomeAssistant, library: Path
) -> None:
    """A folder becomes its tracks, depth-first in the source's order."""
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(
            media_content_id=f"{LOCAL}/local/Amon Düül II",
            media_content_type="",
            can_expand=True,
        ),
        limit=10,
    )
    assert _titles(result.items) == [
        "01 Sandoz in the Rain.flac",
        "01 Soap Shop Rock.mp3",
        "02 Archangels Thunderbird.mp3",
    ]
    first = result.items[0]
    assert first.media_content_id == (
        f"{LOCAL}/local/Amon Düül II/Yeti/CD 2/01 Sandoz in the Rain.flac"
    )
    assert first.media_class == MediaClass.MUSIC
    assert first.media_content_type.startswith("audio/")
    assert result.truncated is False


async def test_media_source_file_without_hint_is_a_leaf(
    hass: HomeAssistant, library: Path
) -> None:
    """A file id (from an automation) is queued; the title comes from the id."""
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(
            media_content_id=f"{LOCAL}/local/Amon Düül II/Yeti/01 Soap Shop Rock.mp3",
            media_content_type="audio/mpeg",
        ),
        limit=10,
    )
    assert _titles(result.items) == ["01 Soap Shop Rock.mp3"]


async def test_empty_folder_gives_nothing(hass: HomeAssistant, library: Path) -> None:
    """A folder without media expands to no items."""
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id=f"{LOCAL}/local/Empty", media_content_type=""),
        limit=10,
    )
    assert result.items == []


async def test_player_tree_is_expanded(hass: HomeAssistant) -> None:
    """Ids of the player itself are browsed through the player entity."""
    player = FakePlayer(
        "Fake",
        {
            "artist": folder(
                "artist",
                "Artist",
                [
                    folder("album-1", "Album 1", can_play=True),
                    node("loose", "Loose track"),
                    node("not-playable", "Info", can_play=False),
                    folder("playlist", "Playlist", can_play=True),
                    folder("broken", "Broken"),
                    folder("unlisted", "Unlisted"),
                    node("picture", "Picture", media_class=MediaClass.IMAGE),
                ],
            ),
            "album-1": folder(
                "album-1",
                "Album 1",
                [
                    node("t1", "Track 1", thumbnail="/media/local/t1.jpg"),
                    node("t2", "Track 2"),
                ],
                can_play=True,
            ),
            "playlist": folder("playlist", "Playlist", [], can_play=True),
            "unlisted": folder("unlisted", "Unlisted", None),
        },
    )
    await async_add_players(hass, player)

    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="artist", media_content_type="artist"),
        limit=10,
    )

    assert _titles(result.items) == ["Track 1", "Track 2", "Loose track", "Playlist"]
    assert result.items[0].thumbnail == "/media/local/t1.jpg"
    assert result.items[0].media_content_type == "track"
    assert result.items[3].media_content_type == "album"
    assert player.browsed == ["artist", "album-1", "playlist", "broken", "unlisted"]


async def test_top_level_leaf_from_browse(hass: HomeAssistant) -> None:
    """A browsed id that turns out to be a leaf is queued with its own title."""
    player = FakePlayer(
        "Fake",
        {"t1": node("t1", "Track 1"), "info": node("info", "Info", can_play=False)},
    )
    await async_add_players(hass, player)

    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="t1", media_content_type="track"),
        limit=10,
    )
    assert _titles(result.items) == ["Track 1"]

    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="info", media_content_type="track"),
        limit=10,
    )
    assert result.items == []


async def test_cap_truncates(hass: HomeAssistant) -> None:
    """Expansion stops at the limit and says whether something was left out."""
    tracks = [node(f"t{i}", f"Track {i}") for i in range(3)]
    player = FakePlayer(
        "Fake",
        {
            "three": folder("three", "Three", tracks),
            "two": folder("two", "Two", tracks[:2]),
        },
    )
    await async_add_players(hass, player)

    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="three", media_content_type="album"),
        limit=2,
    )
    assert _titles(result.items) == ["Track 0", "Track 1"]
    assert result.truncated is True

    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="two", media_content_type="album"),
        limit=2,
    )
    assert result.truncated is False


async def test_zero_limit_browses_nothing(hass: HomeAssistant) -> None:
    """A full queue does not browse at all."""
    player = FakePlayer("Fake", {"two": folder("two", "Two", [node("t", "T")])})
    await async_add_players(hass, player)
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="two", media_content_type="album"),
        limit=0,
    )
    assert result.items == []
    assert result.truncated is True
    assert player.browsed == []


async def test_depth_limit(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Folders deeper than the limit are not opened; playable ones are queued."""
    monkeypatch.setattr(expand, "MAX_DEPTH", 2)
    player = FakePlayer(
        "Fake",
        {
            "d0": folder("d0", "D0", [folder("d1", "D1")]),
            "d1": folder(
                "d1",
                "D1",
                [folder("d2", "D2"), folder("d2-playable", "D2 album", can_play=True)],
            ),
            "d2": folder("d2", "D2", [node("deep", "Deep")]),
        },
    )
    await async_add_players(hass, player)

    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="d0", media_content_type="album"),
        limit=10,
    )
    assert _titles(result.items) == ["D2 album"]
    assert player.browsed == ["d0", "d1"]


async def test_cycles_are_not_followed(hass: HomeAssistant) -> None:
    """A tree that links back to an opened folder does not loop."""
    player = FakePlayer(
        "Fake",
        {
            "a": folder("a", "A", [node("t", "T"), folder("b", "B")]),
            "b": folder("b", "B", [folder("a", "A")]),
        },
    )
    await async_add_players(hass, player)
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="a", media_content_type="album"),
        limit=10,
    )
    assert _titles(result.items) == ["T"]
    assert player.browsed == ["a", "b"]


async def test_browse_budget(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Huge trees of folders stop after a fixed number of browse calls."""
    monkeypatch.setattr(expand, "MAX_BROWSE_CALLS", 2)
    player = FakePlayer(
        "Fake",
        {
            "root": folder("root", "Root", [folder(f"f{i}", "F") for i in range(3)]),
            "f0": folder("f0", "F0", [node("t", "T")]),
            "f1": folder("f1", "F1", [node("u", "U")]),
        },
    )
    await async_add_players(hass, player)
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="root", media_content_type="album"),
        limit=10,
    )
    assert _titles(result.items) == ["T"]
    assert result.truncated is True


async def test_unknown_player_with_folder(hass: HomeAssistant) -> None:
    """A folder of a player that does not exist cannot be opened."""
    await async_add_players(hass)
    with pytest.raises(ServiceValidationError) as err:
        await async_expand(
            hass,
            "media_player.gone",
            AddRequest(
                media_content_id="album", media_content_type="album", can_expand=True
            ),
            limit=10,
        )
    assert err.value.translation_key == "cannot_browse"
    assert err.value.translation_placeholders == {"item": "album"}


async def test_unknown_item_without_hint_is_a_leaf(hass: HomeAssistant) -> None:
    """Without the media_player component, a plain id is queued as it is."""
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="http://radio/x", media_content_type="music"),
        limit=10,
    )
    assert _titles(result.items) == ["x"]


async def test_player_without_browse(hass: HomeAssistant) -> None:
    """A player that cannot browse: folders fail, plain ids are leaves."""
    player = FakePlayer("Fake", features=MediaPlayerEntityFeature.PLAY_MEDIA)
    await async_add_players(hass, player)

    with pytest.raises(ServiceValidationError):
        await async_expand(
            hass,
            PLAYER,
            AddRequest(
                media_content_id="album",
                media_content_type="album",
                title="Album",
                can_expand=True,
            ),
            limit=10,
        )
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="http://x/y.mp3", media_content_type="music"),
        limit=10,
    )
    assert _titles(result.items) == ["y.mp3"]
    assert player.browsed == []


async def test_browse_not_implemented(hass: HomeAssistant) -> None:
    """A player that claims browse but does not implement it is a leaf source."""
    await async_add_players(hass, FakePlayer("Fake"))
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="not-implemented", media_content_type="music"),
        limit=10,
    )
    assert _titles(result.items) == ["not-implemented"]


async def test_single_image_can_be_queued(hass: HomeAssistant) -> None:
    """Images are only skipped inside folders, not when added on purpose."""
    await async_add_players(
        hass,
        FakePlayer("Fake", {"pic": node("pic", "Pic", media_class=MediaClass.IMAGE)}),
    )
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="pic", media_content_type="image"),
        limit=10,
    )
    assert _titles(result.items) == ["Pic"]


@pytest.mark.parametrize(
    ("thumbnail", "kept"),
    [
        ("https://img.example/a.jpg", True),
        ("http://nas/cover.jpg", True),
        ("/api/media_player_proxy/media_player.a?token=x", True),
        ("/api/image_proxy/image.a", True),
        ("/api/brands/integration/sonos/logo.png", True),
        ("/media/local/cover.jpg", True),
        ("javascript:alert(1)", False),
        ("data:image/png;base64,AAAA", False),
        ("/api/states", False),
        ("https://img.example/" + "x" * 3000, False),
    ],
)
async def test_thumbnails_are_checked(
    hass: HomeAssistant, thumbnail: str, kept: bool
) -> None:
    """Only image URLs of the web or of Home Assistant's media paths are kept."""
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(
            media_content_id="x",
            media_content_type="music",
            thumbnail=thumbnail,
            can_expand=False,
        ),
        limit=10,
    )
    assert result.items[0].thumbnail == (thumbnail if kept else None)


async def test_titles_are_trimmed_and_capped(hass: HomeAssistant) -> None:
    """Long titles (from callers or sources) are cut at 300 characters."""
    player = FakePlayer(
        "Fake",
        {"a": folder("a", "A", [node("t", "  " + "y" * 400, thumbnail="evil:x")])},
    )
    await async_add_players(hass, player)
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(media_content_id="a", media_content_type="album"),
        limit=10,
    )
    assert result.items[0].title == "y" * 300
    assert result.items[0].thumbnail is None
    result = await async_expand(
        hass,
        PLAYER,
        AddRequest(
            media_content_id="x",
            media_content_type="music",
            title="z" * 400,
            can_expand=False,
        ),
        limit=10,
    )
    assert result.items[0].title == "z" * 300
