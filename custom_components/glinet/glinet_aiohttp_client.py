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
    Hardened GL.iNet + LuCI client (HA-safe)

    FIXES:
    - SID only committed after final validation
    - no ghost sessions
    - safe backend detection
    - correct handling of -32000 Access denied
    - avoids false login failure due to transient RPC delay
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

        self.sid: Optional[str] = None
        self._pending_sid: Optional[str] = None

        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._login_lock = asyncio.Lock()
        self._rpc_lock = asyncio.Lock()
        self._reauth_lock = asyncio.Lock()

        self._rpc_id = itertools.count(1)
        self._timeout = ClientTimeout(total=timeout, connect=max(3, timeout // 2))
        self._close_session = close_session

        self._mode: Optional[str] = None
        self._rpc_base = "/rpc"
        self._auth_base = "/rpc"

    # =====================================================
    # BACKEND DETECTION (SAFE + NON-DESTRUCTIVE)
    # =====================================================
    async def _detect_backend(self):
        if self._mode:
            return

        gl_score = 0
        luci_score = 0

        try:
            r = await self._raw_post("/rpc", json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "challenge",
                "params": {"username": "root"},
            })

            result = r.get("result") if isinstance(r, dict) else None
            if isinstance(result, dict):
                gl_score += int("salt" in result)
                gl_score += int("nonce" in result)

        except Exception:
            pass

        try:
            r = await self._raw_post("/cgi-bin/luci/rpc/auth", json={
                "method": "login",
                "params": ["root", "test"],
                "id": 1,
            })

            if isinstance(r, dict) and "error" not in r:
                luci_score += 1

        except Exception:
            pass

        self._mode = "luci" if luci_score > gl_score else "gl"
        self._rpc_base = "/cgi-bin/luci/rpc" if self._mode == "luci" else "/rpc"
        self._auth_base = "/cgi-bin/luci/rpc/auth" if self._mode == "luci" else "/rpc"

    # =====================================================
    # HASHING (GL.iNet CHALLENGE AUTH)
    # =====================================================
    def _hashes(self, username: str, password: str, salt: str, nonce: str):
        a = hashlib.md5((password + salt).encode()).hexdigest()
        h1 = hashlib.md5(f"{username}:{a}:{nonce}".encode()).hexdigest()

        b = hashlib.md5((salt + password).encode()).hexdigest()
        h2 = hashlib.md5(f"{username}:{b}:{nonce}".encode()).hexdigest()

        return [h1, h2]

    # =====================================================
    # STRICT SID VALIDATION (FINAL COMMIT ONLY)
    # =====================================================
    async def _validate_sid(self, sid: str) -> bool:
        try:
            r = await self._raw_post(self._rpc_base, json={
                "jsonrpc": "2.0",
                "id": next(self._rpc_id),
                "method": "call",
                "params": [sid, "system", "board", {}],
            })

            if not isinstance(r, dict):
                return False

            if r.get("error"):
                return False

            return r.get("result") is not None

        except Exception:
            return False

    # =====================================================
    # LOGIN (SAFE FLOW + SINGLE COMMIT POINT)
    # =====================================================
    async def login(self, username: str, password: str):
        self._username = username
        self._password = password

        async with self._login_lock:
            async with self._reauth_lock:

                self.sid = None
                self._pending_sid = None

                await self._detect_backend()

                last = None

                for _ in range(3):

                    candidate_sid: Optional[str] = None

                    # ---------------- LUCI ----------------
                    if self._mode == "luci":
                        try:
                            last = await self._raw_post(
                                self._auth_base,
                                json={
                                    "method": "login",
                                    "params": [username, password],
                                    "id": next(self._rpc_id),
                                },
                            )

                            candidate_sid = self._extract_sid(last)

                        except Exception:
                            pass

                    # ---------------- GL ----------------
                    try:
                        challenge = await self._raw_post(self._rpc_base, json={
                            "jsonrpc": "2.0",
                            "id": next(self._rpc_id),
                            "method": "challenge",
                            "params": {"username": username},
                        })

                        result = challenge.get("result") if isinstance(challenge, dict) else None
                        if not isinstance(result, dict):
                            continue

                        salt = result.get("salt")
                        nonce = result.get("nonce")

                        if not salt or not nonce:
                            continue

                        for h in self._hashes(username, password, salt, nonce):
                            last = await self._raw_post(self._rpc_base, json={
                                "jsonrpc": "2.0",
                                "id": next(self._rpc_id),
                                "method": "login",
                                "params": {"username": username, "hash": h},
                            })

                            candidate_sid = self._extract_sid(last)

                            if candidate_sid:
                                break

                    except Exception:
                        pass

                    # =================================================
                    # COMMIT POINT (ONLY VALIDATED SID IS ACCEPTED)
                    # =================================================
                    if candidate_sid and await self._validate_sid(candidate_sid):
                        self.sid = candidate_sid
                        return

                raise GlinetAuthError(f"Login failed: {last}")

    # =====================================================
    # SID EXTRACTION
    # =====================================================
    def _extract_sid(self, resp: Any):
        if not isinstance(resp, dict):
            return None

        r = resp.get("result")

        if isinstance(r, str):
            return r

        if isinstance(r, dict):
            return r.get("sid") or r.get("token")

        return resp.get("sid")

    # =====================================================
    # AUTH ERROR DETECTION
    # =====================================================
    def _is_auth_error(self, err: Any) -> bool:
        if isinstance(err, dict):
            return (
                err.get("code") == -32000
                or "access denied" in str(err).lower()
                or "session" in str(err).lower()
            )

        return False

    # =====================================================
    # RPC
    # =====================================================
    async def _rpc(self, namespace: str, method: str, params=None):
        async with self._rpc_lock:
            await self.ensure_session()

            for _ in range(2):

                payload = {
                    "jsonrpc": "2.0",
                    "id": next(self._rpc_id),
                    "method": "call",
                    "params": [self.sid, namespace, method, params or {}],
                }

                data = await self._raw_post(self._rpc_base, json=payload)

                if isinstance(data, dict) and data.get("error"):
                    if self._is_auth_error(data["error"]):
                        async with self._reauth_lock:
                            self.sid = None
                            await self.login(self._username, self._password)
                        continue

                    raise GlinetApiError(data["error"])

                return data.get("result")

            raise GlinetAuthError("RPC failed after retry")

    # =====================================================
    # SESSION HANDLING
    # =====================================================
    async def ensure_session(self):
        if self.sid:
            return
        await self.login(self._username, self._password)

    # =====================================================
    # HTTP CORE
    # =====================================================
    async def _raw_post(self, path: str, **kwargs):
        url = str(URL(self._http_base) / path.lstrip("/"))

        try:
            async with self._session.post(url, timeout=self._timeout, **kwargs) as resp:
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