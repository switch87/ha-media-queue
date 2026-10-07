"""Titles from audio file tags of the local media source (blocking: executor).

Only the tag header and the first audio frame are read (mutagen), so a file
costs a few small reads, also over a slow network mount.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import os
import time
from typing import Any

import mutagen

from .expand import LOCAL_MEDIA, clean_title

# Bigger files are skipped (no music file is this large; avoids odd formats).
MAX_FILE_SIZE = 1 << 30


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


def _first(tags: Any, key: str) -> str | None:
    values = tags.get(key) if tags is not None else None
    text = clean_title(str(values[0])) if values else ""
    return text or None


def read_tags(path: str) -> Tags | None:
    """Return the tags of the audio file at path, None when there are none."""
    try:
        if os.path.getsize(path) > MAX_FILE_SIZE:
            return None
        audio = mutagen.File(path, easy=True)
    except Exception:  # broken files raise all kinds of errors
        return None
    if audio is None:
        return None
    length = getattr(audio.info, "length", None)
    duration = (
        float(length)
        if isinstance(length, int | float) and math.isfinite(length) and length > 0
        else None
    )
    return Tags(
        title=_first(audio.tags, "title"),
        artist=_first(audio.tags, "artist"),
        album=_first(audio.tags, "album"),
        duration=duration,
    )


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
