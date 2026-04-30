from homeassistant.components.number import NumberEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]

    entities = [
        DHCPLeaseTimeNumber(coordinator, device_identifiers),
    ]

    async_add_entities(entities)


class DHCPLeaseTimeNumber(NumberEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "DHCP Lease Time (hours)"
        self._attr_unique_id = "dhcp_lease_time"
        self._attr_device_info = {"identifiers": {device_identifiers}}
        self._attr_min_value = 1
        self._attr_max_value = 168  # 1 week
        self._attr_step = 1

    @property
    def value(self):
        return self.coordinator.data.get("dhcp_settings", {}).get("lease_time", 24)

    async def async_set_value(self, value: float):
        """Set the DHCP lease time in hours."""
        try:
            config = {"lease_time": int(value)}
            await self.coordinator.api.async_set_dhcp_settings(config)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to set DHCP lease time: {e}")