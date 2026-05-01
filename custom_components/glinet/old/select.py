from homeassistant.components.select import SelectEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]

    entities = [
        DNSPrimarySelect(coordinator, device_identifiers),
        DNSSecondarySelect(coordinator, device_identifiers),
    ]

    async_add_entities(entities)


class DNSPrimarySelect(SelectEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Primary DNS Server"
        self._attr_unique_id = "dns_primary"
        self._attr_device_info = {"identifiers": {device_identifiers}}
        self._attr_options = [
            "8.8.8.8", "8.8.4.4", "1.1.1.1", "9.9.9.9", "208.67.222.222"
        ]

    @property
    def current_option(self):
        dns_servers = self.coordinator.data.get("dns_settings", {}).get("servers", [])
        return dns_servers[0] if dns_servers else None

    async def async_select_option(self, option: str):
        """Set the primary DNS server."""
        current_servers = self.coordinator.data.get("dns_settings", {}).get("servers", ["", ""])
        new_servers = [option, current_servers[1] if len(current_servers) > 1 else ""]
        try:
            await self.coordinator.api.async_set_dns_servers(new_servers)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to set primary DNS server: {e}")


class DNSSecondarySelect(SelectEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "Secondary DNS Server"
        self._attr_unique_id = "dns_secondary"
        self._attr_device_info = {"identifiers": {device_identifiers}}
        self._attr_options = [
            "8.8.8.8", "8.8.4.4", "1.1.1.1", "9.9.9.9", "208.67.220.220"
        ]

    @property
    def current_option(self):
        dns_servers = self.coordinator.data.get("dns_settings", {}).get("servers", [])
        return dns_servers[1] if len(dns_servers) > 1 else None

    async def async_select_option(self, option: str):
        """Set the secondary DNS server."""
        current_servers = self.coordinator.data.get("dns_settings", {}).get("servers", ["", ""])
        new_servers = [current_servers[0] if current_servers else "", option]
        try:
            await self.coordinator.api.async_set_dns_servers(new_servers)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to set secondary DNS server: {e}")