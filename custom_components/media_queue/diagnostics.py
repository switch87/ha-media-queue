"""Diagnostics for the media queue."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import MediaQueueConfigEntry

# The fingerprint is the player's media URL, which may carry a signed token.
TO_REDACT = {"fingerprint"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MediaQueueConfigEntry
) -> dict[str, Any]:
    """Return a summary of every queue."""
    manager = entry.runtime_data
    queues: dict[str, Any] = {}
    for entity_id in manager.entity_ids:
        controller = manager.controller(entity_id)
        data = controller.snapshot()
        queues[entity_id] = async_redact_data(
            {
                "items": len(data["items"]),
                "current": data["current"],
                "next": data["next"],
                "shuffle": data["shuffle"],
                "repeat": data["repeat"],
                "phase": data["phase"],
                "fingerprint": controller.fingerprint,
            },
            TO_REDACT,
        )
    library = manager.library
    # Counts only: playlist names are the user's own words.
    history = manager.history
    return {
        "queues": queues,
        "playlists": {"count": library.count, "items": library.item_count},
        # Counts only: what someone listens to is personal.
        "history": {"tracks": history.track_count, "plays": history.play_count},
        # Open panels (and other subscribers) following a queue.
        "subscriptions": manager.subscription_count,
    }
