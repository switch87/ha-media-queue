"""Tests for reading .m3u/.pls playlists of the local media source."""

from pathlib import Path

import pytest

from custom_components.media_queue.playlist import Entry, is_playlist, read_playlist


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Return a media dir like Gert's library."""
    for name in (
        "Vaya Con Dios/Night Owls/08 Night Owls.mp3",
        "Amon Düül II/Yeti/01 Soap Shop Rock.mp3",
        "Amon Düül II/Yeti/02 Archangels Thunderbird.mp3",
        "Afspeellijsten/Other.m3u",
    ):
        _write(tmp_path / "lib" / name, b"")
    _write(tmp_path / "outside.mp3", b"")
    return tmp_path / "lib"


def test_is_playlist() -> None:
    """Playlists are recognised by extension, case-insensitively."""
    assert is_playlist("a/B.M3U")
    assert is_playlist("x.m3u8")
    assert is_playlist("x.pls")
    assert not is_playlist("x.mp3")


def test_m3u_like_gerts(root: Path) -> None:
    """Relative entries, #EXTINF titles, accents, backslashes, BOM."""
    _write(
        root / "Afspeellijsten" / "Fav.m3u",
        (
            "﻿#EXTM3U\n"
            "#EXTINF:239,Vaya Con Dios - Night Owls\n"
            "../Vaya Con Dios/Night Owls/08 Night Owls.mp3\n"
            "\n"
            "# a comment\n"
            "..\\Amon Düül II\\Yeti\\01 Soap Shop Rock.mp3\r\n"
            "#EXTINF:12,\n"
            "../Amon Düül II/Yeti/02 Archangels Thunderbird.mp3\n"
        ).encode(),
    )
    assert read_playlist(root, "Afspeellijsten/Fav.m3u") == [
        Entry(
            "file",
            "Vaya Con Dios/Night Owls/08 Night Owls.mp3",
            "Vaya Con Dios - Night Owls",
        ),
        Entry("file", "Amon Düül II/Yeti/01 Soap Shop Rock.mp3", None),
        Entry("file", "Amon Düül II/Yeti/02 Archangels Thunderbird.mp3", None),
    ]


def test_latin1_absolute_urls_and_escapes(root: Path) -> None:
    """Latin-1 files, absolute paths inside the root, URLs; escapes skipped."""
    _write(
        root / "Afspeellijsten" / "Mixed.m3u8",
        (
            f"{root}/Amon Düül II/Yeti/01 Soap Shop Rock.mp3\n"
            "#EXTINF:-1,Radio 1\n"
            "https://radio.example/stream.mp3\n"
            "http://nas/muziek/x.mp3\n"
            "../../outside.mp3\n"
            f"{root.parent}/outside.mp3\n"
            "../missing.mp3\n"
            "Other.m3u\n"
            "ftp://nope/x.mp3\n"
        ).encode("latin-1"),
    )
    assert read_playlist(root, "Afspeellijsten/Mixed.m3u8") == [
        Entry("file", "Amon Düül II/Yeti/01 Soap Shop Rock.mp3", None),
        Entry("url", "https://radio.example/stream.mp3", "Radio 1"),
        Entry("url", "http://nas/muziek/x.mp3", None),
    ]


def test_pls(root: Path) -> None:
    """PLS: FileN/TitleN in number order."""
    _write(
        root / "Afspeellijsten" / "List.pls",
        b"[playlist]\n"
        b"File2=../Amon D\xc3\xbc\xc3\xbcl II/Yeti/01 Soap Shop Rock.mp3\n"
        b"Title1=Owls\n"
        b"File1=../Vaya Con Dios/Night Owls/08 Night Owls.mp3\n"
        b"Length1=239\n"
        b"NumberOfEntries=2\n"
        b"FileX=broken\n"
        b"Version=2\n",
    )
    assert read_playlist(root, "Afspeellijsten/List.pls") == [
        Entry("file", "Vaya Con Dios/Night Owls/08 Night Owls.mp3", "Owls"),
        Entry("file", "Amon Düül II/Yeti/01 Soap Shop Rock.mp3", None),
    ]


def test_playlist_outside_the_root_is_refused(root: Path) -> None:
    """The playlist itself must be inside the media dir."""
    with pytest.raises(ValueError, match="outside"):
        read_playlist(root, "../outside.mp3")
