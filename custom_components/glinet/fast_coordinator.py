from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

_LOGGER = logging.getLogger(__name__)


class GlinetFastCoordinator(DataUpdateCoordinator):
    """Fast-changing network state (clients, wifi, vpn, throughput)."""

    def __init__(self, hass, api, interval: int = 30):
        super().__init__(
            hass,
            _LOGGER,
            name="glinet_fast",
            update_interval=timedelta(seconds=interval),
        )

        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}

        # -------------------------
        # CLIENTS
        # -------------------------
        try:
            raw_clients = await self.api.async_get_clients()
        except ClientError as e:
            raise UpdateFailed(f"clients failed: {e}") from e

        clients_by_mac = {}

        if isinstance(raw_clients, list):
            for c in raw_clients:
                mac = (c.get("mac") or "").lower().strip()
                if not mac:
                    continue

                clients_by_mac[mac] = {
                    "mac": mac,
                    "name": c.get("name"),
                    "ip": c.get("ip"),
                    "interface": c.get("interface"),
                    "connected": c.get("connected"),
                    "rx": c.get("rx"),
                    "tx": c.get("tx"),
                    "signal": c.get("signal"),
                }

        data["clients_by_mac"] = clients_by_mac
        data["clients"] = list(clients_by_mac.values())

        # -------------------------
        # WIFI
        # -------------------------
        try:
            wifi_raw = await self.api.async_get_wifi()
        except Exception:
            wifi_raw = {}

        wifi_by_name = {}

        interfaces = (
            wifi_raw.get("interfaces")
            if isinstance(wifi_raw, dict)
            else wifi_raw if isinstance(wifi_raw, list) else []
        )

        for iface in interfaces:
            name = iface.get("name")
            if not name:
                continue

            wifi_by_name[name] = {
                "name": name,
                "ssid": iface.get("ssid"),
                "enabled": iface.get("enabled"),
                "band": iface.get("band"),
                "channel": iface.get("channel"),
                "guest": iface.get("guest"),
            }

        data["wifi_by_name"] = wifi_by_name

        # -------------------------
        # VPN
        # -------------------------
        try:
            vpn_raw = await self.api.async_get_vpn()
        except Exception:
            vpn_raw = {}

        if isinstance(vpn_raw, dict):
            data["vpn"] = {
                "connected": bool(
                    vpn_raw.get("connected")
                    or vpn_raw.get("status") in ("up", "running", "connected")
                ),
                "type": vpn_raw.get("type"),
                "server": vpn_raw.get("server"),
                "status": vpn_raw.get("status"),
                "uptime": vpn_raw.get("uptime"),
            }
        else:
            data["vpn"] = {"connected": False}

        # -------------------------
        # THROUGHPUT
        # -------------------------
        try:
            data["throughput"] = await self.api.async_get_throughput()
        except Exception:
            data["throughput"] = {}

        return data