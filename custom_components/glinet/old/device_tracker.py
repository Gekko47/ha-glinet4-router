from __future__ import annotations

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up device tracker entities."""

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities(
        [
            GlinetDeviceTracker(coordinator, c.get("mac"))
            for c in coordinator.data.get("clients", [])
            if c.get("mac")
        ]
    )


class GlinetDeviceTracker(CoordinatorEntity, TrackerEntity):
    """Track GL.iNet connected clients."""

    def __init__(self, coordinator, mac: str):
        super().__init__(coordinator)
        self._mac = mac.lower().strip()

    # ----------------------------------------------------
    # CLIENT RESOLUTION (O(1) lookup via coordinator cache)
    # ----------------------------------------------------
    @property
    def _client(self) -> dict | None:
        return self.coordinator._clients_by_mac.get(self._mac)

    # ----------------------------------------------------
    # IDENTITY
    # ----------------------------------------------------
    @property
    def unique_id(self):
        return self._mac

    @property
    def name(self):
        client = self._client
        if not client:
            return self._mac
        return client.get("name") or client.get("hostname") or self._mac

    @property
    def source_type(self):
        return "router"

    # ----------------------------------------------------
    # STATE
    # ----------------------------------------------------
    @property
    def is_connected(self):
        return self._client is not None

    @property
    def location_name(self):
        client = self._client
        if not client:
            return None
        return client.get("interface") or "router"

    # ----------------------------------------------------
    # ATTRIBUTES (SAFE COPY ONLY)
    # ----------------------------------------------------
    @property
    def extra_state_attributes(self):
        client = self._client
        if not client:
            return {}

        # return safe copy (important HA rule)
        return {
            "mac": client.get("mac"),
            "ip": client.get("ip"),
            "hostname": client.get("hostname"),
            "name": client.get("name"),
            "interface": client.get("interface"),
            "connected": client.get("connected"),
            "rx": client.get("rx"),
            "tx": client.get("tx"),
            "last_seen": client.get("last_seen"),
        }

    # ----------------------------------------------------
    # DEVICE INFO (IMPORTANT FOR HA UI GROUPING)
    # ----------------------------------------------------
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._mac)},
            "name": self.name,
            "manufacturer": "GL.iNet",
            "model": "Client Device",
        }