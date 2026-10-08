"""Websocket commands for the panel."""

from __future__ import annotations

from typing import Any

from homeassistant.auth.models import User
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components.media_player.const import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.websocket_api import async_register_command
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    websocket_command,
)
from homeassistant.components.websocket_api.messages import event_message
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .controller import QueueController
from .expand import AddRequest
from .history import HISTORY_MAX
from .library import PLAYLIST_ITEMS, clean_name
from .manager import async_get_manager
from .model import Mode, Repeat
from .stream import MAX_URL, async_expand_url

ENTITY: dict[str | vol.Marker, Any] = {
    vol.Required("entity_id"): cv.entity_domain(MEDIA_PLAYER_DOMAIN)
}
INDEX = vol.All(vol.Coerce(int), vol.Range(min=0))


def _item_schema(command: str) -> vol.All:
    """Return a schema that names one item by item_id or index."""
    return vol.All(
        vol.Schema(
            {
                vol.Required("type"): command,
                **ENTITY,
                vol.Optional("item_id"): cv.string,
                vol.Optional("index"): INDEX,
            }
        ),
        cv.has_at_least_one_key("item_id", "index"),
    )


def _position(controller: QueueController, msg: dict[str, Any]) -> int:
    return controller.resolve(msg.get("item_id"), msg.get("index"))


type Connection = ActiveConnection


def _allow(connection: Connection, entity_id: str, policy: str) -> None:
    """Refuse users whose permissions do not cover the player."""
    if not connection.user.permissions.check_entity(entity_id, policy):
        raise Unauthorized(entity_id=entity_id, permission=policy)


def can_manage_playlists(hass: HomeAssistant, user: User) -> bool:
    """Return whether user may rename or delete playlists.

    Admins, and users who may control at least one media player.
    """
    return user.is_admin or any(
        user.permissions.check_entity(state.entity_id, POLICY_CONTROL)
        for state in hass.states.async_all(MEDIA_PLAYER_DOMAIN)
    )


def _allow_manage(hass: HomeAssistant, connection: Connection) -> None:
    if not can_manage_playlists(hass, connection.user):
        raise Unauthorized(permission=POLICY_CONTROL)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the media_queue/* commands."""
    for command in (
        ws_get,
        ws_subscribe,
        ws_add,
        ws_play_index,
        ws_next,
        ws_previous,
        ws_remove,
        ws_move,
        ws_clear,
        ws_set_shuffle,
        ws_set_repeat,
        ws_playlists_list,
        ws_playlists_get,
        ws_playlists_save,
        ws_playlists_rename,
        ws_playlists_delete,
        ws_playlists_load,
        ws_history_list,
        ws_history_reset,
        ws_add_url,
        ws_streams_save,
    ):
        async_register_command(hass, command)


@websocket_command({vol.Required("type"): "media_queue/get", **ENTITY})
@callback
def ws_get(hass: HomeAssistant, connection: Connection, msg: dict[str, Any]) -> None:
    """Return the queue of a player."""
    _allow(connection, msg["entity_id"], POLICY_READ)
    manager = async_get_manager(hass)
    connection.send_result(msg["id"], manager.snapshot(msg["entity_id"]))


@websocket_command({vol.Required("type"): "media_queue/subscribe", **ENTITY})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Send the queue of a player now and whenever it changes."""
    entity_id = msg["entity_id"]
    _allow(connection, entity_id, POLICY_READ)
    manager = async_get_manager(hass)

    @callback
    def forward(data: dict[str, Any]) -> None:
        connection.send_message(event_message(msg["id"], data))

    @callback
    def closed() -> None:
        # The entry unloads (reload, removal): the panel subscribes again.
        connection.subscriptions.pop(msg["id"], None)
        connection.send_message(
            event_message(msg["id"], {"entity_id": entity_id, "closed": True})
        )

    connection.subscriptions[msg["id"]] = manager.subscribe(entity_id, forward, closed)
    connection.send_result(msg["id"])
    forward(manager.snapshot(entity_id))


@websocket_command(
    {
        vol.Required("type"): "media_queue/add",
        **ENTITY,
        vol.Required("media_content_id"): cv.string,
        vol.Required("media_content_type"): vol.Any(cv.string, ""),
        vol.Optional("mode", default=Mode.ADD.value): vol.In([m.value for m in Mode]),
        vol.Optional("title"): vol.Any(None, cv.string),
        vol.Optional("media_class"): vol.Any(None, cv.string),
        vol.Optional("thumbnail"): vol.Any(None, cv.string),
        vol.Optional("can_expand"): vol.Any(None, cv.boolean),
    }
)
@async_response
async def ws_add(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Add a track, album or folder in the given mode."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).controller(msg["entity_id"])
    request = AddRequest(
        media_content_id=msg["media_content_id"],
        media_content_type=msg["media_content_type"],
        title=msg.get("title"),
        media_class=msg.get("media_class"),
        thumbnail=msg.get("thumbnail"),
        can_expand=msg.get("can_expand"),
    )
    result = await controller.async_add(
        request, Mode(msg["mode"]), context=connection.context(msg)
    )
    connection.send_result(msg["id"], result)


@websocket_command(_item_schema("media_queue/play_index"))
@async_response
async def ws_play_index(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Jump to an item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).existing(msg["entity_id"])
    await controller.async_play(
        _position(controller, msg), context=connection.context(msg)
    )
    connection.send_result(msg["id"])


@websocket_command({vol.Required("type"): "media_queue/next", **ENTITY})
@async_response
async def ws_next(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Play the next item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).existing(msg["entity_id"])
    await controller.async_next(context=connection.context(msg))
    connection.send_result(msg["id"])


@websocket_command({vol.Required("type"): "media_queue/previous", **ENTITY})
@async_response
async def ws_previous(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Play the previous item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).existing(msg["entity_id"])
    await controller.async_previous(context=connection.context(msg))
    connection.send_result(msg["id"])


@websocket_command(_item_schema("media_queue/remove"))
@callback
def ws_remove(hass: HomeAssistant, connection: Connection, msg: dict[str, Any]) -> None:
    """Remove an item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).existing(msg["entity_id"])
    controller.remove(_position(controller, msg))
    connection.send_result(msg["id"])


@websocket_command(
    vol.All(
        vol.Schema(
            {
                vol.Required("type"): "media_queue/move",
                **ENTITY,
                vol.Optional("item_id"): cv.string,
                vol.Optional("from_index"): INDEX,
                vol.Required("to_index"): INDEX,
            }
        ),
        cv.has_at_least_one_key("item_id", "from_index"),
    )
)
@callback
def ws_move(hass: HomeAssistant, connection: Connection, msg: dict[str, Any]) -> None:
    """Move an item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).existing(msg["entity_id"])
    source = controller.resolve(msg.get("item_id"), msg.get("from_index"))
    controller.move(source, msg["to_index"])
    connection.send_result(msg["id"])


@websocket_command({vol.Required("type"): "media_queue/clear", **ENTITY})
@callback
def ws_clear(hass: HomeAssistant, connection: Connection, msg: dict[str, Any]) -> None:
    """Remove every item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    async_get_manager(hass).existing(msg["entity_id"]).clear()
    connection.send_result(msg["id"])


@websocket_command(
    {
        vol.Required("type"): "media_queue/set_shuffle",
        **ENTITY,
        vol.Required("shuffle"): cv.boolean,
    }
)
@callback
def ws_set_shuffle(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Play the queue in order or shuffled."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    async_get_manager(hass).existing(msg["entity_id"]).set_shuffle(msg["shuffle"])
    connection.send_result(msg["id"])


@websocket_command(
    {
        vol.Required("type"): "media_queue/set_repeat",
        **ENTITY,
        vol.Required("repeat"): vol.In([r.value for r in Repeat]),
    }
)
@callback
def ws_set_repeat(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Repeat nothing, the queue or the current item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).existing(msg["entity_id"])
    controller.set_repeat(Repeat(msg["repeat"]))
    connection.send_result(msg["id"])


# ------------------------------------------------------------------ playlists

PLAYLIST_ID: dict[str | vol.Marker, Any] = {
    vol.Required("playlist_id"): vol.All(cv.string, vol.Length(max=64))
}
# The library allows 100 characters after trimming; this only bounds the input.
NAME = vol.All(cv.string, vol.Length(max=200))


@websocket_command({vol.Required("type"): "media_queue/playlists/list"})
@callback
def ws_playlists_list(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Return the summaries of every saved playlist."""
    library = async_get_manager(hass).library
    connection.send_result(msg["id"], {"playlists": library.summaries()})


@websocket_command({vol.Required("type"): "media_queue/playlists/get", **PLAYLIST_ID})
@callback
def ws_playlists_get(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Return a playlist with its items."""
    playlist = async_get_manager(hass).library.get(msg["playlist_id"])
    connection.send_result(msg["id"], playlist.as_dict())


@websocket_command(
    {
        vol.Required("type"): "media_queue/playlists/save",
        **ENTITY,
        vol.Required("name"): NAME,
        vol.Optional("overwrite", default=False): cv.boolean,
    }
)
@callback
def ws_playlists_save(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Save a player's queue (in its shown order) as a playlist."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    manager = async_get_manager(hass)
    controller = manager.get(msg["entity_id"])
    items = controller.queue.items if controller is not None else []
    playlist = manager.library.save(msg["name"], items, overwrite=msg["overwrite"])
    connection.send_result(msg["id"], playlist.summary())


@websocket_command(
    {
        vol.Required("type"): "media_queue/playlists/rename",
        **PLAYLIST_ID,
        vol.Required("name"): NAME,
    }
)
@callback
def ws_playlists_rename(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Give a playlist another name."""
    _allow_manage(hass, connection)
    library = async_get_manager(hass).library
    library.rename(msg["playlist_id"], msg["name"])
    connection.send_result(msg["id"], library.get(msg["playlist_id"]).summary())


@websocket_command(
    {vol.Required("type"): "media_queue/playlists/delete", **PLAYLIST_ID}
)
@callback
def ws_playlists_delete(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Delete a playlist."""
    _allow_manage(hass, connection)
    async_get_manager(hass).library.delete(msg["playlist_id"])
    connection.send_result(msg["id"])


@websocket_command(
    {
        vol.Required("type"): "media_queue/playlists/load",
        **ENTITY,
        **PLAYLIST_ID,
        vol.Optional("mode", default=Mode.ADD.value): vol.In([m.value for m in Mode]),
        vol.Optional("item_id"): cv.string,
    }
)
@async_response
async def ws_playlists_load(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Put a playlist (or one of its tracks) in a player's queue."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    manager = async_get_manager(hass)
    items = manager.library.load(msg["playlist_id"], msg.get("item_id"))
    result = await manager.controller(msg["entity_id"]).async_add_items(
        items, Mode(msg["mode"]), context=connection.context(msg)
    )
    connection.send_result(msg["id"], result)


# -------------------------------------------------------------------- history

HISTORY_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=HISTORY_MAX))


def history_result(hass: HomeAssistant, limit: int) -> dict[str, Any]:
    """Return the most played tracks and the totals."""
    history = async_get_manager(hass).history
    return {
        "tracks": history.entries(limit),
        "track_count": history.track_count,
        "play_count": history.play_count,
    }


@websocket_command(
    {
        vol.Required("type"): "media_queue/history/list",
        vol.Optional("limit", default=100): HISTORY_LIMIT,
    }
)
@callback
def ws_history_list(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Return the most played tracks."""
    connection.send_result(msg["id"], history_result(hass, msg["limit"]))


@websocket_command({vol.Required("type"): "media_queue/history/reset"})
@callback
def ws_history_reset(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Forget every play."""
    _allow_manage(hass, connection)
    async_get_manager(hass).history.reset()
    connection.send_result(msg["id"])


# -------------------------------------------------------------------- streams

URL = vol.All(cv.string, vol.Length(max=MAX_URL + 100))


@websocket_command(
    {
        vol.Required("type"): "media_queue/add_url",
        **ENTITY,
        vol.Required("url"): URL,
        vol.Optional("mode", default=Mode.ADD.value): vol.In([m.value for m in Mode]),
        vol.Optional("title"): vol.Any(None, NAME),
    }
)
@async_response
async def ws_add_url(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Add a stream URL (internet radio, a .m3u/.pls playlist) in a mode."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).controller(msg["entity_id"])
    result = await controller.async_add_url(
        msg["url"],
        Mode(msg["mode"]),
        msg.get("title"),
        context=connection.context(msg),
    )
    connection.send_result(msg["id"], result)


@websocket_command(
    {
        vol.Required("type"): "media_queue/streams/save",
        vol.Required("url"): URL,
        vol.Required("name"): NAME,
        vol.Optional("overwrite", default=False): cv.boolean,
    }
)
@async_response
async def ws_streams_save(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Save a stream URL as a favourite: a playlist of its stream(s)."""
    _allow_manage(hass, connection)
    library = async_get_manager(hass).library
    name = clean_name(msg["name"])
    expansion = await async_expand_url(hass, msg["url"], name, limit=PLAYLIST_ITEMS)
    playlist = library.save(name, expansion.items, overwrite=msg["overwrite"])
    connection.send_result(msg["id"], playlist.summary())
