from __future__ import annotations

import logging
from typing import Any, Optional

from aiohttp import ClientResponseError, ClientConnectorError, ClientError, ClientTimeout

_LOGGER = logging.getLogger(__name__)


# =========================================================
# EXCEPTIONS
# =========================================================
class GlinetAuthError(Exception):
    pass


class GlinetConnectionError(Exception):
    pass


class GlinetApiError(Exception):
    pass


# =========================================================
# CLIENT
# =========================================================
class GLinetClient:
    """Production-grade GL.iNet RPC client (no REST fallback)."""

    def __init__(self, session, base_url: str, timeout: int = 10):
        self._session = session
        self._base_url = base_url.rstrip("/")

        self._token: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._timeout = ClientTimeout(total=timeout)
        self._rpc_id = 0

    # =====================================================
    # AUTH
    # =====================================================
    async def login(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

        payload = self._build_payload(
            method="login",
            params={
                "username": username,
                "password": password,
            },
        )

        data = await self._raw_post("/rpc", json=payload)

        _LOGGER.debug("RPC login response: %s", data)

        if not isinstance(data, dict):
            raise GlinetApiError("Invalid login response")

        result = data.get("result") or {}

        token = result.get("sid") or result.get("token")

        if not token:
            raise GlinetAuthError(f"Authentication failed: {data}")

        self._token = token

    async def ensure_logged_in(self):
        if self._token:
            return

        if not self._username or not self._password:
            raise GlinetAuthError("Missing credentials")

        await self.login(self._username, self._password)

    # =====================================================
    # PAYLOAD BUILDER
    # =====================================================
    def _build_payload(self, method: str, params: Any) -> dict:
        self._rpc_id += 1

        return {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": method,
            "params": params,
        }

    # =====================================================
    # RPC CORE
    # =====================================================
    async def _rpc(
        self,
        namespace: str,
        method: str,
        params: dict | None = None,
        *,
        retry: bool = True,
        retry_count: int = 0,
    ) -> Any:

        await self.ensure_logged_in()

        payload = self._build_payload(
            method="call",
            params=[
                self._token,
                namespace,
                method,
                params or {},
            ],
        )

        try:
            data = await self._raw_post("/rpc", json=payload)

            _LOGGER.debug("RPC %s.%s -> %s", namespace, method, data)

            if not isinstance(data, dict):
                raise GlinetApiError("Invalid RPC response")

            if data.get("error"):
                raise GlinetApiError(data["error"])

            result = data.get("result")

            if result is None:
                raise GlinetApiError(f"Missing result in response: {data}")

            return result

        except GlinetAuthError:
            if retry and retry_count == 0:
                _LOGGER.debug("Re-authenticating RPC session")
                self._token = None
                await self.ensure_logged_in()

                return await self._rpc(
                    namespace,
                    method,
                    params,
                    retry=True,
                    retry_count=1,
                )
            raise

    # =====================================================
    # RAW HTTP
    # =====================================================
    async def _raw_post(self, path: str, **kwargs) -> Any:
        url = f"{self._base_url}{path}"

        try:
            async with self._session.post(
                url,
                timeout=self._timeout,
                **kwargs,
            ) as resp:

                if resp.status in (401, 403):
                    raise GlinetAuthError("Auth failed")

                resp.raise_for_status()

                try:
                    return await resp.json()
                except Exception:
                    raise GlinetApiError("Invalid JSON response")

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e

        except (ClientResponseError, ClientError) as e:
            raise GlinetConnectionError(str(e)) from e

    # =====================================================
    # NORMALIZED API (FOR COORDINATORS)
    # =====================================================
    async def async_get_system_info(self) -> dict:
        return await self._rpc("system", "info") or {}

    async def async_get_status(self) -> dict:
        return await self._rpc("system", "status") or {}

    async def async_get_clients(self) -> dict:
        return await self._rpc("client", "list") or {}

    async def async_get_wifi(self) -> dict:
        return await self._rpc("wifi", "status") or {}

    async def async_get_vpn(self) -> dict:
        return await self._rpc("vpn", "status") or {}

    async def async_get_wan_status(self) -> dict:
        return await self._rpc("network", "wan_status") or {}

    async def async_get_throughput(self) -> dict:
        return await self._rpc("system", "realtime") or {}

    async def async_get_lan_status(self) -> dict:
        return await self._rpc("network", "lan_status") or {}

    async def async_get_dhcp_leases(self) -> list:
        return await self._rpc("dhcp", "leases") or []

    async def async_get_port_forwarding(self) -> list:
        return await self._rpc("firewall", "port_forwards") or []

    async def async_get_usb_devices(self) -> list:
        return await self._rpc("system", "usb") or []

    async def async_get_logs(self) -> list:
        return await self._rpc("log", "read") or []

    # =====================================================
    # CONTROL API
    # =====================================================
    async def async_set_wifi(self, iface: str, enabled: bool):
        if not iface:
            raise ValueError("iface required")

        return await self._rpc(
            "wifi",
            "set",
            {"name": iface, "enabled": enabled},
        )

    async def async_set_vpn(self, enabled: bool):
        return await self._rpc(
            "vpn",
            "set",
            {"enabled": enabled},
        )

    async def async_reboot(self):
        return await self._rpc("system", "reboot")

    # =====================================================
    # CLEANUP
    # =====================================================
    async def close(self):
        """Session managed by Home Assistant."""
        return