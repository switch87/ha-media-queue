"""Actions (services) for automations and scripts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components.media_player.const import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import Unauthorized, UnknownUser
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .controller import QueueController
from .expand import AddRequest
from .manager import async_get_manager
from .model import Mode

INDEX = vol.All(vol.Coerce(int), vol.Range(min=0))
ENTITY: dict[str | vol.Marker, Any] = {
    vol.Required(ATTR_ENTITY_ID): cv.entity_domain(MEDIA_PLAYER_DOMAIN)
}

type Handler = Callable[[QueueController, ServiceCall], Awaitable[ServiceResponse]]


async def _controller(
    hass: HomeAssistant, call: ServiceCall, policy: str
) -> QueueController:
    """Return the controller of the call's player, checking the user's rights."""
    entity_id: str = call.data[ATTR_ENTITY_ID]
    if call.context.user_id is not None:
        user = await hass.auth.async_get_user(call.context.user_id)
        if user is None:
            raise UnknownUser(context=call.context)
        if not user.permissions.check_entity(entity_id, policy):
            raise Unauthorized(
                context=call.context, entity_id=entity_id, permission=policy
            )
    manager = async_get_manager(hass)
    if call.service == "add":
        return manager.controller(entity_id)
    return manager.existing(entity_id)


async def _add(controller: QueueController, call: ServiceCall) -> ServiceResponse:
    request = AddRequest(
        media_content_id=call.data["media_content_id"],
        media_content_type=call.data["media_content_type"],
        title=call.data.get("title"),
    )
    return await controller.async_add(
        request, Mode(call.data["mode"]), context=call.context
    )


def _position(controller: QueueController, call: ServiceCall, key: str) -> int:
    return controller.resolve(call.data.get("item_id"), call.data.get(key))


async def _play_index(controller: QueueController, call: ServiceCall) -> None:
    await controller.async_play(
        _position(controller, call, "index"), context=call.context
    )


async def _next(controller: QueueController, call: ServiceCall) -> None:
    await controller.async_next(context=call.context)


async def _previous(controller: QueueController, call: ServiceCall) -> None:
    await controller.async_previous(context=call.context)


async def _remove(controller: QueueController, call: ServiceCall) -> None:
    controller.remove(_position(controller, call, "index"))


async def _move(controller: QueueController, call: ServiceCall) -> None:
    controller.move(_position(controller, call, "from_index"), call.data["to_index"])


async def _clear(controller: QueueController, call: ServiceCall) -> None:
    controller.clear()


async def _get_queue(controller: QueueController, call: ServiceCall) -> ServiceResponse:
    return controller.snapshot()


ITEM: dict[str | vol.Marker, Any] = {
    vol.Optional("item_id"): cv.string,
    vol.Optional("index"): INDEX,
}
# The fields that name the item: one of them is required.
_ONE_OF = {
    "play_index": ("item_id", "index"),
    "remove": ("item_id", "index"),
    "move": ("item_id", "from_index"),
}

_SERVICES: list[tuple[str, Handler, dict[str | vol.Marker, Any], SupportsResponse]] = [
    (
        "add",
        _add,
        {
            vol.Required("media_content_id"): cv.string,
            vol.Required("media_content_type"): vol.Any(cv.string, ""),
            vol.Optional("mode", default=Mode.ADD.value): vol.In(
                [mode.value for mode in Mode]
            ),
            vol.Optional("title"): cv.string,
        },
        SupportsResponse.OPTIONAL,
    ),
    ("play_index", _play_index, ITEM, SupportsResponse.NONE),
    ("next", _next, {}, SupportsResponse.NONE),
    ("previous", _previous, {}, SupportsResponse.NONE),
    ("remove", _remove, ITEM, SupportsResponse.NONE),
    (
        "move",
        _move,
        {
            vol.Optional("item_id"): cv.string,
            vol.Optional("from_index"): INDEX,
            vol.Required("to_index"): INDEX,
        },
        SupportsResponse.NONE,
    ),
    ("clear", _clear, {}, SupportsResponse.NONE),
    ("get_queue", _get_queue, {}, SupportsResponse.ONLY),
]


def _schema(name: str, fields: dict[str | vol.Marker, Any]) -> vol.Schema | vol.All:
    schema = vol.Schema({**ENTITY, **fields})
    if name in _ONE_OF:
        return vol.All(schema, cv.has_at_least_one_key(*_ONE_OF[name]))
    return schema


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the media_queue actions."""
    for name, handler, fields, response in _SERVICES:
        policy = POLICY_READ if response is SupportsResponse.ONLY else POLICY_CONTROL

        async def handle(
            call: ServiceCall, handler: Handler = handler, policy: str = policy
        ) -> ServiceResponse:
            return await handler(await _controller(hass, call, policy), call)

        hass.services.async_register(
            DOMAIN,
            name,
            handle,
            schema=_schema(name, fields),
            supports_response=response,
        )
