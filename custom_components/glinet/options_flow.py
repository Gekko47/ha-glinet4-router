"""GL.iNet options flow for reconfigurable settings."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Defaults for update intervals (seconds)
DEFAULT_FAST_INTERVAL = 30
DEFAULT_SLOW_INTERVAL = 300
DEFAULT_TIMEOUT = 10


class GlinetOptionsFlow(config_entries.OptionsFlow):
    """Handle GL.iNet options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage GL.iNet options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options or {}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "fast_interval",
                        default=options.get("fast_interval", DEFAULT_FAST_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=10, max=300),
                    ),
                    vol.Optional(
                        "slow_interval",
                        default=options.get("slow_interval", DEFAULT_SLOW_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=30, max=3600),
                    ),
                    vol.Optional(
                        "timeout",
                        default=options.get("timeout", DEFAULT_TIMEOUT),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=5, max=60),
                    ),
                }
            ),
        )


async def async_setup_options_flow(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> bool:
    """Set up the options flow."""
    config_entry.async_on_unload(
        config_entry.add_update_listener(async_update_options)
    )
    return True


async def async_update_options(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
