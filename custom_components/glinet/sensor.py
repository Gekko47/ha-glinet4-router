from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# =========================================================
# SYSTEM LOGS (SLOW COORDINATOR)
# =========================================================
class GlinetSystemLogsSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, slow_coordinator):
        super().__init__(slow_coordinator)

        self._attr_name = "System Logs"
        self._attr_unique_id = "glinet_system_logs"
        self._attr_translation_key = "system_logs"

    @property
    def state(self):
        logs = (self.coordinator.data or {}).get("logs") or []
        return len(logs)

    @property
    def extra_state_attributes(self):
        logs = (self.coordinator.data or {}).get("logs") or []
        return {
            "last_50": logs[-50:],
            "total": len(logs),
        }


# =========================================================
# SETUP ENTRY
# =========================================================
async def async_setup_entry(hass, entry, async_add_entities):
    """Set up GL.iNet sensors."""

    data = hass.data[DOMAIN][entry.entry_id]

    fast = data["fast_coordinator"]
    slow = data["slow_coordinator"]

    entities: list[SensorEntity] = []

    # =====================================================
    # ROUTER REAL-TIME SENSORS (FAST)
    # =====================================================
    entities.extend(
        [
            GlinetUptimeSensor(fast),
            GlinetRXSensor(fast),
            GlinetTXSensor(fast),
            GlinetCPUTemperatureSensor(fast),
            GlinetMemoryUsageSensor(fast),
            GlinetDiskUsageSensor(fast),
            GlinetFlashUsageSensor(fast),
            GlinetSystemLoadSensor(fast),
            GlinetWanIPSensor(fast),
            GlinetLanIPSensor(fast),
            GlinetConnectedDevicesSensor(fast),
            GlinetUSBSensor(fast),
            GlinetFirmwareVersionSensor(fast),
            GlinetDHCPLeasesSensor(fast),
            GlinetPortForwardingSensor(fast),
        ]
    )

    # logs come from slow coordinator
    entities.append(GlinetSystemLogsSensor(slow))

    async_add_entities(entities)

    # =====================================================
    # CLIENT ENTITIES (FAST COORDINATOR ONLY)
    # =====================================================
    existing_clients: set[str] = set()

    def _add_clients():
        new_entities: list[SensorEntity] = []

        clients_by_mac = (fast.data or {}).get("clients_by_mac", {}) or {}

        for mac in clients_by_mac:
            if mac in existing_clients:
                continue

            existing_clients.add(mac)
            new_entities.append(GlinetClientEntity(fast, mac))

        if new_entities:
            async_add_entities(new_entities)

    _add_clients()


# =========================================================
# BASE SENSORS (FAST)
# =========================================================
class GlinetUptimeSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Router Uptime"
        self._attr_unique_id = "glinet_uptime"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("status", {}).get("uptime")


class GlinetRXSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "WAN Download"
        self._attr_unique_id = "glinet_wan_rx"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("throughput", {}).get("rx")


class GlinetTXSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "WAN Upload"
        self._attr_unique_id = "glinet_wan_tx"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("throughput", {}).get("tx")


class GlinetCPUTemperatureSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "CPU Temperature"
        self._attr_unique_id = "glinet_cpu_temp"
        self._attr_unit_of_measurement = "°C"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("system_info", {}).get("cpu_temp")


class GlinetMemoryUsageSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Memory Usage"
        self._attr_unique_id = "glinet_memory"
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("system_info", {}).get("memory_percent")


class GlinetDiskUsageSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Disk Usage"
        self._attr_unique_id = "glinet_disk"
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("system_info", {}).get("disk_percent")


class GlinetFlashUsageSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Flash Usage"
        self._attr_unique_id = "glinet_flash"
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("system_info", {}).get("flash_percent")


class GlinetSystemLoadSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "System Load"
        self._attr_unique_id = "glinet_load"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("system_info", {}).get("load_average")

    @property
    def extra_state_attributes(self):
        return (self.coordinator.data or {}).get("system_info", {}).get(
            "load_average_detailed", {}
        )


class GlinetWanIPSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "WAN IP"
        self._attr_unique_id = "glinet_wan_ip"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("wan_status", {}).get("ip")


class GlinetLanIPSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "LAN IP"
        self._attr_unique_id = "glinet_lan_ip"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("lan_status", {}).get("ip")


class GlinetConnectedDevicesSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Connected Devices"
        self._attr_unique_id = "glinet_clients_count"

    @property
    def state(self):
        return len((self.coordinator.data or {}).get("clients_by_mac", {}))


class GlinetUSBSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "USB Devices"
        self._attr_unique_id = "glinet_usb"

    @property
    def state(self):
        return len((self.coordinator.data or {}).get("usb_devices") or [])

    @property
    def extra_state_attributes(self):
        return {"devices": (self.coordinator.data or {}).get("usb_devices") or []}


class GlinetFirmwareVersionSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Firmware"
        self._attr_unique_id = "glinet_firmware"

    @property
    def state(self):
        return (self.coordinator.data or {}).get("system_info", {}).get("firmware_version")


class GlinetDHCPLeasesSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "DHCP Leases"
        self._attr_unique_id = "glinet_dhcp"

    @property
    def state(self):
        return len((self.coordinator.data or {}).get("dhcp_leases") or [])

    @property
    def extra_state_attributes(self):
        return {"leases": (self.coordinator.data or {}).get("dhcp_leases") or []}


class GlinetPortForwardingSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Port Forwarding"
        self._attr_unique_id = "glinet_port_forwarding"

    @property
    def state(self):
        return len((self.coordinator.data or {}).get("port_forwarding") or [])

    @property
    def extra_state_attributes(self):
        return {"rules": (self.coordinator.data or {}).get("port_forwarding") or []}


# =========================================================
# CLIENT ENTITY
# =========================================================
class GlinetClientEntity(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, mac: str):
        super().__init__(coordinator)
        self.mac = mac

        self._attr_unique_id = f"glinet_client_{mac}"
        self._attr_name = mac

    @property
    def client(self):
        return (self.coordinator.data or {}).get("clients_by_mac", {}).get(self.mac)

    @property
    def state(self):
        c = self.client
        return c.get("ip") if c else None

    @property
    def extra_state_attributes(self):
        return self.client or {}