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


def synchsafe(value: int) -> bytes:
    """Return value as a 4-byte ID3v2 synchsafe integer."""
    return bytes((value >> shift) & 0x7F for shift in (21, 14, 7, 0))


def id3_frame(frame_id: str, data: bytes, version: int = 4, flags: int = 0) -> bytes:
    """Return one ID3v2.3/2.4 frame."""
    size = synchsafe(len(data)) if version == 4 else len(data).to_bytes(4, "big")
    return frame_id.encode() + size + bytes([0, flags]) + data


def text_frame(frame_id: str, text: str, encoding: int = 3, version: int = 4) -> bytes:
    """Return a text frame (encoding 0 latin-1, 1 UTF-16, 2 UTF-16BE, 3 UTF-8)."""
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(encoding)
    body = text.encode(codec) if codec else text.encode()
    return id3_frame(frame_id, bytes([encoding]) + body, version)


def id3_tag(frames: bytes, version: int = 4, flags: int = 0, padding: int = 0) -> bytes:
    """Return an ID3v2 tag holding frames and padding."""
    body = frames + bytes(padding)
    return b"ID3" + bytes([version, 0, flags]) + synchsafe(len(body)) + body


def write_mp3_with_cover(
    path: Path, seconds: float, cover: int, version: int = 4, **tags: str
) -> Path:
    """Write an MP3 whose ID3 tag carries a cover picture of cover bytes."""
    frames = b"".join(
        text_frame(frame_id, tags[key], version=version)
        for key, frame_id in (("title", "TIT2"), ("artist", "TPE1"), ("album", "TALB"))
        if key in tags
    )
    picture = b"\x00image/jpeg\x00\x03\x00" + bytes(cover)
    frames = id3_frame("APIC", picture, version) + frames  # the cover first
    path.write_bytes(
        id3_tag(frames, version) + FRAME * round(seconds * FRAMES_PER_SECOND)
    )
    return path


def flac_block(kind: int, data: bytes, last: bool = False) -> bytes:
    """Return a FLAC metadata block."""
    return bytes([kind | (0x80 if last else 0)]) + len(data).to_bytes(3, "big") + data


def streaminfo(seconds: float, rate: int = 44100) -> bytes:
    """Return a STREAMINFO block body for seconds of audio."""
    samples = round(seconds * rate)
    packed = (rate << 44) | (1 << 41) | (15 << 36) | samples  # stereo, 16 bit
    return bytes(10) + packed.to_bytes(8, "big") + bytes(16)


def vorbis_comment(*entries: str) -> bytes:
    """Return a VORBIS_COMMENT block body."""
    vendor = b"test"
    out = len(vendor).to_bytes(4, "little") + vendor
    out += len(entries).to_bytes(4, "little")
    for entry in entries:
        raw = entry.encode()
        out += len(raw).to_bytes(4, "little") + raw
    return out


def write_flac(path: Path, *blocks: bytes) -> Path:
    """Write a FLAC file of the given metadata blocks (no audio frames)."""
    path.write_bytes(b"fLaC" + b"".join(blocks))
    return path
