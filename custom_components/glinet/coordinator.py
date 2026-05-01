from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import SCAN_INTERVAL, SIGNAL_CLIENTS_UPDATED

_LOGGER = logging.getLogger(__name__)


class GlinetCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api):
        super().__init__(
            hass,
            _LOGGER,
            name="glinet",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self._known_clients = set()

    async def _async_update_data(self):
        data = {}
        try:
            data["status"] = await self.api.router_get_status()
        except Exception:
            data["status"] = {}

        try:
            clients_resp = await self.api.list_all_clients()
            data["clients"] = clients_resp.get("clients", []) if isinstance(clients_resp, dict) else []
        except Exception:
            data["clients"] = []

        try:
            data["throughput"] = await self.api.router_get_load()
        except Exception:
            data["throughput"] = {}

        data["vpn"] = {}

        try:
            wifi_ifaces = await self.api.wifi_ifaces_get()
            if isinstance(wifi_ifaces, dict):
                data["wifi"] = {"interfaces": list(wifi_ifaces.values())}
            else:
                data["wifi"] = {"interfaces": []}
        except Exception:
            data["wifi"] = {"interfaces": []}

        try:
            data["system_info"] = await self.api.router_info()
        except Exception:
            data["system_info"] = {}

        try:
            data["wan_status"] = await self.api.connected_to_internet()
        except Exception:
            data["wan_status"] = {}

        data["dhcp_leases"] = []
        data["port_forwarding"] = []
        data["lan_status"] = {}
        data["dns_settings"] = {}
        data["usb_devices"] = []
        data["logs"] = []
        data["firmware"] = {"version": data.get("system_info", {}).get("firmware_version")}

        macs = {c.get("mac") for c in data["clients"] if c.get("mac")}

        if macs != self._known_clients:
            self._known_clients = macs
            async_dispatcher_send(self.hass, SIGNAL_CLIENTS_UPDATED)

        return data