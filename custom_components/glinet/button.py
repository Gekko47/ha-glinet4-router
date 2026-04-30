from homeassistant.components.button import ButtonEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]
    async_add_entities([
        Reboot(api, device_identifiers),
        UpdateFirmware(api, device_identifiers),
    ])


class Reboot(ButtonEntity):
    def __init__(self, api, device_identifiers):
        self.api = api
        self._attr_name = "Reboot Router"
        self._attr_unique_id = "reboot"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    async def async_press(self):
        await self.api.system.reboot()


class UpdateFirmware(ButtonEntity):
    def __init__(self, api, device_identifiers):
        self.api = api
        self._attr_name = "Update Firmware"
        self._attr_unique_id = "update_firmware"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    async def async_press(self):
        await self.api.system.update_firmware()