"""Fill a dev media folder with tiny tagged MP3 files (for the e2e checks).

Usage: python scripts/make_dev_library.py ~/Workspace/ha-dev/lib

The files are valid MPEG audio (silent frames) of a few seconds with ID3
tags, so the media queue can read titles, artists, albums and durations.
Needs only mutagen (as the integration itself).
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, cast

from mutagen.easyid3 import EasyID3

# One MPEG-1 Layer III frame: 128 kbit/s, 44.1 kHz, no padding (417 bytes).
_HEADER = bytes.fromhex("fffb9064")
FRAME = _HEADER + bytes(417 - len(_HEADER))
FRAMES_PER_SECOND = 44100 / 1152

ALBUMS = {
    ("Amon Düül II", "Yeti"): [
        "Soap Shop Rock",
        "Archangels Thunderbird",
        "Cerberus",
        "The Return of Ruebezahl",
        "Eye-Shaking King",
        "Pharao",
        "Sandoz in the Rain",
    ],
    ("Vaya Con Dios", "Night Owls"): [
        "Nah Neh Nah",
        "Just a Friend of Mine",
        "What's a Woman",
        "Night Owls",
    ],
}
# File names as on the NAS: "NN Title.mp3"; Night Owls is track 8 on purpose
# (the playlist Afspeellijsten/Test.m3u points at "08 Night Owls.mp3").
NUMBERS = {"Night Owls": 8}


def write(path: Path, seconds: float, **tags: str) -> None:
    """Write a silent MP3 of seconds with the given tags."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(FRAME * round(seconds * FRAMES_PER_SECOND))
    id3 = cast(Any, EasyID3)()  # mutagen has no type hints
    for key, value in tags.items():
        id3[key] = value
    id3.save(path)


def main(root: Path) -> None:
    """Write the albums below root."""
    for (artist, album), titles in ALBUMS.items():
        for number, title in enumerate(titles, start=1):
            track = NUMBERS.get(title, number)
            path = root / artist / album / f"{track:02d} {title}.mp3"
            write(
                path,
                30 + number,
                title=title,
                artist=artist,
                album=album,
                tracknumber=str(track),
            )
            print(path)


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
