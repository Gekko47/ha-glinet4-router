from __future__ import annotations

import logging

from gli4py import GLinet
from aiohttp import ClientError

_LOGGER = logging.getLogger(__name__)


class GlinetAPI:
    """HA-friendly wrapper around gli4py."""

    def __init__(self, host: str, username: str, password: str):
        self.host = host
        self.username = username
        self.password = password

        self.client = GLinet(host)

        self._logged_in = False

    # =====================================================
    # SESSION MANAGEMENT (REQUIRED FOR STABILITY)
    # =====================================================
    async def ensure_logged_in(self):
        """Ensure session is active (safe to call every cycle)."""
        if not self._logged_in:
            await self.async_connect()

    async def async_connect(self):
        try:
            await self.client.login(self.username, self.password)
            self._logged_in = True
        except Exception as e:
            self._logged_in = False
            raise ClientError(f"login failed: {e}") from e

    async def async_close(self):
        try:
            await self.client.close()
        except Exception:
            pass

    # =====================================================
    # INTERNAL SAFE CALL WRAPPER
    # =====================================================
    async def _safe_call(self, coro):
        try:
            await self.ensure_logged_in()
            return await coro
        except Exception as e:
            _LOGGER.debug("API call failed, retrying login: %s", e)

            self._logged_in = False
            await self.ensure_logged_in()

            return await coro

    # =====================================================
    # STATUS
    # =====================================================
    async def async_get_status(self):
        return await self._safe_call(self.client.system.status())

    async def async_get_system_info(self):
        return await self._safe_call(self.client.system.info())

    # =====================================================
    # CLIENTS
    # =====================================================
    async def async_get_clients(self):
        return await self._safe_call(self.client.clients.list())

    # =====================================================
    # NETWORK
    # =====================================================
    async def async_get_throughput(self):
        return await self._safe_call(self.client.system.realtime())

    async def async_get_wifi(self):
        return await self._safe_call(self.client.wifi.status())

    async def async_get_wan_status(self):
        return await self._safe_call(self.client.network.wan())

    async def async_get_lan_status(self):
        return await self._safe_call(self.client.network.lan())

    async def async_get_dns_settings(self):
        return await self._safe_call(self.client.network.dns())

    # =====================================================
    # VPN
    # =====================================================
    async def async_get_vpn_status(self):
        return await self._safe_call(self.client.vpn.status())

    # =====================================================
    # OPTIONAL DATA
    # =====================================================
    async def async_get_dhcp_leases(self):
        return await self._safe_call(self.client.dhcp.leases())

    async def async_get_port_forwarding(self):
        return await self._safe_call(self.client.firewall.port_forwarding())

    async def async_get_usb_devices(self):
        return await self._safe_call(self.client.usb.devices())

    async def async_get_logs(self):
        return await self._safe_call(self.client.system.logs())

    async def async_get_firmware_status(self):
        return await self._safe_call(self.client.system.firmware())

    # =====================================================
    # CONTROL
    # =====================================================
    async def async_set_wifi(self, iface: str, enabled: bool):
        if not iface:
            raise ValueError("interface required")

        return await self._safe_call(
            self.client.wifi.set_enabled(iface, enabled)
        )

    async def async_set_vpn(self, enabled: bool):
        if enabled:
            return await self._safe_call(self.client.vpn.start())
        return await self._safe_call(self.client.vpn.stop())

    async def async_reboot(self):
        return await self._safe_call(self.client.system.reboot())