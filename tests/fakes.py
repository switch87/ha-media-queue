"""A fake media player with a browse tree, for tests."""

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.browse_media import BrowseMedia
from homeassistant.components.media_player.const import (
    MediaClass,
    MediaPlayerEntityFeature,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    setup_test_component_platform,
)


def node(
    content_id: str,
    title: str,
    *,
    children: list[BrowseMedia] | None = None,
    can_play: bool = True,
    can_expand: bool = False,
    media_class: MediaClass = MediaClass.TRACK,
    content_type: str = "track",
    thumbnail: str | None = None,
) -> BrowseMedia:
    """Return a browse node."""
    return BrowseMedia(
        media_class=media_class,
        media_content_id=content_id,
        media_content_type=content_type,
        title=title,
        can_play=can_play,
        can_expand=can_expand,
        children=children,
        thumbnail=thumbnail,
    )


def folder(
    content_id: str,
    title: str,
    children: list[BrowseMedia] | None = None,
    *,
    can_play: bool = False,
) -> BrowseMedia:
    """Return an expandable node (children None when listed as a child)."""
    return node(
        content_id,
        title,
        children=children,
        can_play=can_play,
        can_expand=True,
        media_class=MediaClass.ALBUM,
        content_type="album",
    )


class FakePlayer(MediaPlayerEntity):
    """A player whose library is a dict of browse results."""

    _attr_should_poll = False

    def __init__(
        self,
        name: str,
        tree: dict[str | None, BrowseMedia] | None = None,
        features: MediaPlayerEntityFeature = (
            MediaPlayerEntityFeature.BROWSE_MEDIA | MediaPlayerEntityFeature.PLAY_MEDIA
        ),
    ) -> None:
        """Create the player."""
        self._attr_name = name
        self._attr_unique_id = name
        self._attr_supported_features = features
        self.tree = tree or {}
        self.browsed: list[str | None] = []

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Return the node for media_content_id."""
        self.browsed.append(media_content_id)
        if media_content_id == "not-implemented":
            raise NotImplementedError
        if media_content_id not in self.tree:
            raise BrowseError(f"No such item {media_content_id}")
        return self.tree[media_content_id]


async def async_add_players(hass: HomeAssistant, *players: FakePlayer) -> None:
    """Set up the media_player component with the given fake players."""
    setup_test_component_platform(hass, "media_player", players)
    assert await async_setup_component(
        hass, "media_player", {"media_player": {"platform": "test"}}
    )
    await hass.async_block_till_done()
