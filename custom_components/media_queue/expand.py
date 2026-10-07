"""Turn a browse item (track, album, folder, …) into playable queue items."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote

from homeassistant.components import media_source
from homeassistant.components.media_player import DATA_COMPONENT
from homeassistant.components.media_player.browse_media import BrowseMedia
from homeassistant.components.media_player.const import (
    MediaClass,
    MediaPlayerEntityFeature,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .model import QueueItem
from .playlist import is_playlist, read_playlist

_LOGGER = logging.getLogger(__name__)

# Folder levels opened below the added item, and browse calls per add: enough for
# artist/album/disc trees, bounded for sources with endless trees (radio lists).
MAX_DEPTH = 8
MAX_BROWSE_CALLS = 200
# Playlist files are listed as audio by the media source but are no tracks;
# inside a folder they are skipped (like cover images).
PLAYLIST_TYPES = {
    "application/vnd.apple.mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
    "audio/x-scpls",
}


# The local media source sorts plainly ("10" before "2"); its order is redone.
LOCAL_MEDIA = "media-source://media_source/"
VIDEO_CLASSES = {
    MediaClass.VIDEO,
    MediaClass.MOVIE,
    MediaClass.EPISODE,
    MediaClass.TV_SHOW,
    MediaClass.SEASON,
}
MAX_TITLE = 300
MAX_THUMBNAIL = 2000
# Thumbnails the panel may load: web images and Home Assistant's media paths.
THUMBNAIL_PREFIXES = (
    "http://",
    "https://",
    "/api/media_player_proxy/",
    "/api/image_proxy/",
    "/api/brands/",
    "/media/",
)


def clean_title(title: str) -> str:
    """Return the title trimmed and capped."""
    return title.strip()[:MAX_TITLE]


def clean_thumbnail(url: str | None) -> str | None:
    """Return url if it is an image URL the panel may load, else None."""
    if url and len(url) <= MAX_THUMBNAIL and url.startswith(THUMBNAIL_PREFIXES):
        return url
    return None


@dataclass(frozen=True, slots=True, kw_only=True)
class AddRequest:
    """An item to add, as the panel or a service call describes it."""

    media_content_id: str
    media_content_type: str
    title: str | None = None
    media_class: str | None = None
    thumbnail: str | None = None
    can_expand: bool | None = None  # None: unknown, find out by browsing


@dataclass(slots=True)
class Expansion:
    """The playable items found, and whether the limit cut some off."""

    items: list[QueueItem] = field(default_factory=list)
    truncated: bool = False


class _Unbrowsable(Exception):
    """The item cannot be browsed (no player, no browse support, an error)."""


class _Full(Exception):
    """The limit or the browse budget is reached."""


async def async_expand(
    hass: HomeAssistant, entity_id: str, request: AddRequest, *, limit: int
) -> Expansion:
    """Return the playable items below request, at most limit of them."""
    if limit <= 0:
        return Expansion(truncated=True)
    if (playlist := _local_playlist(hass, request.media_content_id)) is not None:
        return await _expand_playlist(hass, request, *playlist, limit=limit)
    if request.can_expand is False:
        return Expansion(items=[_leaf(request)])
    walker = _Walker(hass, entity_id, limit)
    try:
        top = await walker.browse(request.media_content_id, request.media_content_type)
    except _Unbrowsable as err:
        if request.can_expand:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cannot_browse",
                translation_placeholders={
                    "item": request.title or request.media_content_id
                },
            ) from err
        return Expansion(items=[_leaf(request)])
    try:
        await walker.add(top, depth=0, top=True)
    except _Full:
        walker.result.truncated = True
    return walker.result


class _Walker:
    """Depth-first walk through a browse tree, collecting playable leaves."""

    def __init__(self, hass: HomeAssistant, entity_id: str, limit: int) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self.limit = limit
        self.result = Expansion()
        self.opened: set[str] = set()
        self.calls = 0
        # Videos inside folders are only queued for players that show them.
        player = hass.states.get(entity_id)
        self.videos = (
            player is not None and player.attributes.get("device_class") == "tv"
        )

    async def browse(self, content_id: str, content_type: str) -> BrowseMedia:
        """Browse one item through the media source or the player."""
        self.calls += 1
        self.opened.add(content_id)
        try:
            if media_source.is_media_source_id(content_id):
                return await media_source.async_browse_media(self.hass, content_id)
            component = self.hass.data.get(DATA_COMPONENT)
            player = component.get_entity(self.entity_id) if component else None
            if (
                player is None
                or MediaPlayerEntityFeature.BROWSE_MEDIA
                not in player.supported_features
            ):
                raise _Unbrowsable(content_id)
            return await player.async_browse_media(content_type, content_id)
        except (HomeAssistantError, NotImplementedError) as err:
            raise _Unbrowsable(content_id) from err

    async def add(self, item: BrowseMedia, *, depth: int, top: bool = False) -> None:
        """Add item, or what is below it, to the result."""
        if not item.can_expand:
            if item.can_play and (top or self._is_track(item)):
                self._append(item)
            return
        before = len(self.result.items)
        if item.children is None and not top:
            if depth < MAX_DEPTH and item.media_content_id not in self.opened:
                await self._open(item, depth)
        else:
            for child in _ordered(item):
                await self.add(child, depth=depth + 1)
        if len(self.result.items) == before and item.can_play:
            self._append(item)

    async def _open(self, item: BrowseMedia, depth: int) -> None:
        if self.calls >= MAX_BROWSE_CALLS:
            raise _Full
        try:
            listed = await self.browse(item.media_content_id, item.media_content_type)
        except _Unbrowsable:
            _LOGGER.debug("Skipping %s: it cannot be browsed", item.media_content_id)
            return
        for child in _ordered(listed):
            await self.add(child, depth=depth + 1)

    def _is_track(self, item: BrowseMedia) -> bool:
        """Return whether a playable item in a folder belongs in the queue."""
        if item.media_class == MediaClass.IMAGE:
            return False
        if item.media_content_type in PLAYLIST_TYPES:
            return False
        is_video = item.media_class in VIDEO_CLASSES or str(
            item.media_content_type
        ).startswith("video/")
        return self.videos or not is_video

    def _append(self, item: BrowseMedia) -> None:
        if len(self.result.items) >= self.limit:
            raise _Full
        self.result.items.append(
            QueueItem(
                media_content_id=item.media_content_id,
                media_content_type=item.media_content_type,
                title=clean_title(item.title),
                media_class=str(item.media_class) if item.media_class else None,
                thumbnail=clean_thumbnail(item.thumbnail),
            )
        )


def _natural(title: str) -> list[tuple[int, int, str]]:
    """Return a sort key in which "2" comes before "10"."""
    return [
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in re.split(r"(\d+)", title.casefold())
    ]


def _ordered(node: BrowseMedia) -> list[BrowseMedia]:
    """Return the children; local media folders first, then files, naturally."""
    children = list(node.children or [])
    if node.media_content_id.startswith(LOCAL_MEDIA):
        children.sort(key=lambda child: (child.can_play, _natural(child.title)))
    return children


def _local_playlist(hass: HomeAssistant, content_id: str) -> tuple[str, str] | None:
    """Return (media dir, path) when content_id is a playlist of local media."""
    if not content_id.startswith(LOCAL_MEDIA):
        return None
    media_dir, _, relative = content_id.removeprefix(LOCAL_MEDIA).partition("/")
    if media_dir in hass.config.media_dirs and is_playlist(relative):
        return media_dir, relative
    return None


async def _expand_playlist(
    hass: HomeAssistant,
    request: AddRequest,
    media_dir: str,
    relative: str,
    *,
    limit: int,
) -> Expansion:
    """Return the entries of a local playlist as queue items."""
    root = Path(hass.config.media_dirs[media_dir])
    try:
        items = await hass.async_add_executor_job(
            _playlist_items, root, media_dir, relative
        )
    except (OSError, ValueError) as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="cannot_browse",
            translation_placeholders={
                "item": request.title or request.media_content_id
            },
        ) from err
    return Expansion(items=items[:limit], truncated=len(items) > limit)


def _playlist_items(root: Path, media_dir: str, relative: str) -> list[QueueItem]:
    """Read a playlist and return its entries as items (runs in the executor)."""
    items: list[QueueItem] = []
    for entry in read_playlist(root, relative):
        name = unquote(entry.target.rstrip("/").rsplit("/", 1)[-1])
        if entry.kind == "url":
            content_id, content_type = entry.target, MediaType.MUSIC.value
        else:
            content_id = f"{LOCAL_MEDIA}{media_dir}/{entry.target}"
            content_type = mimetypes.guess_type(entry.target)[0] or "audio/mpeg"
        items.append(
            QueueItem(
                media_content_id=content_id,
                media_content_type=content_type,
                title=clean_title(entry.title or name),
                media_class=MediaClass.MUSIC.value,
            )
        )
    return items


def _leaf(request: AddRequest) -> QueueItem:
    """Return the queue item for a request that is played as it is."""
    title = request.title or unquote(request.media_content_id.rsplit("/", 1)[-1])
    return QueueItem(
        media_content_id=request.media_content_id,
        media_content_type=request.media_content_type,
        title=clean_title(title),
        media_class=request.media_class,
        thumbnail=clean_thumbnail(request.thumbnail),
    )
