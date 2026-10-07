"""The saved playlists as a media source, for HA's own media browser.

A playlist opens to its tracks; each track plays with its original media id.
The playlist itself is not playable here (HA's media browser plays one
item): whole playlists are loaded from the Muziek page or the action.
"""

from __future__ import annotations

from homeassistant.components.media_player.browse_media import BrowseMedia
from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .library import Playlist, PlaylistLibrary
from .manager import async_get_manager
from .model import QueueItem

NAMES = {"nl": "Afspeellijsten (Muziek)"}
NAME = "Playlists (Media queue)"


async def async_get_media_source(hass: HomeAssistant) -> PlaylistSource:
    """Return the playlist media source."""
    return PlaylistSource(hass)


class PlaylistSource(MediaSource):
    """Saved playlists, browsable by every player."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Name the source in the installation's language."""
        self.name = NAMES.get(hass.config.language.split("-")[0], NAME)
        super().__init__(DOMAIN)

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Refuse: a whole playlist is loaded from the Muziek page."""
        raise Unresolvable(
            "A playlist is loaded into a queue from the Muziek page or the "
            "media_queue.load_playlist action; its tracks play from here"
        )

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """List the playlists, or the tracks of one."""
        library = _library(item.hass)
        if not item.identifier:
            return self._node(
                None,
                self.name or NAME,
                [self._node(p.playlist_id, p.name) for p in _sorted(library)],
            )
        try:
            playlist = library.get(item.identifier)
        except HomeAssistantError as err:
            raise BrowseError(str(err)) from err
        return self._node(
            playlist.playlist_id, playlist.name, [_track(i) for i in playlist.items]
        )

    @staticmethod
    def _node(
        identifier: str | None,
        title: str,
        children: list[BrowseMedia] | None = None,
    ) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY
            if identifier is None
            else MediaClass.PLAYLIST,
            media_content_type=MediaType.PLAYLIST,
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=(
                MediaClass.PLAYLIST if identifier is None else MediaClass.TRACK
            ),
        )


def _library(hass: HomeAssistant) -> PlaylistLibrary:
    try:
        return async_get_manager(hass).library
    except HomeAssistantError as err:
        raise BrowseError(str(err)) from err


def _sorted(library: PlaylistLibrary) -> list[Playlist]:
    return [library.get(summary["id"]) for summary in library.summaries()]


def _track(item: QueueItem) -> BrowseMedia:
    title = f"{item.title} – {item.artist}" if item.artist else item.title
    return BrowseMedia(
        media_class=item.media_class or MediaClass.MUSIC,
        media_content_id=item.media_content_id,
        media_content_type=item.media_content_type,
        title=title,
        can_play=True,
        can_expand=False,
        thumbnail=item.thumbnail,
    )
