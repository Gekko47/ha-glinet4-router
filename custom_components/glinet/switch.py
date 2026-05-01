from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


# =========================================================
# SETUP ENTRY
# =========================================================
async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]

    api = data["api"]
    fast = data["fast_coordinator"]

    system = (fast.data or {}).get("system_info", {}) or {}
    device_id = system.get("mac", entry.entry_id)

    entities: list[SwitchEntity] = []

    # -------------------------
    # WIFI SWITCHES
    # -------------------------
    wifi_by_name = (fast.data or {}).get("wifi_by_name", {}) or {}

    for name in wifi_by_name.keys():
        entities.append(
            GlinetWifiSwitch(
                api=api,
                coordinator=fast,
                name=name,
                device_id=device_id,
            )
        )

    # -------------------------
    # VPN SWITCH (SINGLE ONLY)
    # -------------------------
    entities.append(
        GlinetVpnSwitch(
            api=api,
            coordinator=fast,
            device_id=device_id,
        )
    )

    async_add_entities(entities)


# =========================================================
# WIFI SWITCH
# =========================================================
class GlinetWifiSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, api, coordinator, name: str, device_id: str):
        super().__init__(coordinator)

        self.api = api
        self.name = name

        self._attr_name = f"WiFi {name}"
        self._attr_unique_id = f"glinet_wifi_{name}"
        self._attr_device_info = {"identifiers": {(DOMAIN, device_id)}}

    # -------------------------
    # SAFE ACCESSOR
    # -------------------------
    @property
    def _iface(self):
        return (
            (self.coordinator.data or {})
            .get("wifi_by_name", {})
            .get(self.name, {})
        )

    # -------------------------
    # STATE
    # -------------------------
    @property
    def is_on(self) -> bool:
        return bool(self._iface.get("enabled", False))

    # -------------------------
    # ATTRIBUTES
    # -------------------------
    @property
    def extra_state_attributes(self):
        return {
            "ssid": self._iface.get("ssid"),
            "band": self._iface.get("band"),
            "channel": self._iface.get("channel"),
            "hidden": self._iface.get("hidden"),
            "guest": self._iface.get("guest"),
            "interface_name": self.name,
            "signal": self._iface.get("signal"),
            "connected_clients": self._count_clients(),
        }

    def _count_clients(self) -> int:
        clients = (self.coordinator.data or {}).get("clients_by_mac", {}) or {}

        return sum(
            1
            for c in clients.values()
            if c.get("interface") == self.name and c.get("connected")
        )

    # -------------------------
    # ACTIONS
    # -------------------------
    async def async_turn_on(self):
        await self.api.async_set_wifi(self.name, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.api.async_set_wifi(self.name, False)
        await self.coordinator.async_request_refresh()


# =========================================================
# VPN SWITCH (FIXED - SINGLE ENTITY ONLY)
# =========================================================
class GlinetVpnSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, api, coordinator, device_id: str):
        super().__init__(coordinator)

        self.api = api

        self._attr_name = "VPN"
        self._attr_unique_id = "glinet_vpn"
        self._attr_device_info = {"identifiers": {(DOMAIN, device_id)}}

    # -------------------------
    # SAFE ACCESSOR
    # -------------------------
    @property
    def _vpn(self):
        return (self.coordinator.data or {}).get("vpn", {}) or {}

    # -------------------------
    # STATE
    # -------------------------
    @property
    def is_on(self) -> bool:
        return bool(self._vpn.get("connected", False))

    # -------------------------
    # ATTRIBUTES
    # -------------------------
    @property
    def extra_state_attributes(self):
        return {
            "type": self._vpn.get("type"),
            "server": self._vpn.get("server"),
            "status": self._vpn.get("status"),
            "uptime": self._vpn.get("uptime"),
            "connected": self._vpn.get("connected"),
            "last_update_ok": self.coordinator.last_update_success,
        }

    # -------------------------
    # ACTIONS
    # -------------------------
    async def async_turn_on(self):
        await self.api.async_set_vpn(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.api.async_set_vpn(False)
        await self.coordinator.async_request_refresh()