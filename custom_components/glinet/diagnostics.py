"""Diagnostics support for GL.iNet integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry.entry_id, {})

    api = entry_data.get("api")
    auth = entry_data.get("auth")
    fast_coord = entry_data.get("fast_coordinator")
    slow_coord = entry_data.get("slow_coordinator")

    diag_data = {
        "config_entry": {
            "data": {
                "host": entry.data.get("host"),
                # Don't expose credentials
                "username": "***",
                "password": "***",
            },
            "version": entry.version,
        },
        "api_state": {
            "session_valid": api.is_logged_in() if api else None,
            "sid_exists": bool(api.sid) if api else None,
        },
        "auth_state": {
            "username_set": bool(auth.username) if auth else None,
            "credentials_valid": bool(auth.username and auth.password) if auth else None,
        },
        "coordinators": {
            "fast": {
                "name": fast_coord.name if fast_coord else None,
                "last_update_success": fast_coord.last_update_success if fast_coord else None,
                "update_interval": (
                    str(fast_coord.update_interval) if fast_coord else None
                ),
                "data_keys": list(fast_coord.data.keys()) if fast_coord and fast_coord.data else [],
            },
            "slow": {
                "name": slow_coord.name if slow_coord else None,
                "last_update_success": slow_coord.last_update_success if slow_coord else None,
                "update_interval": (
                    str(slow_coord.update_interval) if slow_coord else None
                ),
                "data_keys": list(slow_coord.data.keys()) if slow_coord and slow_coord.data else [],
            },
        },
        "system_info": (fast_coord.data or {}).get("system_info", {})
        if fast_coord
        else {},
    }

    return diag_data
