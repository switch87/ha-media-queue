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
from .model import Mode, Repeat
from .websocket import HISTORY_LIMIT, can_manage_playlists, history_result

INDEX = vol.All(vol.Coerce(int), vol.Range(min=0))
# The library allows 100 characters after trimming; this only bounds the input.
NAME = vol.All(cv.string, vol.Length(max=200))
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
    if call.service in ("add", "add_url", "load_playlist"):
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


async def _add_url(controller: QueueController, call: ServiceCall) -> ServiceResponse:
    return await controller.async_add_url(
        call.data["url"],
        Mode(call.data["mode"]),
        call.data.get("title"),
        context=call.context,
    )


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


async def _set_shuffle(controller: QueueController, call: ServiceCall) -> None:
    controller.set_shuffle(call.data["shuffle"])


async def _set_repeat(controller: QueueController, call: ServiceCall) -> None:
    controller.set_repeat(Repeat(call.data["repeat"]))


async def _save_playlist(
    controller: QueueController, call: ServiceCall
) -> ServiceResponse:
    library = async_get_manager(controller.hass).library
    playlist = library.save(
        call.data["name"], controller.queue.items, overwrite=call.data["overwrite"]
    )
    return playlist.summary()


async def _load_playlist(
    controller: QueueController, call: ServiceCall
) -> ServiceResponse:
    library = async_get_manager(controller.hass).library
    items = library.load(library.named(call.data["name"]).playlist_id, None)
    return await controller.async_add_items(
        items, Mode(call.data["mode"]), context=call.context
    )


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
    (
        "add_url",
        _add_url,
        {
            vol.Required("url"): vol.All(cv.string, vol.Length(max=2100)),
            vol.Optional("mode", default=Mode.ADD.value): vol.In(
                [mode.value for mode in Mode]
            ),
            vol.Optional("title"): NAME,
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
    (
        "set_shuffle",
        _set_shuffle,
        {vol.Required("shuffle"): cv.boolean},
        SupportsResponse.NONE,
    ),
    (
        "set_repeat",
        _set_repeat,
        {vol.Required("repeat"): vol.In([repeat.value for repeat in Repeat])},
        SupportsResponse.NONE,
    ),
    ("get_queue", _get_queue, {}, SupportsResponse.ONLY),
    (
        "save_playlist",
        _save_playlist,
        {
            vol.Required("name"): NAME,
            vol.Optional("overwrite", default=False): cv.boolean,
        },
        SupportsResponse.OPTIONAL,
    ),
    (
        "load_playlist",
        _load_playlist,
        {
            vol.Required("name"): NAME,
            vol.Optional("mode", default=Mode.ADD.value): vol.In(
                [mode.value for mode in Mode]
            ),
        },
        SupportsResponse.OPTIONAL,
    ),
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
    async_register_library(hass)


async def _check_manager(hass: HomeAssistant, call: ServiceCall) -> None:
    """Refuse users who may not rename or delete playlists."""
    if call.context.user_id is None:
        return
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None:
        raise UnknownUser(context=call.context)
    if not can_manage_playlists(hass, user):
        raise Unauthorized(context=call.context, permission=POLICY_CONTROL)


@callback
def async_register_library(hass: HomeAssistant) -> None:
    """Register the actions on the playlist library (no player involved)."""

    async def get_playlists(call: ServiceCall) -> ServiceResponse:
        summaries: list[Any] = async_get_manager(hass).library.summaries()
        return {"playlists": summaries}

    async def rename_playlist(call: ServiceCall) -> None:
        await _check_manager(hass, call)
        library = async_get_manager(hass).library
        library.rename(
            library.named(call.data["name"]).playlist_id, call.data["new_name"]
        )

    async def delete_playlist(call: ServiceCall) -> None:
        await _check_manager(hass, call)
        library = async_get_manager(hass).library
        library.delete(library.named(call.data["name"]).playlist_id)

    async def get_history(call: ServiceCall) -> ServiceResponse:
        return history_result(hass, call.data["limit"])

    async def reset_history(call: ServiceCall) -> None:
        await _check_manager(hass, call)
        async_get_manager(hass).history.reset()

    hass.services.async_register(
        DOMAIN,
        "get_history",
        get_history,
        schema=vol.Schema({vol.Optional("limit", default=100): HISTORY_LIMIT}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "reset_history", reset_history, schema=vol.Schema({})
    )
    hass.services.async_register(
        DOMAIN,
        "get_playlists",
        get_playlists,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "rename_playlist",
        rename_playlist,
        schema=vol.Schema({vol.Required("name"): NAME, vol.Required("new_name"): NAME}),
    )
    hass.services.async_register(
        DOMAIN,
        "delete_playlist",
        delete_playlist,
        schema=vol.Schema({vol.Required("name"): NAME}),
    )
