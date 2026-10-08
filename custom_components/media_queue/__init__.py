"""Media queue for Home Assistant: a queue per media player and a "Muziek" panel."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from . import panel, services, websocket
from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .history import HISTORY_STORAGE_KEY, HISTORY_STORAGE_VERSION
from .library import PLAYLIST_STORAGE_KEY, PLAYLIST_STORAGE_VERSION
from .manager import QueueManager

type MediaQueueConfigEntry = ConfigEntry[QueueManager]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the API (it needs a loaded entry to do anything)."""
    websocket.async_register(hass)
    services.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MediaQueueConfigEntry) -> bool:
    """Load the queues and show the panel."""
    manager = QueueManager(hass)
    await manager.async_load()
    entry.runtime_data = manager
    await panel.async_register(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MediaQueueConfigEntry) -> bool:
    """Remove the panel and save the queues."""
    panel.async_unregister(hass)
    await entry.runtime_data.async_unload()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: MediaQueueConfigEntry) -> None:
    """Delete the stored queues, playlists and history at removal."""
    await Store[dict[str, object]](hass, STORAGE_VERSION, STORAGE_KEY).async_remove()
    await Store[dict[str, object]](
        hass, PLAYLIST_STORAGE_VERSION, PLAYLIST_STORAGE_KEY
    ).async_remove()
    await Store[dict[str, object]](
        hass, HISTORY_STORAGE_VERSION, HISTORY_STORAGE_KEY
    ).async_remove()
