"""Media queue for Home Assistant: a queue per media player and a "Muziek" panel."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import panel
from .const import DOMAIN
from .manager import QueueManager

type MediaQueueConfigEntry = ConfigEntry[QueueManager]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (the API needs a loaded entry to do anything)."""
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
