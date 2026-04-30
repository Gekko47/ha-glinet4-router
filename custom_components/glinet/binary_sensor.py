from homeassistant.components.binary_sensor import BinarySensorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]
    async_add_entities([VPN(coordinator, device_identifiers)])


class VPN(BinarySensorEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "VPN Connected"
        self._attr_unique_id = "vpn_connected"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def is_on(self):
        return self.coordinator.data["vpn"].get("connected", False)