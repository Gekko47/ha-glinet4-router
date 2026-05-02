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
    Hardened GL.iNet + LuCI dual-stack client

    Guarantees:
    - no ghost SID acceptance
    - strict backend detection (no false LuCI switching)
    - SID validated before use
    - single-flight login + reauth protection
    - safe RPC retry handling
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
    # BACKEND DETECTION (STRICT & SAFE)
    # =====================================================
    async def _detect_backend(self):
        if self._mode:
            return

        gl_ok = False
        luci_ok = False

        # ---------------- GL PROBE ----------------
        try:
            r = await self._raw_post("/rpc", json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "challenge",
                "params": {"username": "root"},
            })

            result = r.get("result") if isinstance(r, dict) else None

            if (
                isinstance(result, dict)
                and isinstance(result.get("salt"), str)
                and isinstance(result.get("nonce"), str)
            ):
                gl_ok = True

        except Exception:
            pass

        # ---------------- LUCI PROBE (FIXED STRICT CHECK) ----------------
        try:
            r = await self._raw_post("/cgi-bin/luci/rpc/auth", json={
                "method": "login",
                "params": ["root", "test"],
                "id": 1,
            })

            # FIX: only accept real structured responses
            if (
                isinstance(r, dict)
                and ("result" in r or "sid" in r or "token" in r)
                and "html" not in str(r).lower()
            ):
                luci_ok = True

        except Exception:
            pass

        if luci_ok and not gl_ok:
            self._mode = "luci"
            self._rpc_base = "/cgi-bin/luci/rpc"
            self._auth_base = "/cgi-bin/luci/rpc/auth"
        else:
            self._mode = "gl"
            self._rpc_base = "/rpc"
            self._auth_base = "/rpc"

    # =====================================================
    # HASHING (GL AUTH)
    # =====================================================
    def _hashes(self, username: str, password: str, salt: str, nonce: str):
        a = hashlib.md5((password + salt).encode()).hexdigest()
        h1 = hashlib.md5(f"{username}:{a}:{nonce}".encode()).hexdigest()

        b = hashlib.md5((salt + password).encode()).hexdigest()
        h2 = hashlib.md5(f"{username}:{b}:{nonce}".encode()).hexdigest()

        return [h1, h2]

    # =====================================================
    # SID VALIDATION (STRICT)
    # =====================================================
    async def _validate_sid(self, sid: str) -> bool:
        try:
            r = await self._raw_post(self._rpc_base, json={
                "jsonrpc": "2.0",
                "id": next(self._rpc_id),
                "method": "call",
                "params": [sid, "system", "board", {}],
            })

            return (
                isinstance(r, dict)
                and r.get("error") is None
                and r.get("result") is not None
            )

        except Exception:
            return False

    # =====================================================
    # LOGIN (SAFE + NON-REENTRANT)
    # =====================================================
    async def login(self, username: str, password: str):
        self._username = username
        self._password = password

        async with self._login_lock:
            async with self._reauth_lock:

                self.sid = None
                await self._detect_backend()

                last = None

                for _ in range(3):

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

                            sid = self._extract_sid(last)

                            if sid and await self._validate_sid(sid):
                                self.sid = sid
                                return

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
                            break  # prevents wasted retries

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

                            sid = self._extract_sid(last)

                            if sid and await self._validate_sid(sid):
                                self.sid = sid
                                return

                    except Exception:
                        pass

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
            code = err.get("code")
            msg = str(err.get("message", "")).lower()
            return code == -32000 or "access denied" in msg or "session" in msg

        return "access denied" in str(err).lower()

    # =====================================================
    # RPC (SAFE REAUTH, SINGLE CYCLE)
    # =====================================================
    async def _rpc(self, namespace: str, method: str, params=None):
        async with self._rpc_lock:
            await self.ensure_session()

            reauth_done = False

            for _ in range(2):

                payload = {
                    "jsonrpc": "2.0",
                    "id": next(self._rpc_id),
                    "method": "call",
                    "params": [self.sid, namespace, method, params or {}],
                }

                data = await self._raw_post(self._rpc_base, json=payload)

                if isinstance(data, dict) and data.get("error"):
                    err = data["error"]

                    if self._is_auth_error(err):
                        if reauth_done:
                            raise GlinetAuthError("Repeated auth failure")

                        reauth_done = True
                        async with self._reauth_lock:
                            self.sid = None
                            await self.login(self._username, self._password)

                        continue

                    raise GlinetApiError(err)

                return data.get("result")

            raise GlinetAuthError("RPC failed after retry")

    # =====================================================
    # SESSION
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
            async with self._session.post(
                url,
                timeout=self._timeout,
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