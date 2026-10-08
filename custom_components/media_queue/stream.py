"""Stream URLs typed on the Muziek page or given to the add_url action.

Only http and https URLs with a host are accepted (no file://, no
media-source:// or other schemes). A URL whose path ends in .m3u, .m3u8 or
.pls is fetched (bounded in time and size) and expanded into its http(s)
entries; any other URL is one stream item and is not requested here at all.
"""

from __future__ import annotations

import asyncio
from urllib.parse import unquote, urljoin, urlsplit

import aiohttp
from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .expand import Expansion, clean_title
from .model import QueueItem
from .playlist import is_playlist, m3u_entries, pls_entries

SCHEMES = ("http", "https")
MAX_URL = 2000
# Seconds and bytes a playlist download may take.
STREAM_TIMEOUT = 10
MAX_PLAYLIST_BYTES = 256 * 1024
# What a server may call a playlist (many send plain text or bytes).
PLAYLIST_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
    "audio/x-scpls",
    "text/plain",
}


def _invalid(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def _is_web(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme.lower() in SCHEMES and bool(parts.hostname)


def check_url(url: str) -> str:
    """Return the trimmed URL, or raise when it is no http(s) URL with a host."""
    url = url.strip()
    if len(url) > MAX_URL or any(c.isspace() for c in url) or not _is_web(url):
        raise _invalid("invalid_url")
    return url


def _stream(url: str, title: str | None) -> QueueItem:
    parts = urlsplit(url)
    name = unquote(parts.path.rstrip("/").rsplit("/", 1)[-1]) or parts.hostname
    return QueueItem(
        media_content_id=url,
        media_content_type=MediaType.MUSIC.value,
        title=clean_title(title or name or url),
        media_class=MediaClass.MUSIC.value,
    )


async def async_expand_url(
    hass: HomeAssistant, url: str, title: str | None, *, limit: int
) -> Expansion:
    """Return the stream items of url, at most limit of them."""
    url = check_url(url)
    path = urlsplit(url).path
    if not is_playlist(path):
        return Expansion(items=[_stream(url, title)])
    text = await _fetch(hass, url)
    pairs = pls_entries(text) if path.lower().endswith(".pls") else m3u_entries(text)
    items = [
        _stream(target, entry_title)
        for target, entry_title in (
            (urljoin(url, raw.strip()), entry_title) for raw, entry_title in pairs
        )
        if _is_web(target)
    ]
    if not items:
        raise _invalid("stream_empty", url=url)
    return Expansion(items=items[:limit], truncated=len(items) > limit)


async def _fetch(hass: HomeAssistant, url: str) -> str:
    """Return the start of the playlist at url as text."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(STREAM_TIMEOUT), session.get(url) as response:
            response.raise_for_status()
            content_type = (
                response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            )
            if content_type not in PLAYLIST_CONTENT_TYPES:
                raise _invalid("stream_bad_content", url=url, content_type=content_type)
            raw = await response.content.read(MAX_PLAYLIST_BYTES)
    except (TimeoutError, aiohttp.ClientError) as err:
        raise _invalid("stream_unreachable", url=url) from err
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")
