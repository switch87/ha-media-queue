"""All queues of the installation, their storage and their subscribers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    PLAYBACK_SAVE_DELAY,
    SAVE_DELAY,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
)
from .controller import Change, Phase, QueueController, snapshot
from .history import ListeningHistory
from .library import PlaylistLibrary
from .model import Queue, Repeat

_LOGGER = logging.getLogger(__name__)

type Subscriber = Callable[[dict[str, Any]], None]
type Closer = Callable[[], None]


def _is_player(entity_id: Any) -> bool:
    return isinstance(entity_id, str) and entity_id.startswith(
        f"{Platform.MEDIA_PLAYER}."
    )


class QueueStore(Store[dict[str, Any]]):
    """The stored queues, migrated from older versions."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: Any
    ) -> dict[str, Any]:
        """Add the 0.2.0 settings to queues stored by 0.1.0."""
        queues = old_data.get("queues") if isinstance(old_data, dict) else None
        if old_minor_version < 2 and isinstance(queues, dict):
            for raw in queues.values():
                if isinstance(raw, dict):
                    raw.setdefault("shuffle", False)
                    raw.setdefault("repeat", Repeat.OFF.value)
        data: dict[str, Any] = old_data
        return data


class QueueManager:
    """Keep one controller per media player and persist them."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the manager; call async_load before use."""
        self.hass = hass
        self._store = QueueStore(
            hass, STORAGE_VERSION, STORAGE_KEY, minor_version=STORAGE_MINOR_VERSION
        )
        self._controllers: dict[str, QueueController] = {}
        self._subscribers: dict[str, list[tuple[Subscriber, Closer | None]]] = {}
        self._unloaded = False
        # Until when a soon save (after a queue edit) is pending.
        self._soon_save_until = dt_util.utcnow()
        self.history = ListeningHistory(hass)
        self.library = PlaylistLibrary(hass, self.history)

    @property
    def entity_ids(self) -> list[str]:
        """Return the players that have a queue."""
        return list(self._controllers)

    async def async_load(self) -> None:
        """Restore the stored queues."""
        await self.history.async_load()
        await self.library.async_load()
        data = await self._store.async_load()
        queues = data.get("queues") if isinstance(data, dict) else None
        if not isinstance(queues, dict):
            return
        for entity_id, raw in queues.items():
            if _is_player(entity_id) and isinstance(raw, dict):
                controller = QueueController.from_dict(
                    self.hass, entity_id, raw, self._changed, history=self.history
                )
                controller.async_start()
                self._controllers[entity_id] = controller

    async def async_unload(self) -> None:
        """Stop following the players, end subscriptions, save now."""
        self._unloaded = True
        for controller in self._controllers.values():
            controller.async_stop()
        for subscribers in self._subscribers.values():
            for _subscriber, on_close in subscribers:
                if on_close is not None:
                    on_close()
        self._subscribers.clear()
        await self._store.async_save(self._data())
        await self.library.async_unload()
        await self.history.async_unload()

    @property
    def subscription_count(self) -> int:
        """Return the number of open subscriptions of all queues."""
        return sum(len(entries) for entries in self._subscribers.values())

    def get(self, entity_id: str) -> QueueController | None:
        """Return the controller of entity_id if it has one."""
        return self._controllers.get(entity_id)

    def controller(self, entity_id: str) -> QueueController:
        """Return the controller of entity_id, creating it."""
        if (existing := self._controllers.get(entity_id)) is not None:
            return existing
        created = QueueController(
            self.hass, entity_id, self._changed, history=self.history
        )
        created.async_start()
        self._controllers[entity_id] = created
        return created

    def existing(self, entity_id: str) -> QueueController:
        """Return the controller of a player that exists or has a queue."""
        if entity_id in self._controllers or self.hass.states.get(entity_id):
            return self.controller(entity_id)
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_player",
            translation_placeholders={"entity_id": entity_id},
        )

    def snapshot(self, entity_id: str) -> dict[str, Any]:
        """Return the panel state of entity_id's queue (empty if none)."""
        if (controller := self._controllers.get(entity_id)) is not None:
            return controller.snapshot()
        return snapshot(entity_id, Queue(), Phase.IDLE)

    @callback
    def subscribe(
        self, entity_id: str, subscriber: Subscriber, on_close: Closer | None = None
    ) -> CALLBACK_TYPE:
        """Call subscriber whenever entity_id's queue changes; on_close at unload."""
        subscribers = self._subscribers.setdefault(entity_id, [])
        entry = (subscriber, on_close)
        subscribers.append(entry)

        @callback
        def unsubscribe() -> None:
            self._drop(entity_id, entry)

        return unsubscribe

    def _drop(self, entity_id: str, entry: tuple[Subscriber, Closer | None]) -> None:
        subscribers = self._subscribers.get(entity_id, [])
        if entry in subscribers:
            subscribers.remove(entry)
        if not subscribers:
            self._subscribers.pop(entity_id, None)

    @callback
    def _changed(self, controller: QueueController, change: Change) -> None:
        if self._unloaded:
            return  # a late change (an advance being cancelled): not ours anymore
        full = change is Change.QUEUE
        data = controller.snapshot() if full else controller.playback()
        for entry in list(self._subscribers.get(controller.entity_id, [])):
            try:
                entry[0](data)
            except Exception:
                # A dead connection must not break the queue or the others.
                _LOGGER.exception(
                    "Dropping a subscriber of %s that failed", controller.entity_id
                )
                self._drop(controller.entity_id, entry)
        now = dt_util.utcnow()
        if full:
            self._store.async_delay_save(self._data, SAVE_DELAY)
            self._soon_save_until = now + timedelta(seconds=SAVE_DELAY)
        elif change is Change.CURRENT and now >= self._soon_save_until:
            # Rescheduling would postpone a pending soon save; it covers this.
            self._store.async_delay_save(self._data, PLAYBACK_SAVE_DELAY)

    def _data(self) -> dict[str, Any]:
        return {
            "queues": {
                entity_id: controller.as_dict()
                for entity_id, controller in self._controllers.items()
                if controller.queue.items
                or controller.phase is not Phase.IDLE
                or controller.queue.shuffle
                or controller.queue.repeat is not Repeat.OFF
            }
        }


def async_get_manager(hass: HomeAssistant) -> QueueManager:
    """Return the manager of the loaded config entry."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    manager: QueueManager = entries[0].runtime_data
    return manager
