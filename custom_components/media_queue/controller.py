"""The queue controller of one media player."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .model import Queue


class Phase(StrEnum):
    """How far the controller follows the player."""

    IDLE = "idle"
    STARTING = "starting"
    PLAYING = "playing"
    STOPPED = "stopped"


# A play in progress at shutdown is not resumed: it may never have started.
_RESTORED_PHASES = {Phase.PLAYING, Phase.STOPPED}


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

    @callback
    def async_changed(self) -> None:
        """Tell the manager that the queue or phase changed."""
        self._on_change(self)

    def snapshot(self) -> dict[str, Any]:
        """Return the state for the panel."""
        return snapshot(self.entity_id, self.queue, self.phase)

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


def snapshot(entity_id: str, queue: Queue, phase: Phase) -> dict[str, Any]:
    """Return what the panel needs to show a queue."""
    upcoming = queue.next_position
    return {
        "entity_id": entity_id,
        "items": [item.as_dict() for item in queue.items],
        "current": queue.current,
        "next": upcoming if upcoming < len(queue.items) else None,
        "phase": phase.value,
    }
