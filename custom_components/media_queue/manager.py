"""All queues of the installation, their storage and their subscribers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import SAVE_DELAY, STORAGE_KEY, STORAGE_VERSION
from .controller import Phase, QueueController, snapshot
from .model import Queue

type Subscriber = Callable[[dict[str, Any]], None]


def _is_player(entity_id: Any) -> bool:
    return isinstance(entity_id, str) and entity_id.startswith(
        f"{Platform.MEDIA_PLAYER}."
    )


class QueueManager:
    """Keep one controller per media player and persist them."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the manager; call async_load before use."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._controllers: dict[str, QueueController] = {}
        self._subscribers: dict[str, list[Subscriber]] = {}

    @property
    def entity_ids(self) -> list[str]:
        """Return the players that have a queue."""
        return list(self._controllers)

    async def async_load(self) -> None:
        """Restore the stored queues."""
        data = await self._store.async_load() or {}
        queues = data.get("queues")
        if not isinstance(queues, dict):
            return
        for entity_id, raw in queues.items():
            if _is_player(entity_id) and isinstance(raw, dict):
                controller = QueueController.from_dict(
                    self.hass, entity_id, raw, self._changed
                )
                controller.async_start()
                self._controllers[entity_id] = controller

    async def async_unload(self) -> None:
        """Stop following the players and write pending changes now."""
        for controller in self._controllers.values():
            controller.async_stop()
        await self._store.async_save(self._data())

    def get(self, entity_id: str) -> QueueController | None:
        """Return the controller of entity_id if it has one."""
        return self._controllers.get(entity_id)

    def controller(self, entity_id: str) -> QueueController:
        """Return the controller of entity_id, creating it."""
        if (existing := self._controllers.get(entity_id)) is not None:
            return existing
        created = QueueController(self.hass, entity_id, self._changed)
        created.async_start()
        self._controllers[entity_id] = created
        return created

    def snapshot(self, entity_id: str) -> dict[str, Any]:
        """Return the panel state of entity_id's queue (empty if none)."""
        if (controller := self._controllers.get(entity_id)) is not None:
            return controller.snapshot()
        return snapshot(entity_id, Queue(), Phase.IDLE)

    @callback
    def subscribe(self, entity_id: str, subscriber: Subscriber) -> CALLBACK_TYPE:
        """Call subscriber with a snapshot whenever entity_id's queue changes."""
        subscribers = self._subscribers.setdefault(entity_id, [])
        subscribers.append(subscriber)

        @callback
        def unsubscribe() -> None:
            if subscriber in subscribers:
                subscribers.remove(subscriber)

        return unsubscribe

    @callback
    def _changed(self, controller: QueueController) -> None:
        data = controller.snapshot()
        for subscriber in list(self._subscribers.get(controller.entity_id, [])):
            subscriber(data)
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def _data(self) -> dict[str, Any]:
        return {
            "queues": {
                entity_id: controller.as_dict()
                for entity_id, controller in self._controllers.items()
                if controller.queue.items or controller.phase is not Phase.IDLE
            }
        }
