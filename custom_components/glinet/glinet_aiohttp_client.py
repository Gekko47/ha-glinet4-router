from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Any, Optional

from aiohttp import ClientConnectorError, ClientError, ClientTimeout
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
    """Final locked, HACS-grade GL.iNet RPC client."""

    def __init__(
        self,
        session,
        base_url: str,
        timeout: int = 10,
        *,
        close_session: bool = False,
    ):
        self._session = session

        url = URL(base_url)
        self._http_base = str(url.with_path("").with_query(""))

        self._sid: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._login_lock = asyncio.Lock()
        self._rpc_id = itertools.count(1)

        self._login_strategy: Optional[str] = None

        self._timeout = ClientTimeout(
            total=timeout,
            connect=max(3, timeout // 2),
            sock_read=timeout,
        )

        self._close_session = close_session

    # =====================================================
    # LOGIN
    # =====================================================
    async def login(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

        async with self._login_lock:
            if self._sid:
                return

            if self._session is None or getattr(self._session, "closed", False):
                raise GlinetConnectionError("HTTP session invalid")

            # Bootstrap session
            try:
                async with self._session.get(self._http_base, timeout=self._timeout) as resp:
                    await resp.text()
            except asyncio.TimeoutError:
                raise GlinetTimeoutError("Bootstrap timeout")
            except Exception as e:
                raise GlinetConnectionError(f"Router unreachable: {e}") from e

            attempts = [
                ("v4-auth-null", lambda: self._build_payload(
                    "call",
                    [None, "auth", "login", {"username": username, "password": password}],
                )),
                ("v4-auth-empty", lambda: self._build_payload(
                    "call",
                    ["", "auth", "login", {"username": username, "password": password}],
                )),
                ("v4-auth-list", lambda: self._build_payload(
                    "call",
                    [None, "auth", "login", [username, password]],
                )),
                ("legacy", lambda: self._build_payload(
                    "login",
                    {"username": username, "password": password},
                )),
            ]

            if self._login_strategy:
                attempts = sorted(
                    attempts,
                    key=lambda x: 0 if x[0] == self._login_strategy else 1,
                )

            last_error = None

            for i, (name, builder) in enumerate(attempts):
                try:
                    payload = builder()

                    _LOGGER.debug("GL.iNet login attempt: %s", name)

                    data = await self._raw_post("/rpc", json=payload)
                    _LOGGER.debug("Login response (%s): %s", name, data)

                    if isinstance(data, dict) and data.get("error"):
                        err = data["error"]

                        if isinstance(err, dict):
                            code = err.get("code")
                            msg = str(err.get("message", "")).lower()

                            # real auth failure → stop
                            if isinstance(err, dict):
                                code = err.get("code")
                                msg = str(err.get("message", "")).lower()

                                # Only treat as FINAL auth failure if we're on LAST attempt
                                if code in (-32001,) or ("access denied" in msg and i == len(attempts) - 1):
                                    raise GlinetAuthError(err)

                            # otherwise → try next strategy
                            last_error = err
                            continue

                        last_error = err
                        continue

                    sid = self._extract_sid(data)

                    if sid:
                        self._sid = sid
                        self._login_strategy = name
                        _LOGGER.debug("Login success via %s", name)
                        return

                except GlinetAuthError:
                    raise

                except Exception as e:
                    last_error = e

                    if name == self._login_strategy:
                        _LOGGER.debug("Cached login strategy failed, clearing")
                        self._login_strategy = None

                    _LOGGER.debug("Login attempt failed (%s): %s", name, e)

                if i < len(attempts) - 1:
                    await asyncio.sleep(min(0.2 * (i + 1), 1.0))

            raise GlinetAuthError(f"Authentication failed (last error: {repr(last_error)})")

    async def ensure_logged_in(self):
        if self._sid:
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
    # RPC
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
            "call",
            [self._sid, namespace, method, params or {}],
        )

        try:
            data = await self._raw_post("/rpc", json=payload)
            _LOGGER.debug("RPC %s.%s response: %s", namespace, method, data)

            if not isinstance(data, dict):
                raise GlinetApiError("Invalid RPC response")

            if data.get("error"):
                err = data["error"]

                if isinstance(err, dict):
                    code = err.get("code")
                    msg = str(err.get("message", "")).lower()

                    if code in (-32000, -32001) or "access" in msg:
                        raise GlinetAuthError(err)

                raise GlinetApiError(err)

            result = data.get("result")

            if result is None:
                raise GlinetApiError(f"Missing result: {data}")

            return result

        except GlinetAuthError:
            if retry and retry_count == 0:
                _LOGGER.debug("Re-authenticating session")

                self._sid = None

                await asyncio.sleep(min(0.3 * (retry_count + 1), 2.0))
                await self.ensure_logged_in()

                return await self._rpc(
                    namespace,
                    method,
                    params,
                    retry=True,
                    retry_count=1,
                )
            raise

        except asyncio.TimeoutError:
            raise GlinetTimeoutError("RPC timeout")

    # =====================================================
    # HTTP
    # =====================================================
    async def _raw_post(self, path: str, **kwargs) -> Any:
        if self._session is None or getattr(self._session, "closed", False):
            raise GlinetConnectionError("HTTP session invalid")

        url = str(URL(self._http_base) / path.lstrip("/"))

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

                if resp.status >= 400:
                    raise GlinetHTTPError(f"HTTP {resp.status}: {text[:300]}")

                try:
                    return await resp.json(content_type=None)
                except Exception:
                    try:
                        return json.loads(text)
                    except Exception as e:
                        raise GlinetApiError(
                            f"Invalid JSON: {e} | body={text[:200]}"
                        ) from e

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e

        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e

        except asyncio.TimeoutError:
            raise GlinetTimeoutError("HTTP timeout")

    # =====================================================
    # SID EXTRACTION
    # =====================================================
    def _extract_sid(self, data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None

        result = data.get("result") or {}

        for key in ("sid", "token", "session"):
            val = result.get(key)
            if isinstance(val, str):
                return val

        for v in result.values():
            if isinstance(v, dict):
                for key in ("sid", "token"):
                    if isinstance(v.get(key), str):
                        return v[key]

        return None

    # =====================================================
    # API
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

    async def async_get_lan_status(self) -> dict:
        return await self._rpc("network", "lan_status") or {}

    async def async_get_throughput(self) -> dict:
        return await self._rpc("system", "realtime") or {}

    async def async_get_dhcp_leases(self) -> list:
        return await self._rpc("dhcp", "leases") or []

    async def async_get_port_forwarding(self) -> list:
        return await self._rpc("firewall", "port_forwards") or []

    async def async_get_usb_devices(self) -> list:
        return await self._rpc("system", "usb") or []

    async def async_get_logs(self) -> list:
        return await self._rpc("log", "read") or []

    # =====================================================
    # CONTROL
    # =====================================================
    async def async_set_wifi(self, iface: str, enabled: bool):
        return await self._rpc("wifi", "set", {"name": iface, "enabled": enabled})

    async def async_set_vpn(self, enabled: bool):
        return await self._rpc("vpn", "set", {"enabled": enabled})

    async def async_reboot(self):
        return await self._rpc("system", "reboot")

    # =====================================================
    # CLEANUP
    # =====================================================
    async def close(self):
        if self._close_session and self._session:
            await self._session.close()