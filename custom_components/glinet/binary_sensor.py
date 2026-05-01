from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


# =========================================================
# SETUP ENTRY
# =========================================================
async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]

    fast = data["fast_coordinator"]

    device_id = data.get("device_identifiers") or entry.entry_id

    async_add_entities([
        VPNBinarySensor(
            coordinator=fast,
            device_id=device_id,
        )
    ])


# =========================================================
# VPN BINARY SENSOR
# =========================================================
class VPNBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """VPN connection state."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(coordinator)

        self._attr_name = "VPN Connected"
        self._attr_unique_id = "glinet_vpn_connected"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
        }

    # -----------------------------------------------------
    # STATE
    # -----------------------------------------------------
    @property
    def is_on(self) -> bool:
        vpn = (self.coordinator.data or {}).get("vpn", {}) or {}
        return bool(vpn.get("connected", False))