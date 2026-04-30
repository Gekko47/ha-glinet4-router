from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIGNAL_CLIENTS_UPDATED


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]
    entities = {}

    base = [
        GlinetUptimeSensor(coordinator, device_identifiers),
        GlinetRXSensor(coordinator, device_identifiers),
        GlinetTXSensor(coordinator, device_identifiers),
        GlinetCPUTemperatureSensor(coordinator, device_identifiers),
        GlinetMemoryUsageSensor(coordinator, device_identifiers),
        GlinetDiskUsageSensor(coordinator, device_identifiers),
        GlinetFlashUsageSensor(coordinator, device_identifiers),
        GlinetSystemLoadSensor(coordinator, device_identifiers),
        GlinetWanIPSensor(coordinator, device_identifiers),
        GlinetLanIPSensor(coordinator, device_identifiers),
        GlinetConnectedDevicesSensor(coordinator, device_identifiers),
        GlinetUSBSensor(coordinator, device_identifiers),
        GlinetFirmwareVersionSensor(coordinator, device_identifiers),
        GlinetDHCPLeasesSensor(coordinator, device_identifiers),
        GlinetPortForwardingSensor(coordinator, device_identifiers),
    ]

    async_add_entities(base)

    def _devices():
        new = []
        for c in coordinator.data["clients"]:
            mac = c.get("mac")
            if mac and mac not in entities:
                rx = ClientRX(coordinator, mac, device_identifiers)
                tx = ClientTX(coordinator, mac, device_identifiers)
                entities[mac] = True
                new.extend([rx, tx])
        if new:
            async_add_entities(new)

    _devices()
    async_dispatcher_connect(hass, SIGNAL_CLIENTS_UPDATED, _devices)


class GlinetUptimeSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Router Uptime"
        self._attr_unique_id = "uptime"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        return self.coordinator.data["status"].get("uptime")


class GlinetRXSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "WAN Download"
        self._attr_unique_id = "wan_rx"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        return self.coordinator.data["throughput"].get("rx")


class GlinetTXSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "WAN Upload"
        self._attr_unique_id = "wan_tx"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        return self.coordinator.data["throughput"].get("tx")


class GlinetCPUTemperatureSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "CPU Temperature"
        self._attr_unique_id = "cpu_temp"
        self._attr_device_info = {"identifiers": {device_identifiers}}
        self._attr_unit_of_measurement = "°C"

    @property
    def state(self):
        return self.coordinator.data.get("system_info", {}).get("cpu_temp")


class GlinetMemoryUsageSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Memory Usage"
        self._attr_unique_id = "memory_usage"
        self._attr_device_info = {"identifiers": {device_identifiers}}
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        return self.coordinator.data.get("system_info", {}).get("memory_percent")


class GlinetDiskUsageSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Disk Usage"
        self._attr_unique_id = "disk_usage"
        self._attr_device_info = {"identifiers": {device_identifiers}}
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        return self.coordinator.data.get("system_info", {}).get("disk_percent")


class GlinetFlashUsageSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Flash Usage"
        self._attr_unique_id = "flash_usage"
        self._attr_device_info = {"identifiers": {device_identifiers}}
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        return self.coordinator.data.get("system_info", {}).get("flash_percent")


class GlinetSystemLoadSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "System Load"
        self._attr_unique_id = "system_load"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        load = self.coordinator.data.get("system_info", {}).get("load_average")
        return load

    @property
    def extra_state_attributes(self):
        load_data = self.coordinator.data.get("system_info", {}).get("load_average_detailed", {})
        return {
            "1min": load_data.get("1min"),
            "5min": load_data.get("5min"),
            "15min": load_data.get("15min"),
        }


class GlinetWanIPSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "WAN IP Address"
        self._attr_unique_id = "wan_ip"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        return self.coordinator.data.get("wan_status", {}).get("ip")


class GlinetLanIPSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "LAN IP Address"
        self._attr_unique_id = "lan_ip"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        return self.coordinator.data.get("lan_status", {}).get("ip")


class GlinetConnectedDevicesSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Connected Devices"
        self._attr_unique_id = "connected_devices"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        return len(self.coordinator.data.get("clients", []))


class GlinetUSBSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "USB Devices"
        self._attr_unique_id = "usb_devices"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        usb_devices = self.coordinator.data.get("usb_devices", [])
        return len(usb_devices)

    @property
    def extra_state_attributes(self):
        return {"devices": self.coordinator.data.get("usb_devices", [])}


class GlinetFirmwareVersionSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Firmware Version"
        self._attr_unique_id = "firmware_version"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        return self.coordinator.data.get("firmware", {}).get("version")


class GlinetDHCPLeasesSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "DHCP Leases"
        self._attr_unique_id = "dhcp_leases"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        leases = self.coordinator.data.get("dhcp_leases", [])
        return len(leases)

    @property
    def extra_state_attributes(self):
        return {"leases": self.coordinator.data.get("dhcp_leases", [])}


class GlinetPortForwardingSensor(SensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Port Forwarding Rules"
        self._attr_unique_id = "port_forwarding"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def state(self):
        rules = self.coordinator.data.get("port_forwarding", [])
        return len(rules)

    @property
    def extra_state_attributes(self):
        return {"rules": self.coordinator.data.get("port_forwarding", [])}


class ClientRX(SensorEntity):
    def __init__(self, coordinator, mac, device_identifiers):
        self.coordinator = coordinator
        self.mac = mac
        self.device_identifiers = device_identifiers
        self._client = None
        self._update_client()

    def _update_client(self):
        self._client = next((c for c in self.coordinator.data["clients"] if c.get("mac") == self.mac), None)
        name = self._client.get("name", self.mac) if self._client else self.mac
        self._attr_name = f"{name} Download"
        self._attr_unique_id = f"{self.mac}_rx"
        self._attr_device_info = {"identifiers": {self.device_identifiers}}

    @property
    def state(self):
        self._update_client()
        return self._client.get("rx") if self._client else None


class ClientTX(SensorEntity):
    def __init__(self, coordinator, mac, device_identifiers):
        self.coordinator = coordinator
        self.mac = mac
        self.device_identifiers = device_identifiers
        self._client = None
        self._update_client()

    def _update_client(self):
        self._client = next((c for c in self.coordinator.data["clients"] if c.get("mac") == self.mac), None)
        name = self._client.get("name", self.mac) if self._client else self.mac
        self._attr_name = f"{name} Upload"
        self._attr_unique_id = f"{self.mac}_tx"
        self._attr_device_info = {"identifiers": {self.device_identifiers}}

    @property
    def state(self):
        self._update_client()
        return self._client.get("tx") if self._client else None