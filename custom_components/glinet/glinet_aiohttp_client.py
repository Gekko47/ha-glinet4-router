from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any, Optional

from aiohttp import (
    ClientConnectorError,
    ClientError,
    ClientTimeout,
)
from yarl import URL

_LOGGER = logging.getLogger(__name__)


# =========================================================
# EXCEPTIONS
# =========================================================
class GlinetAuthError(Exception):
    pass


class GlinetConnectionError(Exception):
    pass


class GlinetTimeoutError(GlinetConnectionError):
    pass


class GlinetHTTPError(GlinetConnectionError):
    pass


class GlinetApiError(Exception):
    pass


# =========================================================
# CLIENT
# =========================================================
class GLinetClient:
    """
    Home Assistant–ready GL.iNet RPC client.

    Goals:
    - Safe concurrency under HA polling
    - Robust GL.iNet firmware handling
    - Clean auth lifecycle
    - Minimal deadlock risk
    - Stable retry behavior
    """

    def __init__(
        self,
        session,
        base_url: str,
        timeout: int = 10,
        *,
        close_session: bool = False,
    ):
        self._session = session

        # SAFE URL HANDLING (fixes malformed /rpc cases)
        url = URL(base_url)
        self._http_base = str(url.with_path("").with_query(""))

        # Auth state
        self._token: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        # Concurrency
        self._login_lock = asyncio.Lock()
        self._rpc_id = itertools.count(1)

        # Timeout (HA-safe defaults)
        self._timeout = ClientTimeout(
            total=timeout,
            connect=max(3, timeout // 2),
            sock_read=timeout,
        )

        # Lifecycle
        self._close_session = close_session

    # =====================================================
    # AUTH
    # =====================================================
    async def login(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

        async with self._login_lock:
            if self._token:
                return

            try:
                async with self._session.get(
                    self._http_base,
                    timeout=self._timeout,
                ) as resp:
                    await resp.text()
            except Exception as e:
                raise GlinetConnectionError(f"Router unreachable: {e}") from e

            payload = self._build_payload(
                method="login",
                params={"username": username, "password": password},
            )

            data = await self._raw_post("/rpc", json=payload)

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
    # PAYLOAD
    # =====================================================
    def _build_payload(self, method: str, params: Any) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": next(self._rpc_id),
            "method": method,
            "params": params,
        }

    # =====================================================
    # CORE RPC
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
            params=[self._token, namespace, method, params or {}],
        )

        try:
            data = await self._raw_post("/rpc", json=payload)

            if not isinstance(data, dict):
                raise GlinetApiError("Invalid RPC response")

            if data.get("error"):
                raise GlinetApiError(data["error"])

            result = data.get("result")
            if result is None:
                raise GlinetApiError(f"Missing result: {data}")

            return result

        # -------------------------------------------------
        # AUTH RECOVERY PATH
        # -------------------------------------------------
        except GlinetAuthError:
            if retry and retry_count == 0:
                _LOGGER.debug("Re-authenticating GL.iNet session")

                self._token = None

                await asyncio.sleep(min(1.5, 0.3 * (retry_count + 1)))
                await self.ensure_logged_in()

                return await self._rpc(
                    namespace,
                    method,
                    params,
                    retry=True,
                    retry_count=1,
                )
            raise

        # -------------------------------------------------
        # TIMEOUT NORMALIZATION
        # -------------------------------------------------
        except asyncio.TimeoutError:
            raise GlinetTimeoutError("RPC timeout")

    # =====================================================
    # HTTP LAYER
    # =====================================================
    async def _raw_post(self, path: str, **kwargs) -> Any:
        if not self._session:
            raise GlinetConnectionError("Session not initialized")

        url = f"{self._http_base}{path}"

        headers = kwargs.pop("headers", {})
        headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": self._http_base,
                "Referer": f"{self._http_base}/",
            }
        )

        try:
            async with self._session.post(
                url,
                timeout=self._timeout,
                headers=headers,
                **kwargs,
            ) as resp:

                text = await resp.text()

                # PRESERVE ERROR CONTEXT (important for router debugging)
                if resp.status >= 400:
                    raise GlinetHTTPError(
                        f"HTTP {resp.status}: {text[:300]}"
                    )

                try:
                    return await resp.json()
                except Exception as e:
                    raise GlinetApiError(
                        f"Invalid JSON response: {e} | body={text[:200]}"
                    ) from e

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e

        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e

        except asyncio.TimeoutError:
            raise GlinetTimeoutError("Request timeout")

    # =====================================================
    # API METHODS
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
    # CONTROL METHODS
    # =====================================================
    async def async_set_wifi(self, iface: str, enabled: bool):
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
        if self._close_session and self._session:
            await self._session.close()