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


class GlinetSlowCoordinator(DataUpdateCoordinator):
    """Slow-changing system state (diagnostics, WAN, logs)."""

    def __init__(self, hass, api, interval: int = 300):
        super().__init__(
            hass,
            _LOGGER,
            name="glinet_slow",
            update_interval=timedelta(seconds=interval),
        )

        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}

        # -------------------------
        # STATUS
        # -------------------------
        try:
            data["status"] = await self.api.async_get_status()
        except ClientError as e:
            raise UpdateFailed(f"status failed: {e}") from e

        # -------------------------
        # SYSTEM INFO
        # -------------------------
        try:
            data["system_info"] = await self.api.async_get_system_info()
        except Exception:
            data["system_info"] = {}

        # -------------------------
        # WAN
        # -------------------------
        try:
            data["wan_status"] = await self.api.async_get_wan_status()
        except Exception:
            data["wan_status"] = {}

        # -------------------------
        # PLACEHOLDERS / OPTIONAL
        # -------------------------
        data.update(
            {
                "dhcp_leases": None,
                "port_forwarding": None,
                "usb_devices": None,
                "logs": None,
                "lan_status": None,
            }
        )

        return data