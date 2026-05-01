from __future__ import annotations

import asyncio
import itertools
import json
import logging
import hashlib
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
    """
    Stable, HA-safe GL.iNet client

    FEATURES:
    - Challenge → hash → SID authentication
    - Safe session persistence (SID reuse)
    - Auto recovery on expired sessions
    - Race-condition safe re-login lock
    - Firmware-tolerant error detection
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
        self._http_base = str(URL(base_url).with_path("").with_query(""))

        # Auth state
        self.sid: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        # Locks
        self._login_lock = asyncio.Lock()
        self._relogin_lock = asyncio.Lock()
        self._rpc_lock = asyncio.Lock()

        self._rpc_id = itertools.count(1)

        self._timeout = ClientTimeout(
            total=timeout,
            connect=max(3, timeout // 2),
            sock_read=timeout,
        )

        self._close_session = close_session

    # =====================================================
    # LOGIN (CHALLENGE FLOW)
    # =====================================================
    async def login(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

        async with self._login_lock:
            if self.sid:
                return

            self._assert_session()
            await self._bootstrap()

            challenge = await self._challenge(username)
            if not challenge:
                raise GlinetAuthError("Missing challenge response")

            alg = challenge["alg"]
            salt = challenge["salt"]
            nonce = challenge["nonce"]
            hash_method = challenge.get("hash-method", "md5")

            cipher = self._cipher_password(alg, salt, password)

            login_hash = self._login_hash(hash_method, username, cipher, nonce)

            sid_resp = await self._get_sid(username, login_hash)

            sid = sid_resp.get("sid")
            if not sid:
                raise GlinetAuthError(f"Login failed: {sid_resp}")

            self.sid = sid
            _LOGGER.debug("GL.iNet login successful")

    # =====================================================
    # SESSION RECOVERY ENTRYPOINT
    # =====================================================
    async def ensure_session(self):
        if self.sid:
            return

        if not self._username or not self._password:
            raise GlinetAuthError("Missing credentials")

        await self.login(self._username, self._password)

    # =====================================================
    # CHALLENGE
    # =====================================================
    async def _challenge(self, username: str) -> dict:
        return await self._raw_post("/rpc", json={
            "jsonrpc": "2.0",
            "id": next(self._rpc_id),
            "method": "challenge",
            "params": {"username": username},
        })

    # =====================================================
    # LOGIN REQUEST
    # =====================================================
    async def _get_sid(self, username: str, hashed: str) -> dict:
        return await self._raw_post("/rpc", json={
            "jsonrpc": "2.0",
            "id": next(self._rpc_id),
            "method": "login",
            "params": {
                "username": username,
                "hash": hashed,
            },
        })

    # =====================================================
    # RPC CORE (AUTO HEAL + SAFE RETRY)
    # =====================================================
    async def _rpc(
        self,
        namespace: str,
        method: str,
        params: dict | None = None,
    ):
        async with self._rpc_lock:
            await self.ensure_session()

            payload = {
                "jsonrpc": "2.0",
                "id": next(self._rpc_id),
                "method": "call",
                "params": [self.sid, namespace, method, params or {}],
            }

            data = await self._raw_post("/rpc", json=payload)

            # =================================================
            # AUTH FAILURE DETECTION
            # =================================================
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                code = err.get("code") if isinstance(err, dict) else None
                msg = str(err).lower()

                auth_failed = (
                    code in (-32000, -32001, -32602)
                    or "access denied" in msg
                    or "not logged in" in msg
                    or "session" in msg
                )

                if not auth_failed:
                    raise GlinetApiError(err)

                _LOGGER.debug("SID invalid → attempting single recovery")

                # =================================================
                # SINGLE RECOVERY (NO RECURSION)
                # =================================================
                async with self._login_lock:
                    # double-check after acquiring lock
                    self.sid = None

                    try:
                        await self.ensure_session()
                    except Exception as e:
                        raise GlinetAuthError(f"Re-auth failed: {e}") from e

                    # retry request ONCE (no recursion)
                    payload["params"][0] = self.sid
                    data = await self._raw_post("/rpc", json=payload)

                    if isinstance(data, dict) and data.get("error"):
                        raise GlinetApiError(data["error"])

            return data.get("result")

    # =====================================================
    # VALIDATION
    # =====================================================
    async def async_validate_session(self) -> bool:
        """Validate the current SID without triggering a full re-login."""
        if not self.sid:
            return False

        payload = {
            "jsonrpc": "2.0",
            "id": next(self._rpc_id),
            "method": "call",
            "params": [self.sid, "system", "status", {}],
        }

        data = await self._raw_post("/rpc", json=payload)

        if isinstance(data, dict) and data.get("error"):
            return False

        return "result" in data

    # =====================================================
    # API HELPERS
    # =====================================================
    async def async_get_status(self):
        return await self._rpc("system", "status")

    async def async_get_system_info(self):
        return await self._rpc("system", "info")

    async def async_get_clients(self):
        return await self._rpc("clients", "list")

    async def async_get_throughput(self):
        return await self._rpc("system", "realtime")

    async def async_get_wifi(self):
        return await self._rpc("wifi", "status")

    async def async_get_wan_status(self):
        return await self._rpc("network", "wan")

    async def async_get_vpn(self):
        return await self._rpc("vpn", "status")

    # =====================================================
    # BOOTSTRAP
    # =====================================================
    async def _bootstrap(self):
        try:
            async with self._session.get(self._http_base, timeout=self._timeout):
                pass
        except Exception as e:
            raise GlinetConnectionError(f"Bootstrap failed: {e}") from e

    # =====================================================
    # HTTP LAYER
    # =====================================================
    async def _raw_post(self, path: str, **kwargs) -> Any:
        self._assert_session()

        url = str(URL(self._http_base) / path.lstrip("/"))

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self._http_base,
            "Referer": f"{self._http_base}/",
        }

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
                    return json.loads(text)

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e
        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e
        except asyncio.TimeoutError:
            raise GlinetTimeoutError("Timeout")

    # =====================================================
    # CRYPTO
    # =====================================================
    def _cipher_password(self, alg: int, salt: str, password: str) -> str:
        data = (salt + password).encode()

        if alg == 1:
            return hashlib.md5(data).hexdigest()
        if alg == 5:
            return hashlib.sha256(data).hexdigest()
        if alg == 6:
            return hashlib.sha512(data).hexdigest()

        raise ValueError("Unsupported cipher algorithm")

    def _login_hash(self, method: str, username: str, cipher: str, nonce: str) -> str:
        data = f"{username}:{cipher}:{nonce}".encode()

        if method == "md5":
            return hashlib.md5(data).hexdigest()
        if method == "sha256":
            return hashlib.sha256(data).hexdigest()
        if method == "sha512":
            return hashlib.sha512(data).hexdigest()

        raise ValueError("Unsupported hash method")

    # =====================================================
    # UTIL
    # =====================================================
    def _assert_session(self):
        if self._session is None or getattr(self._session, "closed", False):
            raise GlinetConnectionError("HTTP session invalid")

    def is_logged_in(self) -> bool:
        return bool(self.sid)

    # =====================================================
    # CLOSE
    # =====================================================
    async def close(self):
        if self._close_session and self._session:
            await self._session.close()