from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# =========================================================
# SERVICE SCHEMAS (HA 2026 BEST PRACTICE)
# =========================================================
SERVICE_REBOOT_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): str,
    }
)


# =========================================================
# SERVICE SETUP
# =========================================================
async def async_setup_services(hass: HomeAssistant) -> None:
    """Register GL.iNet services."""

    async def _get_entry_api(entry_id: str):
        """Safely resolve API from hass.data."""

        domain_data: dict[str, Any] = hass.data.get(DOMAIN, {})

        if not isinstance(domain_data, dict):
            raise HomeAssistantError("GL.iNet integration not loaded")

        entry_data = domain_data.get(entry_id)
        if not entry_data:
            raise HomeAssistantError(f"Config entry '{entry_id}' not found")

        api = entry_data.get("api")
        if not api:
            raise HomeAssistantError(f"API not available for entry '{entry_id}'")

        return api

    # =====================================================
    # REBOOT ROUTER SERVICE
    # =====================================================
    async def reboot_router(call: ServiceCall) -> None:
        """Reboot router via config entry."""

        entry_id = call.data.get("entry_id")

        if not entry_id:
            raise HomeAssistantError("Missing required field: entry_id")

        api = await _get_entry_api(entry_id)

        try:
            _LOGGER.info("Rebooting GL.iNet router (%s)", entry_id)
            await api.async_reboot()

        except Exception as err:
            _LOGGER.exception("Router reboot failed")
            raise HomeAssistantError(f"Router reboot failed: {err}") from err

    # =====================================================
    # REGISTER SERVICE
    # =====================================================
    hass.services.async_register(
        DOMAIN,
        "reboot_router",
        reboot_router,
        schema=SERVICE_REBOOT_SCHEMA,
    )


# =========================================================
# CLEANUP
# =========================================================
async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload GL.iNet services."""

    hass.services.async_remove(DOMAIN, "reboot_router")