from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Optional, TypedDict

from aiohttp import ClientError, ClientTimeout
from yarl import URL

_LOGGER = logging.getLogger(__name__)


# =====================================================
# EXCEPTIONS
# =====================================================

class GlinetError(Exception): ...
class GlinetAuthError(GlinetError): ...
class GlinetConnectionError(GlinetError): ...
class GlinetTimeoutError(GlinetConnectionError): ...
class GlinetApiError(GlinetError): ...
class GlinetCircuitOpen(GlinetConnectionError): ...


# =====================================================
# TYPES
# =====================================================

class AuthResult(TypedDict):
    sid: str
    mode: str


# =====================================================
# CIRCUIT BREAKER
# =====================================================

class CircuitBreaker:
    def __init__(self, fail_threshold: int = 5, reset_timeout: int = 60):
        self.failures = 0
        self.fail_threshold = fail_threshold
        self.reset_timeout = reset_timeout
        self.open_until: float = 0

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.fail_threshold:
            self.open_until = time.time() + self.reset_timeout

    def record_success(self):
        self.failures = 0
        self.open_until = 0

    def allow(self) -> bool:
        return time.time() >= self.open_until


# =====================================================
# CLIENT
# =====================================================

class GLinetClient:
    def __init__(self, session, base_url: str, timeout: int = 10, *, close_session: bool = False):
        self._session = session
        self._base_url = str(URL(base_url).with_path("").with_query(""))
        self._timeout = ClientTimeout(total=timeout)

        self._close_session = close_session

        self._sid: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._rpc_id = 0

        self._auth_lock = asyncio.Lock()
        self._rpc_lock = asyncio.Lock()

        self._circuit = CircuitBreaker()
        self._last_success = 0.0

        self._mode: Optional[str] = None

    # =====================================================
    # UTIL
    # =====================================================

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    # =====================================================
    # HEALTH
    # =====================================================

    def _healthy(self) -> bool:
        return (
            self._sid is not None
            and (time.time() - self._last_success) < 600
            and self._circuit.allow()
        )

    def _touch(self):
        self._last_success = time.time()
        self._circuit.record_success()

    # =====================================================
    # HTTP
    # =====================================================

    async def _post(self, path: str, payload: dict) -> dict:
        if not self._circuit.allow():
            raise GlinetCircuitOpen("Circuit breaker open")

        url = str(URL(self._base_url) / path.lstrip("/"))

        try:
            async with self._session.post(url, json=payload, timeout=self._timeout) as resp:
                text = await resp.text()

                if resp.status >= 400:
                    raise GlinetConnectionError(text[:200])

                try:
                    return await resp.json(content_type=None)
                except Exception:
                    return json.loads(text or "{}")

        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError as e:
            raise GlinetTimeoutError() from e
        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e

    # =====================================================
    # BACKEND DETECTION
    # =====================================================

    async def _detect_backend(self):
        if self._mode:
            return

        gl_ok = False
        luci_ok = False

        try:
            r = await self._post("/rpc", {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "challenge",
                "params": {"username": "root"},
            })

            res = r.get("result")
            if isinstance(res, dict) and res.get("salt") and res.get("nonce"):
                gl_ok = True
        except Exception:
            pass

        try:
            r = await self._post("/cgi-bin/luci/rpc/auth", {
                "method": "login",
                "params": ["root", "invalid"],
                "id": self._next_id(),
            })

            if isinstance(r, dict) and r.get("result") not in (None, ""):
                luci_ok = True
        except Exception:
            pass

        if gl_ok:
            self._mode = "gl"
        elif luci_ok:
            self._mode = "luci"
        else:
            raise GlinetConnectionError("Unable to detect backend")

        _LOGGER.debug("Detected backend: %s", self._mode)

    # =====================================================
    # HASHES
    # =====================================================

    def _generate_hashes(self, username, password, salt, nonce):
        a = hashlib.md5((password + salt).encode()).hexdigest()
        b = hashlib.md5((salt + password).encode()).hexdigest()

        return [
            hashlib.md5(f"{username}:{a}:{nonce}".encode()).hexdigest(),
            hashlib.md5(f"{username}:{b}:{nonce}".encode()).hexdigest(),
        ]

    # =====================================================
    # SID VALIDATION
    # =====================================================

    async def _validate_sid(self, sid: str) -> bool:
        try:
            r = await self._post("/rpc", {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "call",
                "params": [sid, "system", "board", {}],
            })

            return isinstance(r, dict) and not r.get("error")

        except Exception:
            return False

    # =====================================================
    # LOGIN
    # =====================================================

    async def login(self, username: str, password: str) -> AuthResult:
        async with self._auth_lock:

            if self._healthy():
                return {"sid": self._sid, "mode": self._mode}

            self._username = username
            self._password = password

            await self._detect_backend()

            last = None

            for attempt in range(3):
                try:
                    sid = None

                    if self._mode == "luci":
                        r = await self._post("/cgi-bin/luci/rpc/auth", {
                            "method": "login",
                            "params": [username, password],
                            "id": self._next_id(),
                        })
                        last = r
                        sid = self._extract_sid(r)

                    else:
                        challenge = await self._post("/rpc", {
                            "jsonrpc": "2.0",
                            "id": self._next_id(),
                            "method": "challenge",
                            "params": {"username": username},
                        })

                        res = challenge.get("result") or {}
                        salt = res.get("salt")
                        nonce = res.get("nonce")

                        if salt and nonce:
                            for h in self._generate_hashes(username, password, salt, nonce):
                                r = await self._post("/rpc", {
                                    "jsonrpc": "2.0",
                                    "id": self._next_id(),
                                    "method": "login",
                                    "params": {"username": username, "hash": h},
                                })
                                last = r
                                sid = self._extract_sid(r)
                                if sid:
                                    break

                    if sid and await self._validate_sid(sid):
                        self._sid = sid
                        self._touch()
                        return {"sid": sid, "mode": self._mode}

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    _LOGGER.debug("Login attempt failed: %s", e)

                await asyncio.sleep(2 ** attempt)

            self._circuit.record_failure()
            raise GlinetAuthError(f"Login failed: {last}")

    # =====================================================
    # SID EXTRACTION
    # =====================================================

    def _extract_sid(self, resp: dict) -> Optional[str]:
        r = resp.get("result") if isinstance(resp, dict) else None
        if isinstance(r, str):
            return r
        if isinstance(r, dict):
            return r.get("sid") or r.get("token")
        return None

    # =====================================================
    # RPC
    # =====================================================

    async def rpc(self, namespace: str, method: str, params: dict | None = None):
        async with self._rpc_lock:
            await self.ensure_session()
            return await self._rpc_call(namespace, method, params)

    async def _rpc_call(self, namespace, method, params=None):
        r = await self._post("/rpc", {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "call",
            "params": [self._sid, namespace, method, params or {}],
        })

        if isinstance(r, dict) and r.get("error"):
            self._circuit.record_failure()

            if "access denied" in str(r["error"]).lower():
                self._sid = None
                await self.ensure_session()
                return await self._rpc_call(namespace, method, params)

            raise GlinetApiError(r["error"])

        self._touch()
        return r.get("result")

    # =====================================================
    # SESSION
    # =====================================================

    async def ensure_session(self):
        if self._healthy():
            return

        if not self._username or not self._password:
            raise GlinetAuthError("No credentials set")

        await self.login(self._username, self._password)

    # =====================================================
    # CLOSE
    # =====================================================

    async def close(self):
        if self._close_session:
            await self._session.close()