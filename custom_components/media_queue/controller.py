"""The queue controller of one media player: playback and following the player."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
import logging
import math
from typing import Any

from homeassistant.components import media_source
from homeassistant.components.media_player.browse_media import (
    async_process_play_media_url,
)
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_DURATION,
    ATTR_MEDIA_POSITION,
    ATTR_MEDIA_POSITION_UPDATED_AT,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_PLAY_MEDIA,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN, QUEUE_LIMIT
from .expand import AddRequest, async_expand
from .model import Mode, Queue, QueueItem

_LOGGER = logging.getLogger(__name__)

# An item counts as finished when the player stops within this many seconds of
# its end (players report the position only now and then).
END_TOLERANCE = 5.0
# After our own play_media, a position below this (reported after the call)
# means the player restarted, also when it plays the same item again.
RESTART_WINDOW = 15.0
# Items that fail in a row before automatic advancing gives up.
MAX_SKIPS = 3
# Seconds a player may take to start an item before it counts as failed.
STARTING_TIMEOUT = 25

# "standby" is deprecated in HA but still reported by older integrations.
_STOPPED_STATES = {
    MediaPlayerState.IDLE,
    MediaPlayerState.OFF,
    MediaPlayerState.ON,
    "standby",
}


class Phase(StrEnum):
    """How far the controller follows the player."""

    IDLE = "idle"  # not following the player
    STARTING = "starting"  # we asked the player to play an item
    PLAYING = "playing"  # following the current item (also while paused)
    STOPPED = "stopped"  # stopped before its end by someone else


# A play in progress at shutdown is not resumed: it may never have started.
_RESTORED_PHASES = {Phase.PLAYING, Phase.STOPPED}


def _number(value: Any) -> float | None:
    """Return a finite number from a state attribute (MPD reports text)."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _datetime(value: Any) -> datetime | None:
    """Return an aware datetime from a state attribute (object or ISO text)."""
    if isinstance(value, str):
        value = dt_util.parse_datetime(value)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value
    return None


def _content_id(state: State) -> str | None:
    value = state.attributes.get(ATTR_MEDIA_CONTENT_ID)
    return value if isinstance(value, str) and value else None


def _nothing() -> None:
    """Do nothing (the unsubscribe of a controller that is not started)."""


def _media_type(mime_type: str) -> str:
    kind = mime_type.split("/", 1)[0]
    if kind == "video":
        return MediaType.VIDEO
    if kind == "image":
        return MediaType.IMAGE
    return MediaType.MUSIC


class QueueController:
    """The queue of one media_player entity and its playback."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        on_change: Callable[[QueueController], None],
        queue: Queue | None = None,
    ) -> None:
        """Create the controller for entity_id."""
        self.hass = hass
        self.entity_id = entity_id
        self.queue = queue if queue is not None else Queue()
        self.phase = Phase.IDLE
        self.fingerprint: str | None = None
        self._on_change = on_change
        self._lock = asyncio.Lock()
        self._unsubscribe: CALLBACK_TYPE = _nothing
        self._tasks: set[asyncio.Task[None]] = set()
        self._watchdog: CALLBACK_TYPE = _nothing
        # Plays that failed in a row (reset when an item really starts).
        self._failures = 0
        self.last_error: dict[str, str] | None = None
        # State of the play call in progress (phase STARTING).
        self._calling = False
        self._call_started = dt_util.utcnow()
        self._before_state: str | None = None
        self._before_id: str | None = None
        # Seconds the current item has played, for players without a position.
        self._played = 0.0
        self._playing_since: datetime | None = None

    # ------------------------------------------------------------------ setup

    @callback
    def async_start(self) -> None:
        """Start following the player's state."""
        self._unsubscribe = async_track_state_change_event(
            self.hass, [self.entity_id], self._on_state
        )

    @callback
    def async_stop(self) -> None:
        """Stop following the player and cancel an advance in progress."""
        self._unsubscribe()
        self._unsubscribe = _nothing
        self._cancel_watchdog()
        for task in self._tasks:
            task.cancel()

    @callback
    def async_changed(self) -> None:
        """Tell the manager that the queue or phase changed."""
        self._on_change(self)

    # --------------------------------------------------------------- commands

    async def async_add(
        self, request: AddRequest, mode: Mode, *, context: Context | None = None
    ) -> dict[str, Any]:
        """Add what request points at; replace and play also start playing."""
        room = (
            QUEUE_LIMIT if mode is Mode.REPLACE else QUEUE_LIMIT - len(self.queue.items)
        )
        expansion = await async_expand(self.hass, self.entity_id, request, limit=room)
        if not expansion.items:
            if expansion.truncated:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="queue_full",
                    translation_placeholders={"limit": str(QUEUE_LIMIT)},
                )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="nothing_to_add",
                translation_placeholders={
                    "item": request.title or request.media_content_id
                },
            )
        async with self._lock:
            result = self.queue.add(expansion.items, mode, limit=QUEUE_LIMIT)
            if mode in (Mode.REPLACE, Mode.PLAY):
                self._failures = 0
                await self._play(result.start, context)
            else:
                self.async_changed()
        return {
            "added": result.added,
            "truncated": expansion.truncated or result.truncated,
            "limit": QUEUE_LIMIT,
        }

    async def async_next(self, *, context: Context | None = None) -> None:
        """Play the next item."""
        async with self._lock:
            index = self.queue.next_position
            if index >= len(self.queue.items):
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="end_of_queue"
                )
            self._failures = 0
            await self._play(index, context)

    async def async_previous(self, *, context: Context | None = None) -> None:
        """Play the previous item (the first one again at the start)."""
        async with self._lock:
            index = self.queue.previous_position
            if index is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="queue_empty"
                )
            self._failures = 0
            await self._play(index, context)

    @callback
    def remove(self, index: int) -> None:
        """Remove the item at index (the player keeps playing it if current)."""
        self._check(index)
        self.queue.remove(index)
        self.async_changed()

    @callback
    def move(self, source: int, target: int) -> None:
        """Move the item at source to target."""
        self._check(source)
        self._check(target)
        self.queue.move(source, target)
        self.async_changed()

    @callback
    def clear(self) -> None:
        """Remove every item; a playing item plays on, then the queue stops."""
        self.queue.clear()
        self.async_changed()

    def _check(self, index: int) -> None:
        if not 0 <= index < len(self.queue.items):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_index",
                translation_placeholders={
                    "index": str(index),
                    "count": str(len(self.queue.items)),
                },
            )

    # --------------------------------------------------------------- playback

    async def async_play(self, index: int, *, context: Context | None = None) -> None:
        """Play the item at index now."""
        async with self._lock:
            self._failures = 0
            await self._play(index, context)

    async def _play(self, index: int, context: Context | None = None) -> None:
        """Play the item at index; the caller holds the lock."""
        self._check(index)
        self._cancel_watchdog()
        item = self.queue.items[index]
        self.queue.set_current(index)
        before = self.hass.states.get(self.entity_id)
        self._before_state = before.state if before else None
        self._before_id = _content_id(before) if before else None
        self._call_started = dt_util.utcnow()
        self._calling = True
        self.phase = Phase.STARTING
        self.fingerprint = None
        self.async_changed()
        try:
            await self._play_media(item, context)
        except Exception as err:  # players raise their own errors (MPD)
            self.phase = Phase.IDLE
            self._error("cannot_play", item, str(err))
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_play",
                translation_placeholders={"title": item.title, "error": str(err)},
            ) from err
        finally:
            self._calling = False
        state = self.hass.states.get(self.entity_id)
        if (
            state is not None
            and state.state == MediaPlayerState.PLAYING
            and (self._before_state != MediaPlayerState.PLAYING or self._is_new(state))
        ):
            self._arm(state)
        else:
            self._watchdog = async_call_later(
                self.hass, STARTING_TIMEOUT, self._starting_timed_out
            )

    async def _play_media(self, item: QueueItem, context: Context | None) -> None:
        content_id = item.media_content_id
        content_type = item.media_content_type
        if media_source.is_media_source_id(content_id):
            resolved = await media_source.async_resolve_media(
                self.hass, content_id, self.entity_id
            )
            content_id = async_process_play_media_url(self.hass, resolved.url)
            content_type = _media_type(resolved.mime_type)
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                ATTR_ENTITY_ID: self.entity_id,
                ATTR_MEDIA_CONTENT_ID: content_id,
                ATTR_MEDIA_CONTENT_TYPE: content_type,
            },
            blocking=True,
            context=context,
        )

    async def _advance(self) -> None:
        """Play the next item after a natural end, skipping failing items."""
        async with self._lock:
            index = self.queue.next_position
            while index < len(self.queue.items) and self._failures < MAX_SKIPS:
                try:
                    await self._play(index)
                except HomeAssistantError as err:
                    _LOGGER.warning(
                        "%s: skipping item %s: %s", self.entity_id, index, err
                    )
                    self._failures += 1
                    index += 1
                else:
                    return
            self.phase = Phase.IDLE
            self.fingerprint = None
            self.async_changed()

    @callback
    def _starting_timed_out(self, _now: datetime) -> None:
        """Skip the item the player did not start in time."""
        self._watchdog = _nothing
        current = self.queue.current
        item = self.queue.items[current] if current is not None else None
        self._failures += 1
        self._error("did_not_start", item, "")
        self._schedule_advance()

    def _schedule_advance(self) -> None:
        self.phase = Phase.STARTING  # until _advance has the lock
        task = self.hass.async_create_background_task(
            self._advance(), f"{DOMAIN} advance {self.entity_id}"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _error(self, kind: str, item: QueueItem | None, message: str) -> None:
        self.last_error = {
            "kind": kind,
            "title": item.title if item is not None else "",
            "message": message,
            "at": dt_util.utcnow().isoformat(),
        }
        self.async_changed()

    def _cancel_watchdog(self) -> None:
        self._watchdog()
        self._watchdog = _nothing

    # ---------------------------------------------------------- state machine

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        old = event.data["old_state"]
        if new is None or self._calling:
            return
        if self.phase is Phase.STARTING:
            if new.state == MediaPlayerState.PLAYING and (
                old is None
                or old.state != MediaPlayerState.PLAYING
                or self._is_new(new)
            ):
                self._arm(new)
        elif self.phase is Phase.PLAYING:
            self._while_playing(old, new)
        elif self.phase is Phase.STOPPED and new.state == MediaPlayerState.PLAYING:
            if self._other_media(new):
                self._detach()
            else:
                self.phase = Phase.PLAYING
                self._playing_since = new.last_changed
                self.async_changed()

    def _while_playing(self, old: State | None, new: State) -> None:
        if new.state == MediaPlayerState.PLAYING:
            if self._other_media(new):
                self._detach()
                return
            if self.fingerprint is None and _content_id(new) is not None:
                self.fingerprint = _content_id(new)
                self.async_changed()
            if old is None or old.state != MediaPlayerState.PLAYING:
                self._playing_since = new.last_changed
            return
        if old is None or old.state != MediaPlayerState.PLAYING:
            if new.state in _STOPPED_STATES:
                self._stopped()
            return
        if new.state not in _STOPPED_STATES and new.state != MediaPlayerState.PAUSED:
            return  # unavailable, buffering, …: wait and see
        at = new.last_changed
        if self._ended(old, at):
            self._schedule_advance()
            return
        if self._playing_since is not None:
            self._played += (at - self._playing_since).total_seconds()
            self._playing_since = None
        if new.state in _STOPPED_STATES:
            self._stopped()

    def _ended(self, old: State, at: datetime) -> bool:
        """Return whether the item old was playing has reached its end."""
        duration = _number(old.attributes.get(ATTR_MEDIA_DURATION))
        if not duration:
            return False  # streams and unknown lengths never end by themselves
        position = _number(old.attributes.get(ATTR_MEDIA_POSITION))
        if position is None:
            if self._playing_since is None:
                return False
            position = self._played + (at - self._playing_since).total_seconds()
        elif updated := _datetime(old.attributes.get(ATTR_MEDIA_POSITION_UPDATED_AT)):
            position += (at - updated).total_seconds()
        return position >= duration - END_TOLERANCE

    def _is_new(self, state: State) -> bool:
        """Return whether a playing state shows the item we just started."""
        if _content_id(state) != self._before_id:
            return True
        position = _number(state.attributes.get(ATTR_MEDIA_POSITION))
        updated = _datetime(state.attributes.get(ATTR_MEDIA_POSITION_UPDATED_AT))
        return (
            position is not None
            and updated is not None
            and updated >= self._call_started
            and position < RESTART_WINDOW
        )

    def _other_media(self, state: State) -> bool:
        """Return whether the player now plays something we did not start."""
        content_id = _content_id(state)
        return (
            self.fingerprint is not None
            and content_id is not None
            and content_id != self.fingerprint
        )

    def _arm(self, state: State) -> None:
        self._cancel_watchdog()
        self._failures = 0
        self.phase = Phase.PLAYING
        self.fingerprint = _content_id(state)
        self._played = 0.0
        self._playing_since = state.last_changed
        self.async_changed()

    def _stopped(self) -> None:
        self.phase = Phase.STOPPED
        self.async_changed()

    def _detach(self) -> None:
        _LOGGER.debug("%s plays something else; no longer following", self.entity_id)
        self.phase = Phase.IDLE
        self.fingerprint = None
        self.async_changed()

    # ------------------------------------------------------------ persistence

    def snapshot(self) -> dict[str, Any]:
        """Return the state for the panel."""
        return snapshot(self.entity_id, self.queue, self.phase, self.last_error)

    def as_dict(self) -> dict[str, Any]:
        """Return the data to store."""
        phase = self.phase if self.phase in _RESTORED_PHASES else Phase.IDLE
        return {
            **self.queue.as_dict(),
            "phase": phase.value,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(
        cls,
        hass: HomeAssistant,
        entity_id: str,
        data: dict[str, Any],
        on_change: Callable[[QueueController], None],
    ) -> QueueController:
        """Return the controller stored in data."""
        controller = cls(hass, entity_id, on_change, Queue.from_dict(data))
        phase = data.get("phase")
        if phase in {p.value for p in _RESTORED_PHASES}:
            controller.phase = Phase(phase)
        fingerprint = data.get("fingerprint")
        controller.fingerprint = fingerprint if isinstance(fingerprint, str) else None
        return controller


def snapshot(
    entity_id: str,
    queue: Queue,
    phase: Phase,
    last_error: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return what the panel needs to show a queue."""
    upcoming = queue.next_position
    return {
        "entity_id": entity_id,
        "items": [item.as_dict() for item in queue.items],
        "current": queue.current,
        "next": upcoming if upcoming < len(queue.items) else None,
        "phase": phase.value,
        "last_error": last_error,
    }
