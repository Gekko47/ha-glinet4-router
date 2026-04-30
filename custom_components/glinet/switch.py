from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]

    entities = [
        GlinetWifiSwitch(api, coordinator, i["name"], device_identifiers)
        for i in coordinator.data["wifi"].get("interfaces", [])
    ]
    entities.extend([
        GlinetVPNSwitch(api, coordinator, device_identifiers),
        GlinetLEDControlSwitch(api, coordinator, device_identifiers),
        GlinetGuestNetworkSwitch(api, coordinator, device_identifiers),
    ])

    async_add_entities(entities)


class GlinetWifiSwitch(SwitchEntity):
    def __init__(self, api, coordinator, name, device_identifiers):
        self.api = api
        self.coordinator = coordinator
        self.name = name
        self._attr_name = f"WiFi {name}"
        self._attr_unique_id = f"wifi_{name}"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    def _iface(self):
        for i in self.coordinator.data["wifi"].get("interfaces", []):
            if i.get("name") == self.name:
                return i
        return {}

    @property
    def is_on(self):
        return self._iface().get("enabled", False)

    async def async_turn_on(self):
        await self.api.async_set_wifi(self.name, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.api.async_set_wifi(self.name, False)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        return self._iface()


class GlinetVPNSwitch(SwitchEntity):
    def __init__(self, api, coordinator, device_identifiers):
        self.api = api
        self.coordinator = coordinator
        self._attr_name = "VPN"
        self._attr_unique_id = "vpn"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def is_on(self):
        return self.coordinator.data["vpn"].get("connected", False)

    async def async_turn_on(self):
        await self.api.async_set_vpn(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.api.async_set_vpn(False)
        await self.coordinator.async_request_refresh()


class GlinetLEDControlSwitch(SwitchEntity):
    def __init__(self, api, coordinator, device_identifiers):
        self.api = api
        self.coordinator = coordinator
        self._attr_name = "LED Control"
        self._attr_unique_id = "led_control"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def is_on(self):
        return self.coordinator.data.get("system_info", {}).get("led_enabled", True)

    async def async_turn_on(self):
        await self.api.async_set_led(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.api.async_set_led(False)
        await self.coordinator.async_request_refresh()


class GlinetGuestNetworkSwitch(SwitchEntity):
    def __init__(self, api, coordinator, device_identifiers):
        self.api = api
        self.coordinator = coordinator
        self._attr_name = "Guest Network"
        self._attr_unique_id = "guest_network"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def is_on(self):
        return self.coordinator.data.get("wifi", {}).get("guest_enabled", False)

    async def async_turn_on(self):
        await self.api.async_set_guest_network(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.api.async_set_guest_network(False)
        await self.coordinator.async_request_refresh()