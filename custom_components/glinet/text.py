from homeassistant.components.text import TextEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]

    entities = [
        SystemLogsText(coordinator, device_identifiers),
    ]

    async_add_entities(entities)


class SystemLogsText(TextEntity):
    def __init__(self, coordinator, device_identifiers):
        self.coordinator = coordinator
        self._attr_name = "System Logs"
        self._attr_unique_id = "system_logs"
        self._attr_device_info = {"identifiers": {device_identifiers}}

    @property
    def native_value(self):
        logs = self.coordinator.data.get("logs", [])
        return "\n".join(logs[-50:])  # Last 50 log entries