from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIGNAL_CLIENTS_UPDATED


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_identifiers = hass.data[DOMAIN][entry.entry_id]["device_identifiers"]
    entities = {}

    def _update():
        new = []
        for c in coordinator.data["clients"]:
            mac = c.get("mac")
            if mac and mac not in entities:
                e = GlinetDeviceTracker(coordinator, mac, device_identifiers)
                entities[mac] = e
                new.append(e)
        if new:
            async_add_entities(new)

    _update()
    async_dispatcher_connect(hass, SIGNAL_CLIENTS_UPDATED, _update)


class GlinetDeviceTracker(ScannerEntity):
    def __init__(self, coordinator, mac, device_identifiers):
        self.coordinator = coordinator
        self._mac = mac
        self.device_identifiers = device_identifiers

    def _client(self):
        return next((c for c in self.coordinator.data["clients"] if c.get("mac") == self._mac), None)

    @property
    def name(self):
        c = self._client()
        return c.get("name") if c else self._mac

    @property
    def unique_id(self):
        return self._mac

    @property
    def is_connected(self):
        return self._client() is not None

    @property
    def source_type(self):
        return "router"

    @property
    def extra_state_attributes(self):
        c = self._client()
        return c or {}