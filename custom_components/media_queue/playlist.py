"""Read .m3u/.m3u8/.pls playlists of the local media source (blocking: executor)."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
from typing import Literal

PLAYLIST_SUFFIXES = (".m3u", ".m3u8", ".pls")
URL_SCHEMES = ("http://", "https://")


@dataclass(frozen=True, slots=True)
class Entry:
    """One playlist entry: a file (path relative to the media dir) or a URL."""

    kind: Literal["file", "url"]
    target: str
    title: str | None


def is_playlist(name: str) -> bool:
    """Return whether a file name is a playlist."""
    return name.lower().endswith(PLAYLIST_SUFFIXES)


def read_playlist(root: Path, relative: str) -> list[Entry]:
    """Return the usable entries of the playlist at root/relative.

    Paths are relative to the playlist's folder (or absolute inside root);
    entries outside root, missing files and nested playlists are skipped.
    """
    real_root = os.path.realpath(root)
    playlist = os.path.realpath(root / relative)
    if not _inside(playlist, real_root):
        raise ValueError(f"Playlist outside the media folder: {relative}")
    raw = Path(playlist).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    pairs = _pls(text) if playlist.lower().endswith(".pls") else _m3u(text)
    folder = os.path.dirname(playlist)
    entries: list[Entry] = []
    for target, title in pairs:
        if target.lower().startswith(URL_SCHEMES):
            entries.append(Entry("url", target, title))
            continue
        path = os.path.realpath(os.path.join(folder, target.replace("\\", "/")))
        if _inside(path, real_root) and os.path.isfile(path) and not is_playlist(path):
            relative_path = PurePosixPath(Path(path).relative_to(real_root))
            entries.append(Entry("file", str(relative_path), title))
    return entries


def _inside(path: str, root: str) -> bool:
    return os.path.commonpath([path, root]) == root and path != root


def _m3u(text: str) -> list[tuple[str, str | None]]:
    pairs: list[tuple[str, str | None]] = []
    title: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.upper().startswith("#EXTINF:"):
            title = line.partition(",")[2].strip() or None
        elif line and not line.startswith("#"):
            pairs.append((line, title))
            title = None
    return pairs


def _pls(text: str) -> list[tuple[str, str | None]]:
    files: dict[int, str] = {}
    titles: dict[int, str] = {}
    for raw_line in text.splitlines():
        if match := re.fullmatch(r"(file|title)(\d+)=(.*)", raw_line.strip(), re.I):
            kind, number, value = match.groups()
            target = files if kind.lower() == "file" else titles
            target[int(number)] = value.strip()
    return [(files[n], titles.get(n) or None) for n in sorted(files)]
