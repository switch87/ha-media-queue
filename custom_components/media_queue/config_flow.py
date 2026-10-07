"""Config flow for the media queue: one instance, nothing to configure."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class MediaQueueConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the media queue (the manifest allows a single entry)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the integration."""
        if user_input is not None:
            return self.async_create_entry(title="Media queue", data={})
        return self.async_show_form(step_id="user")
