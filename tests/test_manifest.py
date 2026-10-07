"""Tests for the integration manifest."""

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from custom_components.media_queue.const import DOMAIN


async def test_manifest(hass: HomeAssistant) -> None:
    """The manifest describes a local push service with a config flow."""
    integration = await async_get_integration(hass, DOMAIN)

    assert str(integration.version) == "0.2.0"
    assert integration.config_flow is True
    assert integration.iot_class == "calculated"
    assert integration.manifest["single_config_entry"] is True
    assert integration.requirements == ["mutagen==1.48.1"]  # as HA core (tts)
    assert set(integration.dependencies) >= {
        "frontend",
        "http",
        "media_player",
        "media_source",
        "panel_custom",
        "websocket_api",
    }
