from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import SCAN_INTERVAL, SIGNAL_CLIENTS_UPDATED


class GlinetCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api):
        super().__init__(
            hass,
            logger=None,
            name="glinet",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self._known_clients = set()

    async def _async_update_data(self):
        data = {}
        try:
            data["status"] = await self.api.async_get_status()
        except Exception:
            data["status"] = {}

        try:
            data["clients"] = await self.api.async_get_clients()
        except Exception:
            data["clients"] = []

        try:
            data["throughput"] = await self.api.async_get_throughput()
        except Exception:
            data["throughput"] = {}

        try:
            data["vpn"] = await self.api.async_get_vpn_status()
        except Exception:
            data["vpn"] = {}

        try:
            data["wifi"] = await self.api.async_get_wifi()
        except Exception:
            data["wifi"] = {"interfaces": []}

        # NEW: Additional data sources
        try:
            data["system_info"] = await self.api.async_get_system_info()
        except Exception:
            data["system_info"] = {}

        try:
            data["dhcp_leases"] = await self.api.async_get_dhcp_leases()
        except Exception:
            data["dhcp_leases"] = []

        try:
            data["port_forwarding"] = await self.api.async_get_port_forwarding()
        except Exception:
            data["port_forwarding"] = []

        try:
            data["wan_status"] = await self.api.async_get_wan_status()
        except Exception:
            data["wan_status"] = {}

        try:
            data["lan_status"] = await self.api.async_get_lan_status()
        except Exception:
            data["lan_status"] = {}

        try:
            data["dns_settings"] = await self.api.async_get_dns_settings()
        except Exception:
            data["dns_settings"] = {}

        try:
            data["usb_devices"] = await self.api.async_get_usb_devices()
        except Exception:
            data["usb_devices"] = []

        try:
            data["logs"] = await self.api.async_get_logs()
        except Exception:
            data["logs"] = []

        try:
            data["firmware"] = await self.api.async_get_firmware_status()
        except Exception:
            data["firmware"] = {}

        macs = {c.get("mac") for c in data["clients"] if c.get("mac")}

        if macs != self._known_clients:
            self._known_clients = macs
            async_dispatcher_send(self.hass, SIGNAL_CLIENTS_UPDATED)

        return data