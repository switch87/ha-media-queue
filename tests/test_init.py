"""Tests for the config flow, setup, unload and the panel."""

import asyncio
from typing import Any

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    WebSocketGenerator,
)

from custom_components.media_queue.const import DOMAIN, STORAGE_KEY
from custom_components.media_queue.library import PLAYLIST_STORAGE_KEY
from custom_components.media_queue.manager import QueueManager
from custom_components.media_queue.model import Mode

from .common import PLAYER, track


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Media queue", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_creates_one_entry(hass: HomeAssistant) -> None:
    """The user step needs no input; a second instance is refused."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Media queue"
    assert result["data"] == {}
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_setup_registers_the_panel(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """The sidebar gets "Music"; its module is served from a versioned path."""
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, QueueManager)

    panel = hass.data[DATA_PANELS]["media-queue"]
    assert panel.sidebar_title == "Music"
    assert panel.sidebar_icon == "mdi:playlist-music"
    assert panel.require_admin is False
    assert panel.component_name == "custom"
    assert panel.config is not None
    custom: dict[str, Any] = panel.config["_panel_custom"]
    assert custom["name"] == "media-queue-panel"
    assert custom["module_url"] == "/media_queue_frontend/0.3.1/media-queue-panel.js"
    assert custom["embed_iframe"] is False

    client = await hass_client()
    response = await client.get(custom["module_url"])
    assert response.status == 200
    assert "media-queue-panel" in await response.text()


async def test_unload_removes_the_panel_and_saves(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Unloading removes the sidebar entry and writes the queues."""
    entry = await _setup(hass)
    manager: QueueManager = entry.runtime_data
    controller = manager.controller(PLAYER)
    controller.queue.add([track("a")], Mode.ADD, limit=10)
    controller.async_changed()

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "media-queue" not in hass.data[DATA_PANELS]
    assert hass_storage[STORAGE_KEY]["data"]["queues"][PLAYER]["items"]


async def test_dutch_sidebar_title(hass: HomeAssistant) -> None:
    """Dutch installations see "Muziek" in the sidebar."""
    hass.config.language = "nl"
    await _setup(hass)
    assert hass.data[DATA_PANELS]["media-queue"].sidebar_title == "Muziek"


async def test_reload_keeps_the_static_path(hass: HomeAssistant) -> None:
    """A second setup (reload) does not register the static path twice."""
    entry = await _setup(hass)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert "media-queue" in hass.data[DATA_PANELS]


async def test_yaml_is_not_supported(hass: HomeAssistant) -> None:
    """Setting up from configuration.yaml alone creates nothing."""
    assert await async_setup_component(hass, DOMAIN, {})
    assert "media-queue" not in hass.data.get(DATA_PANELS, {})


async def test_removing_the_entry_deletes_the_queues(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Removing the integration leaves no stored queues behind."""
    entry = await _setup(hass)
    controller = entry.runtime_data.controller(PLAYER)
    controller.queue.add([track("a")], Mode.ADD, limit=10)
    controller.async_changed()
    entry.runtime_data.library.save("Mix", [track("a")], overwrite=False)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert STORAGE_KEY not in hass_storage
    assert PLAYLIST_STORAGE_KEY not in hass_storage


async def test_a_yaml_line_is_ignored_with_a_clear_message(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`media_queue:` in configuration.yaml (the Pi tried it) changes nothing.

    Home Assistant logs that YAML is not supported and raises a repair issue;
    the integration still runs once, from its config entry.
    """
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert "does not support YAML setup" in caplog.text
    issues = ir.async_get(hass)
    assert issues.async_get_issue(HOMEASSISTANT_DOMAIN, f"config_entry_only_{DOMAIN}")
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "media_queue/get", "entity_id": PLAYER})
    async with asyncio.timeout(5):
        reply = await client.receive_json()
    assert reply["success"]
