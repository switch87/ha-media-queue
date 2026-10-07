"""Tests for the diagnostics."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.media_queue.const import DOMAIN
from custom_components.media_queue.controller import Phase
from custom_components.media_queue.model import Mode

from .common import PLAYER, track


async def test_diagnostics(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Diagnostics summarise each queue; the fingerprint URL is redacted."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = entry.runtime_data.controller(PLAYER)
    controller.queue.add([track("a"), track("b")], Mode.ADD, limit=10)
    controller.queue.set_current(0)
    controller.phase = Phase.PLAYING
    controller.fingerprint = "http://ha/media/a.mp3?authSig=secret"
    entry.runtime_data.controller("media_player.kitchen")

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diagnostics == {
        "queues": {
            PLAYER: {
                "items": 2,
                "current": 0,
                "next": 1,
                "phase": "playing",
                "fingerprint": "**REDACTED**",
            },
            "media_player.kitchen": {
                "items": 0,
                "current": None,
                "next": None,
                "phase": "idle",
                "fingerprint": None,
            },
        }
    }
