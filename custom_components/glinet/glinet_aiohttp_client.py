from __future__ import annotations

import logging
from typing import Any, Optional

from aiohttp import ClientResponseError, ClientConnectorError, ClientError, ClientTimeout

_LOGGER = logging.getLogger(__name__)


# =========================================================
# EXCEPTIONS (CLEAN FAILURE MODEL)
# =========================================================
class GlinetAuthError(Exception):
    """Authentication failure."""


class GlinetConnectionError(Exception):
    """Network / connectivity issue."""


class GlinetApiError(Exception):
    """Unexpected API response."""


# =========================================================
# CLIENT
# =========================================================
class GLinetClient:
    """
    HA-safe GL.iNet API client.

    Design goals:
    - stable HA integration behavior
    - explicit error types (no ClientError abuse)
    - retry bounded + safe
    - consistent async_* API surface
    """

    def __init__(
        self,
        session,
        base_url: str,
        timeout: int = 10,
    ):
        self._session = session
        self._base_url = base_url.rstrip("/")

        self._token: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._timeout = ClientTimeout(total=timeout)

    # =====================================================
    # AUTH
    # =====================================================
    async def login(self, username: str, password: str) -> Any:
        self._username = username
        self._password = password

        data = await self._raw_post(
            "/login",
            json={"username": username, "password": password},
        )

        if not isinstance(data, dict):
            raise GlinetApiError("Invalid login response")

        token = (
            data.get("token")
            or data.get("session")
            or data.get("auth_token")
        )

        if not token:
            raise GlinetAuthError("Authentication failed")

        self._token = token
        return data

    async def ensure_logged_in(self):
        if self._token:
            return

        if not self._username or not self._password:
            raise GlinetAuthError("Missing stored credentials")

        await self.login(self._username, self._password)

    # =====================================================
    # CORE REQUEST
    # =====================================================
    async def _request(
        self,
        method: str,
        path: str,
        *,
        retry: bool = True,
        retry_count: int = 0,
        **kwargs,
    ) -> Any:

        await self.ensure_logged_in()

        url = f"{self._base_url}{path}"

        headers = kwargs.pop("headers", {})
        headers["Content-Type"] = "application/json"

        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            ) as resp:

                # AUTH FAILURE
                if resp.status in (401, 403):
                    raise GlinetAuthError("Auth expired or invalid")

                resp.raise_for_status()

                # SAFE JSON PARSE
                ctype = resp.headers.get("Content-Type", "")

                if "application/json" in ctype:
                    try:
                        return await resp.json()
                    except Exception:
                        raise GlinetApiError("Invalid JSON response")

                return await resp.text()

        except GlinetAuthError:
            # force re-login once
            if retry and retry_count == 0:
                _LOGGER.debug("Re-authenticating after auth failure")
                self._token = None
                await self.ensure_logged_in()

                return await self._request(
                    method,
                    path,
                    retry=True,
                    retry_count=1,
                    **kwargs,
                )

            raise

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e

        except (ClientResponseError, ClientError) as e:
            raise GlinetConnectionError(str(e)) from e

    async def _raw_post(self, path: str, **kwargs) -> Any:
        url = f"{self._base_url}{path}"

        try:
            async with self._session.post(
                url,
                timeout=self._timeout,
                **kwargs,
            ) as resp:
                resp.raise_for_status()

                try:
                    return await resp.json()
                except Exception:
                    return await resp.text()

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e

        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e

    # =====================================================
    # PUBLIC HTTP METHODS
    # =====================================================
    async def get(self, path: str) -> Any:
        return await self._request("GET", path)

    async def post(self, path: str, json: dict | None = None) -> Any:
        return await self._request("POST", path, json=json)

    # =====================================================
    # NORMALIZED API (USED BY COORDINATOR)
    # =====================================================
    async def async_get_status(self) -> Any:
        return await self.get("/status")

    async def async_get_system_info(self) -> Any:
        return await self.get("/system/info")

    async def async_get_clients(self) -> Any:
        return await self.get("/clients")

    async def async_get_throughput(self) -> Any:
        return await self.get("/system/realtime")

    async def async_get_wifi(self) -> Any:
        return await self.get("/wifi/status")

    async def async_get_wan_status(self) -> Any:
        return await self.get("/internet/status")

    async def async_get_vpn(self) -> Any:
        return await self.get("/vpn/status")

    # =====================================================
    # CONTROL API
    # =====================================================
    async def async_set_wifi(self, iface: str, enabled: bool) -> Any:
        if not iface:
            raise ValueError("iface required")

        return await self.post(
            "/wifi/set",
            json={"name": iface, "enabled": enabled},
        )

    async def async_set_vpn(self, enabled: bool) -> Any:
        return await self.post(
            "/vpn/set",
            json={"enabled": enabled},
        )

    async def async_reboot(self) -> Any:
        return await self.post("/system/reboot")

    # =====================================================
    # CLEANUP
    # =====================================================
    async def close(self):
        """Session managed by HA."""
        return