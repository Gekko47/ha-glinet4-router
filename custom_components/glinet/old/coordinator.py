from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class GlinetCoordinator(DataUpdateCoordinator):
    """
    Modern HA 2026 coordinator:

    - single source of truth
    - normalized + indexed state
    - no dispatcher
    - stable entity consumption model
    """

    def __init__(self, hass, api):
        super().__init__(
            hass,
            _LOGGER,
            name="glinet",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )

        self.api = api

        # stable indexed state
        self._last_clients_by_mac: dict[str, dict[str, Any]] = {}
        self._last_client_signature: tuple | None = None

    # =====================================================
    # CORE UPDATE LOOP
    # =====================================================
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and normalize router state."""

        data: dict[str, Any] = {}

        # =====================================================
        # STATUS (critical)
        # =====================================================
        try:
            data["status"] = await self.api.async_get_status()
        except ClientError as e:
            raise UpdateFailed(f"status failed: {e}") from e

        # =====================================================
        # SYSTEM INFO
        # =====================================================
        try:
            data["system_info"] = await self.api.async_get_system_info()
        except Exception:
            _LOGGER.debug("system_info failed")
            data["system_info"] = {}

        # =====================================================
        # CLIENTS (normalized)
        # =====================================================
        try:
            raw_clients = await self.api.async_get_clients()
        except ClientError as e:
            raise UpdateFailed(f"clients failed: {e}") from e

        if not isinstance(raw_clients, list):
            raw_clients = []

        clients_by_mac: dict[str, dict[str, Any]] = {}

        for c in raw_clients:
            mac = (c.get("mac") or "").lower().strip()
            if not mac:
                continue

            clients_by_mac[mac] = {
                "mac": mac,
                "name": c.get("name"),
                "ip": c.get("ip"),
                "hostname": c.get("hostname"),
                "rx": c.get("rx"),
                "tx": c.get("tx"),
                "connected": c.get("connected"),
                "interface": c.get("interface"),
                "last_seen": c.get("last_seen"),
                "signal": c.get("signal"),
                "vendor": c.get("vendor"),
            }

        data["clients_by_mac"] = clients_by_mac
        data["clients"] = list(clients_by_mac.values())

        # =====================================================
        # THROUGHPUT
        # =====================================================
        try:
            data["throughput"] = await self.api.async_get_throughput()
        except Exception:
            data["throughput"] = {}

        # =====================================================
        # WIFI (robust parsing + normalized index)
        # =====================================================
        wifi_raw: Any = {}
        wifi_by_name: dict[str, dict[str, Any]] = {}

        try:
            wifi_raw = await self.api.async_get_wifi()
        except Exception:
            _LOGGER.debug("wifi fetch failed")
            wifi_raw = {}

        interfaces: list[dict[str, Any]] = []

        if isinstance(wifi_raw, dict):
            interfaces = (
                wifi_raw.get("interfaces")
                or wifi_raw.get("ifaces")
                or []
            )
        elif isinstance(wifi_raw, list):
            interfaces = wifi_raw

        for iface in interfaces:
            name = iface.get("name")
            if not name:
                continue

            wifi_by_name[name] = {
                "name": name,
                "ssid": iface.get("ssid"),
                "enabled": iface.get("enabled"),
                "guest": iface.get("guest"),
                "band": iface.get("band"),
                "channel": iface.get("channel"),
                "hidden": iface.get("hidden"),
                "raw": iface,
            }

        data["wifi"] = wifi_raw
        data["wifi_by_name"] = wifi_by_name

        # =====================================================
        # WAN
        # =====================================================
        try:
            data["wan_status"] = await self.api.async_get_wan_status()
        except Exception:
            data["wan_status"] = {}

        # =====================================================
        # VPN (normalized + resilient)
        # =====================================================
        vpn_data: dict[str, Any] = {}

        try:
            vpn_raw = await self.api.async_get_vpn()

            if isinstance(vpn_raw, dict):
                connected = (
                    vpn_raw.get("connected")
                    or vpn_raw.get("status") in ("running", "connected", "up")
                )

                vpn_data = {
                    "connected": bool(connected),
                    "type": vpn_raw.get("type"),
                    "server": vpn_raw.get("server"),
                    "status": vpn_raw.get("status"),
                    "uptime": vpn_raw.get("uptime"),
                    "raw": vpn_raw,
                }

        except Exception:
            _LOGGER.debug("vpn fetch failed")
            vpn_data = {"connected": False}

        data["vpn"] = vpn_data

        # =====================================================
        # OPTIONAL FIELDS (consistent contract)
        # =====================================================
        data.update(
            {
                "dhcp_leases": None,
                "port_forwarding": None,
                "lan_status": None,
                "dns_settings": None,
                "usb_devices": None,
                "logs": None,
            }
        )

        # =====================================================
        # CHANGE DETECTION (internal only)
        # =====================================================
        signature = self._build_client_signature(clients_by_mac)

        if signature != self._last_client_signature:
            self._last_client_signature = signature
            self._last_clients_by_mac = clients_by_mac

        return data

    # =====================================================
    # SIGNATURE (fast + stable)
    # =====================================================
    def _build_client_signature(
        self, clients: dict[str, dict[str, Any]]
    ) -> tuple:
        return tuple(
            (
                mac,
                c.get("ip"),
                c.get("connected"),
                c.get("rx"),
                c.get("tx"),
            )
            for mac, c in sorted(clients.items())
        )

    # =====================================================
    # PUBLIC ACCESSOR
    # =====================================================
    def get_client(self, mac: str) -> dict[str, Any] | None:
        return self._last_clients_by_mac.get(mac.lower().strip())