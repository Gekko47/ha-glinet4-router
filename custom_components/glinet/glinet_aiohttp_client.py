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
    Flint 2–correct GL.iNet RPC client (gli4py-aligned)

    AUTH FLOW:
      1. challenge(username)
      2. cipher = md5(salt + password)
      3. login_hash = md5(username:cipher:nonce)
      4. login → SID
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
        self._rpc_lock = asyncio.Lock()

        self._rpc_id = itertools.count(1)

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
            if self.sid:
                return

            self._assert_session()
            await self._bootstrap()

            _LOGGER.debug("GL.iNet login attempt as: %s", username)

            challenge = await self._challenge(username)

            if not isinstance(challenge, dict):
                raise GlinetAuthError(f"Invalid challenge response: {challenge}")

            if "error" in challenge:
                raise GlinetAuthError(f"Challenge error: {challenge['error']}")

            if "result" in challenge and isinstance(challenge["result"], dict):
                challenge = challenge["result"]

            try:
                alg = challenge["alg"]
                salt = challenge["salt"]
                nonce = challenge["nonce"]
            except KeyError as e:
                raise GlinetAuthError(
                    f"Missing challenge field: {e} | raw={challenge}"
                ) from e

            cipher = self._cipher_password(alg, salt, password)
            login_hash = self._login_hash(username, cipher, nonce)

            sid_resp = await self._get_sid(username, login_hash)

            if not isinstance(sid_resp, dict):
                raise GlinetAuthError(f"Invalid login response: {sid_resp}")

            sid = sid_resp.get("sid")
            if sid:
                self.sid = sid
                _LOGGER.debug("GL.iNet Flint 2 login successful")
                return
            
            _LOGGER.debug(
                "GL.iNet challenge alg=%s salt_len=%s nonce_present=%s",
                alg,
                len(salt),
                bool(nonce),
            )
            
            raise GlinetAuthError(f"Login failed: {sid_resp}")

    # =====================================================
    # SESSION
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
    # RPC CORE
    # =====================================================
    async def _rpc(self, namespace: str, method: str, params: dict | None = None):
        async with self._rpc_lock:
            await self.ensure_session()

            payload = {
                "jsonrpc": "2.0",
                "id": next(self._rpc_id),
                "method": "call",
                "params": [self.sid, namespace, method, params or {}],
            }

            data = await self._raw_post("/rpc", json=payload)

            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                msg = str(err).lower()

                auth_failed = (
                    "access denied" in msg
                    or "not logged in" in msg
                    or "session" in msg
                )

                if not auth_failed:
                    raise GlinetApiError(err)

                self.sid = None
                await self.ensure_session()

                payload["params"][0] = self.sid
                data = await self._raw_post("/rpc", json=payload)

                if isinstance(data, dict) and data.get("error"):
                    raise GlinetApiError(data["error"])

            return data.get("result")

    # =====================================================
    # VALIDATION
    # =====================================================
    async def async_validate_session(self) -> bool:
        if not self.sid:
            return False

        data = await self._raw_post("/rpc", json={
            "jsonrpc": "2.0",
            "id": next(self._rpc_id),
            "method": "call",
            "params": [self.sid, "system", "status", {}],
        })

        return isinstance(data, dict) and "result" in data

    # =====================================================
    # KEEPALIVE
    # =====================================================
    async def async_keepalive_session(self) -> bool:
        if not self.sid:
            return False

        try:
            return await self.async_validate_session()
        except Exception as e:
            _LOGGER.debug("Keepalive failed: %s", e)
            return False

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

    async def async_reboot(self):
        return await self._rpc("system", "reboot")

    # =====================================================
    # BOOTSTRAP
    # =====================================================
    async def _bootstrap(self):
        try:
            async with self._session.get(self._http_base, timeout=self._timeout) as resp:
                if resp.status >= 400:
                    raise GlinetConnectionError(f"Bootstrap failed HTTP {resp.status}")
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
                    try:
                        return json.loads(text or "{}")
                    except Exception:
                        raise GlinetHTTPError(f"Invalid JSON: {text[:200]}")

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e
        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e
        except asyncio.TimeoutError:
            raise GlinetTimeoutError("Timeout")

    # =====================================================
    # CRYPTO (GLI4PY CORRECT FOR FLINT 2)
    # =====================================================
    def _cipher_password(self, alg: int, salt: str, password: str) -> str:
        """
        GL.iNet compatible password cipher.

        Supports firmware variants:
        - alg=1 → md5
        - alg=5 → sha256
        - alg=6 → sha512

        Most Flint 2 devices use md5, but newer firmware may vary.
        """

        data = (salt + password).encode()

        if alg == 1:
            return hashlib.md5(data).hexdigest()

        if alg == 5:
            return hashlib.sha256(data).hexdigest()

        if alg == 6:
            return hashlib.sha512(data).hexdigest()

        raise GlinetAuthError(f"Unsupported cipher algorithm from router: {alg}")

    def _login_hash(self, username: str, cipher: str, nonce: str) -> str:
        """
        gli4py-compatible:
        md5(username:cipher:nonce)
        """

        return hashlib.md5(f"{username}:{cipher}:{nonce}".encode()).hexdigest()

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