"""The "Muziek" sidebar panel: static files and panel registration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

PANEL_PATH = "media-queue"
ELEMENT = "media-queue-panel"
# The sidebar title is not translated by HA for custom panels: pick it here.
SIDEBAR_TITLES = {"nl": "Muziek"}
SIDEBAR_TITLE = "Music"
SIDEBAR_ICON = "mdi:playlist-music"
URL_BASE = f"/{DOMAIN}_frontend"
FRONTEND_DIR = Path(__file__).parent / "frontend"

_STATIC_REGISTERED: HassKey[str] = HassKey(f"{DOMAIN}_static")


async def async_register(hass: HomeAssistant) -> None:
    """Serve the frontend files and add the panel to the sidebar."""
    version = (await async_get_integration(hass, DOMAIN)).version
    # The version is part of the path, so browsers fetch new modules (also the
    # ones imported relatively) after an update.
    url = f"{URL_BASE}/{version}"
    if hass.data.get(_STATIC_REGISTERED) != url:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(url, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[_STATIC_REGISTERED] = url
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name=ELEMENT,
        sidebar_title=SIDEBAR_TITLES.get(
            hass.config.language.split("-")[0], SIDEBAR_TITLE
        ),
        sidebar_icon=SIDEBAR_ICON,
        module_url=f"{url}/{ELEMENT}.js",
        require_admin=False,
    )


@callback
def async_unregister(hass: HomeAssistant) -> None:
    """Remove the panel from the sidebar."""
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
