"""Websocket commands for the panel."""

from __future__ import annotations

from typing import Any

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

from .expand import AddRequest
from .manager import async_get_manager
from .model import Mode

ENTITY: dict[str | vol.Marker, Any] = {
    vol.Required("entity_id"): cv.entity_domain(MEDIA_PLAYER_DOMAIN)
}
INDEX = vol.All(vol.Coerce(int), vol.Range(min=0))
type Connection = ActiveConnection


def _allow(connection: Connection, entity_id: str, policy: str) -> None:
    """Refuse users whose permissions do not cover the player."""
    if not connection.user.permissions.check_entity(entity_id, policy):
        raise Unauthorized(entity_id=entity_id, permission=policy)


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

    connection.subscriptions[msg["id"]] = manager.subscribe(entity_id, forward)
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


@websocket_command(
    {
        vol.Required("type"): "media_queue/play_index",
        **ENTITY,
        vol.Required("index"): INDEX,
    }
)
@async_response
async def ws_play_index(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Jump to an item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).controller(msg["entity_id"])
    await controller.async_play(msg["index"], context=connection.context(msg))
    connection.send_result(msg["id"])


@websocket_command({vol.Required("type"): "media_queue/next", **ENTITY})
@async_response
async def ws_next(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Play the next item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).controller(msg["entity_id"])
    await controller.async_next(context=connection.context(msg))
    connection.send_result(msg["id"])


@websocket_command({vol.Required("type"): "media_queue/previous", **ENTITY})
@async_response
async def ws_previous(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Play the previous item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).controller(msg["entity_id"])
    await controller.async_previous(context=connection.context(msg))
    connection.send_result(msg["id"])


@websocket_command(
    {vol.Required("type"): "media_queue/remove", **ENTITY, vol.Required("index"): INDEX}
)
@callback
def ws_remove(hass: HomeAssistant, connection: Connection, msg: dict[str, Any]) -> None:
    """Remove an item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    async_get_manager(hass).controller(msg["entity_id"]).remove(msg["index"])
    connection.send_result(msg["id"])


@websocket_command(
    {
        vol.Required("type"): "media_queue/move",
        **ENTITY,
        vol.Required("from_index"): INDEX,
        vol.Required("to_index"): INDEX,
    }
)
@callback
def ws_move(hass: HomeAssistant, connection: Connection, msg: dict[str, Any]) -> None:
    """Move an item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    controller = async_get_manager(hass).controller(msg["entity_id"])
    controller.move(msg["from_index"], msg["to_index"])
    connection.send_result(msg["id"])


@websocket_command({vol.Required("type"): "media_queue/clear", **ENTITY})
@callback
def ws_clear(hass: HomeAssistant, connection: Connection, msg: dict[str, Any]) -> None:
    """Remove every item."""
    _allow(connection, msg["entity_id"], POLICY_CONTROL)
    async_get_manager(hass).controller(msg["entity_id"]).clear()
    connection.send_result(msg["id"])
