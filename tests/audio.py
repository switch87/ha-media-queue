"""Tiny valid MP3 files with ID3 tags, for tests (no encoder needed)."""

from pathlib import Path

from mutagen.easyid3 import EasyID3

# One MPEG-1 Layer III frame: 128 kbit/s, 44.1 kHz, no padding (417 bytes).
_HEADER = bytes.fromhex("fffb9064")
FRAME = _HEADER + bytes(417 - len(_HEADER))
FRAMES_PER_SECOND = 44100 / 1152


def write_mp3(path: Path, seconds: float = 2.0, **tags: str) -> Path:
    """Write an MP3 of about seconds long with the given EasyID3 tags."""
    path.write_bytes(FRAME * round(seconds * FRAMES_PER_SECOND))
    if tags:
        id3 = EasyID3()  # type: ignore[no-untyped-call]
        for key, value in tags.items():
            id3[key] = value
        id3.save(path)
    return path
