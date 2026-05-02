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
    GL.iNet client with TRUE gli4py-parity

    Guarantees:
    - Correct backend detection (validated)
    - Dual GL RPC + LuCI RPC support
    - gli4py-auth retry semantics
    - "Access denied" is retry signal, not failure
    - Safe RPC re-auth cycle (2-stage)
    """

    def __init__(self, session, base_url: str, timeout: int = 10, *, close_session=False):
        self._session = session
        self._http_base = str(URL(base_url).with_path("").with_query(""))

        self.sid: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._login_lock = asyncio.Lock()
        self._rpc_lock = asyncio.Lock()
        self._rpc_id = itertools.count(1)

        self._timeout = ClientTimeout(total=timeout, connect=max(3, timeout // 2))

        self._close_session = close_session

        self._rpc_path = "/rpc"
        self._luci_mode = False
        self._detected = False

    # =====================================================
    # BACKEND DETECTION (STRICT)
    # =====================================================
    async def _detect_backend(self):
        if self._detected:
            return

        _LOGGER.debug("Detecting backend...")

        # --- Try GL RPC ---
        try:
            resp = await self._raw_post("/rpc", json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "challenge",
                "params": {"username": "root"},
            })

            if isinstance(resp, dict) and (
                "result" in resp or "error" in resp
            ):
                self._rpc_path = "/rpc"
                self._luci_mode = False
                self._detected = True
                _LOGGER.debug("Detected GL backend")
                return
        except Exception:
            pass

        # --- Try LuCI ---
        try:
            resp = await self._raw_post("/cgi-bin/luci/rpc/auth", json={
                "method": "login",
                "params": ["root", "invalid"],
                "id": 1,
            })

            if isinstance(resp, dict):
                self._rpc_path = "/cgi-bin/luci/rpc"
                self._luci_mode = True
                self._detected = True
                _LOGGER.debug("Detected LuCI backend")
                return
        except Exception:
            pass

        raise GlinetConnectionError("Unable to detect backend")

    # =====================================================
    # LOGIN (gli4py-correct)
    # =====================================================
    async def login(self, username: str, password: str):
        self._username = username
        self._password = password

        async with self._login_lock:
            self.sid = None

            await self._detect_backend()

            last = None

            for attempt in range(3):
                if self._luci_mode:
                    last = await self._raw_post(
                        f"{self._rpc_path}/auth",
                        json={
                            "method": "login",
                            "params": [username, password],
                            "id": next(self._rpc_id),
                        },
                    )

                    if isinstance(last, dict) and last.get("result"):
                        self.sid = last["result"]
                        return

                    continue

                # --- GL challenge ---
                challenge = await self._raw_post(self._rpc_path, json={
                    "jsonrpc": "2.0",
                    "id": next(self._rpc_id),
                    "method": "challenge",
                    "params": {"username": username},
                })

                if not isinstance(challenge, dict):
                    continue

                if "result" in challenge:
                    challenge = challenge["result"]

                try:
                    salt = challenge["salt"]
                    nonce = challenge["nonce"]
                except Exception:
                    continue

                cipher = hashlib.md5((password + salt).encode()).hexdigest()
                login_hash = hashlib.md5(
                    f"{username}:{cipher}:{nonce}".encode()
                ).hexdigest()

                last = await self._raw_post(self._rpc_path, json={
                    "jsonrpc": "2.0",
                    "id": next(self._rpc_id),
                    "method": "login",
                    "params": {"username": username, "hash": login_hash},
                })

                if isinstance(last, dict) and last.get("sid"):
                    self.sid = last["sid"]
                    return

                err = str(last.get("error", "")).lower() if isinstance(last, dict) else ""

                # gli4py rule: ONLY retry on auth failure
                if "access denied" not in err:
                    break

            raise GlinetAuthError(f"Login failed: {last}")

    # =====================================================
    # RPC (2-stage retry)
    # =====================================================
    async def _rpc(self, namespace: str, method: str, params=None):
        async with self._rpc_lock:
            await self.ensure_session()

            for attempt in range(2):
                if self._luci_mode:
                    return await self._raw_post(
                        f"{self._rpc_path}/{namespace}",
                        json={
                            "method": method,
                            "params": params or {},
                            "id": next(self._rpc_id),
                        },
                    )

                payload = {
                    "jsonrpc": "2.0",
                    "id": next(self._rpc_id),
                    "method": "call",
                    "params": [self.sid, namespace, method, params or {}],
                }

                data = await self._raw_post(self._rpc_path, json=payload)

                if isinstance(data, dict) and data.get("error"):
                    msg = str(data["error"]).lower()

                    if "access denied" in msg or "session" in msg:
                        self.sid = None
                        await self.login(self._username, self._password)
                        continue

                    raise GlinetApiError(data["error"])

                return data.get("result")

            raise GlinetAuthError("RPC failed after retry")

    # =====================================================
    # SESSION
    # =====================================================
    async def ensure_session(self):
        if self.sid:
            return
        if not self._username:
            raise GlinetAuthError("Missing credentials")
        await self.login(self._username, self._password)

    # =====================================================
    # HTTP
    # =====================================================
    async def _raw_post(self, path: str, **kwargs):
        url = str(URL(self._http_base) / path.lstrip("/"))

        headers = {
            "Content-Type": "application/json",
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
                    raise GlinetHTTPError(text[:200])

                try:
                    return await resp.json(content_type=None)
                except Exception:
                    return json.loads(text or "{}")

        except ClientConnectorError as e:
            raise GlinetConnectionError(str(e)) from e
        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e
        except asyncio.TimeoutError:
            raise GlinetTimeoutError("Timeout")

    # =====================================================
    # UTIL
    # =====================================================
    def is_logged_in(self):
        return bool(self.sid)

    async def close(self):
        if self._close_session:
            await self._session.close()