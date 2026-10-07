"""Titles from audio file tags of the local media source (blocking: executor).

Embedded cover pictures are never read, so a file costs a few kB also over a
slow network mount:

- FLAC: the metadata block headers are walked here; only STREAMINFO (the
  duration) and VORBIS_COMMENT are read, PICTURE/PADDING/… are seeked past.
- MP3 with an ID3v2 tag larger than TAG_CAP (a big cover): the frames are
  walked here; only TIT2/TPE1/TALB are read, the duration comes from the
  first MPEG frame after the tag (mutagen).
- Everything else (small ID3 tags, MP4, Ogg, …) goes to mutagen through a
  reader that stops after READ_BUDGET bytes: a file whose tags are bigger
  (an M4A or Ogg file with a large cover) keeps its file name as title.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import os
import time
from typing import IO, Any

import mutagen
from mutagen.mp3 import MPEGInfo

from .expand import LOCAL_MEDIA, clean_title

# Bigger files are skipped (no music file is this large; avoids odd formats).
MAX_FILE_SIZE = 1 << 30
# Most bytes read from one file; an ID3 tag above TAG_CAP is walked frame by frame.
READ_BUDGET = 256 * 1024
TAG_CAP = 128 * 1024
# Read buffer: small, every byte may cross the network.
BUFFER = 8192
# Comments looked at in one FLAC file at most.
MAX_PARTS = 256

_FLAC_STREAMINFO = 0
_FLAC_VORBIS_COMMENT = 4
_ID3_TEXT = {b"TIT2": "title", b"TPE1": "artist", b"TALB": "album"}
_ID3_ENCODINGS = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}
_ID3_UNSYNCHRONISED = 0x80


@dataclass(frozen=True, slots=True)
class Tags:
    """What the tags of one file say."""

    title: str | None
    artist: str | None
    album: str | None
    duration: float | None


def local_file(media_dirs: dict[str, str], content_id: str) -> tuple[str, str] | None:
    """Return (media folder, relative path) of a local media item, else None."""
    if not content_id.startswith(LOCAL_MEDIA):
        return None
    media_dir, _, relative = content_id.removeprefix(LOCAL_MEDIA).partition("/")
    root = media_dirs.get(media_dir)
    if root is None or not relative:
        return None
    return root, relative


class _OverBudget(Exception):
    """The file needs more reading than READ_BUDGET."""


class _Budgeted:
    """A file object that refuses to read more than budget bytes in total."""

    def __init__(self, raw: IO[bytes], name: str, budget: int) -> None:
        self._raw = raw
        self.name = name
        self._left = budget

    def read(self, size: int | None = -1) -> bytes:
        wanted = self._left + 1 if size is None or size < 0 else size
        data = self._raw.read(wanted)
        self._left -= len(data)
        if self._left < 0:
            raise _OverBudget
        return data

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self._raw.seek(offset, whence)

    def tell(self) -> int:
        return self._raw.tell()


def _open(path: str) -> IO[bytes]:
    """Open path for reading (patched in tests to count the bytes read)."""
    return open(path, "rb", buffering=BUFFER)


def _clean(text: str | None) -> str | None:
    return clean_title(text) or None if text else None


def _first(tags: Any, key: str) -> str | None:
    values = tags.get(key) if tags is not None else None
    return _clean(str(values[0])) if values else None


def _seconds(length: Any) -> float | None:
    if isinstance(length, int | float) and math.isfinite(length) and length > 0:
        return float(length)
    return None


def read_tags(path: str) -> Tags | None:
    """Return the tags of the audio file at path, None when there are none."""
    try:
        return _read(path)
    except Exception:  # broken files raise all kinds of errors
        return None


def _read(path: str) -> Tags | None:
    if os.path.getsize(path) > MAX_FILE_SIZE:
        return None
    with _open(path) as raw:
        file = _Budgeted(raw, path, READ_BUDGET)
        head = file.read(10)
        file.seek(0)
        if head[:4] == b"fLaC":
            return _flac(file)
        if head[:3] == b"ID3" and len(head) == 10 and _synchsafe(head[6:]) > TAG_CAP:
            return _big_id3(file, head)
        return _mutagen(file)


def _mutagen(file: _Budgeted) -> Tags | None:
    audio = mutagen.File(file, easy=True)
    if audio is None:
        return None
    return Tags(
        title=_first(audio.tags, "title"),
        artist=_first(audio.tags, "artist"),
        album=_first(audio.tags, "album"),
        duration=_seconds(getattr(audio.info, "length", None)),
    )


def _flac(file: _Budgeted) -> Tags:
    """Read STREAMINFO and VORBIS_COMMENT, seek past every other block."""
    file.seek(4)
    duration: float | None = None
    found: dict[str, str] = {}
    while True:  # every block costs read budget: this ends
        header = file.read(4)
        if len(header) < 4:
            break
        kind = header[0] & 0x7F
        length = int.from_bytes(header[1:], "big")
        if kind == _FLAC_STREAMINFO and length >= 18:
            duration = _streaminfo(file.read(length))
        elif kind == _FLAC_VORBIS_COMMENT and length <= TAG_CAP:
            found = _vorbis_comments(file.read(length))
        else:
            file.seek(length, os.SEEK_CUR)
        if header[0] & 0x80:
            break
    return Tags(
        title=_clean(found.get("title")),
        artist=_clean(found.get("artist")),
        album=_clean(found.get("album")),
        duration=duration,
    )


def _streaminfo(data: bytes) -> float | None:
    packed = int.from_bytes(data[10:18], "big")
    rate = packed >> 44
    samples = packed & 0xFFFFFFFFF
    return samples / rate if rate and samples else None


def _vorbis_comments(data: bytes) -> dict[str, str]:
    """Return the first title/artist/album of a VORBIS_COMMENT block."""
    position = 4 + int.from_bytes(data[:4], "little")
    if position + 4 > len(data):
        raise ValueError("comment block too short")
    count = int.from_bytes(data[position : position + 4], "little")
    position += 4
    found: dict[str, str] = {}
    for _ in range(min(count, MAX_PARTS)):
        size = int.from_bytes(data[position : position + 4], "little")
        entry = data[position + 4 : position + 4 + size]
        if len(entry) < size:
            raise ValueError("comment block too short")
        position += 4 + size
        key, _, value = entry.decode("utf-8", "replace").partition("=")
        found.setdefault(key.lower(), value)
    return found


def _synchsafe(data: bytes) -> int:
    return (data[0] << 21) | (data[1] << 14) | (data[2] << 7) | data[3]


def _big_id3(file: _Budgeted, head: bytes) -> Tags:
    """Read the text frames of a large ID3v2.3/2.4 tag, seek past the rest."""
    version, flags = head[3], head[5]
    end = 10 + _synchsafe(head[6:])
    found: dict[str, str] = {}
    if version in (3, 4) and not flags & _ID3_UNSYNCHRONISED:
        found = _id3_frames(file, version, end)
    try:
        duration = _seconds(MPEGInfo(file, end).length)
    except Exception:  # no MPEG audio after the tag
        duration = None
    return Tags(
        title=found.get("title"),
        artist=found.get("artist"),
        album=found.get("album"),
        duration=duration,
    )


def _id3_frames(file: _Budgeted, version: int, end: int) -> dict[str, str]:
    found: dict[str, str] = {}
    position = 10
    while position + 10 <= end:
        file.seek(position)
        header = file.read(10)
        frame_id = header[:4]
        if len(header) < 10 or not frame_id.isalnum():
            break  # padding or a cut tag
        raw_size = header[4:8]
        size = _synchsafe(raw_size) if version == 4 else int.from_bytes(raw_size)
        position += 10 + size
        key = _ID3_TEXT.get(frame_id)
        if key is None or key in found or header[9] or size > TAG_CAP:
            continue  # pictures, other frames, compressed/encrypted frames
        if (text := _id3_text(file.read(size))) is not None:
            found[key] = text
    return found


def _id3_text(data: bytes) -> str | None:
    codec = _ID3_ENCODINGS.get(data[0]) if data else None
    if codec is None:
        return None
    return _clean(data[1:].decode(codec, "replace").split("\x00")[0])


def _inside(root: str, relative: str) -> str | None:
    """Return the real path of root/relative if it stays inside root."""
    real_root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(real_root, relative))
    if os.path.commonpath([path, real_root]) != real_root:
        return None
    return path


def read_batch(
    files: list[tuple[str, str, str]],
    budget: float,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int, dict[str, Tags]]:
    """Read (item id, media folder, relative path) files until budget seconds.

    Return how many files were handled (at least one) and the tags found by
    item id.
    """
    found: dict[str, Tags] = {}
    started = clock()
    count = 0
    for item_id, root, relative in files:
        count += 1
        path = _inside(root, relative)
        if path is not None and (tags := read_tags(path)) is not None:
            found[item_id] = tags
        if clock() - started >= budget:
            break
    return count, found
