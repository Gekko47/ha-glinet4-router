from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]

    interfaces = [
        iface.get("name")
        for iface in coordinator.data["wifi"].get("interfaces", [])
        if iface.get("name")
    ]

    entities = [
        GlinetWifiSwitch(api, coordinator, name, device_identifiers)
        for name in interfaces
    ]

    if any(iface.get("guest") for iface in coordinator.data["wifi"].get("interfaces", [])):
        entities.append(GlinetGuestNetworkSwitch(api, coordinator, device_identifiers))

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
        await self.api.wifi_iface_set_enabled(self.name, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.api.wifi_iface_set_enabled(self.name, False)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        return self._iface()



class GlinetGuestNetworkSwitch(SwitchEntity):
    def __init__(self, api, coordinator, device_identifiers):
        self.api = api
        self.coordinator = coordinator
        self._attr_name = "Guest Network"
        self._attr_unique_id = "guest_network"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    def _guest_iface(self):
        return next(
            (
                iface
                for iface in self.coordinator.data["wifi"].get("interfaces", [])
                if iface.get("guest")
            ),
            None,
        )

    @property
    def is_on(self):
        iface = self._guest_iface()
        return iface.get("enabled", False) if iface else False

    @property
    def extra_state_attributes(self):
        return self._guest_iface() or {}

    async def async_turn_on(self):
        iface = self._guest_iface()
        if not iface or not iface.get("name"):
            raise ValueError("No guest WiFi interface available")
        await self.api.wifi_iface_set_enabled(iface["name"], True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        iface = self._guest_iface()
        if not iface or not iface.get("name"):
            raise ValueError("No guest WiFi interface available")
        await self.api.wifi_iface_set_enabled(iface["name"], False)
        await self.coordinator.async_request_refresh()