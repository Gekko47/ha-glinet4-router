from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# =========================================================
# SETUP ENTRY
# =========================================================
async def async_setup_entry(hass, entry, async_add_entities):
    """Set up GL.iNet buttons."""

    data = hass.data[DOMAIN][entry.entry_id]

    api = data["api"]
    fast = data["fast_coordinator"]

    system = (fast.data or {}).get("system_info", {}) or {}
    device_id = system.get("mac") or entry.entry_id

    async_add_entities([
        GlinetRebootButton(api, fast, device_id)
    ])


# =========================================================
# REBOOT BUTTON
# =========================================================
class GlinetRebootButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, api, coordinator, device_id: str):
        super().__init__(coordinator)

        self.api = api

        self._attr_name = "Reboot Router"
        self._attr_unique_id = "glinet_reboot"
        self._attr_entity_category = EntityCategory.CONFIG

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)}
        }

    # =====================================================
    # ACTION
    # =====================================================
    async def async_press(self):
        """Reboot router safely."""
        try:
            await self.api.async_reboot()

        except Exception as e:
            _LOGGER.error("Router reboot failed: %s", e)
            return

        # router may drop connection temporarily
        await self.coordinator.async_request_refresh()

    # =====================================================
    # AVAILABILITY (ROBUST)
    # =====================================================
    @property
    def available(self) -> bool:
        """Always available unless integration is broken."""
        return self.coordinator is not None