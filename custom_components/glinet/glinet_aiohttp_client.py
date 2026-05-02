from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional, TypedDict

from aiohttp import ClientError, ClientTimeout
from yarl import URL

_LOGGER = logging.getLogger(__name__)


# =====================================================
# EXCEPTIONS (HA-style taxonomy)
# =====================================================

class GlinetError(Exception): ...
class GlinetAuthError(GlinetError): ...
class GlinetConnectionError(GlinetError): ...
class GlinetTimeoutError(GlinetConnectionError): ...
class GlinetApiError(GlinetError): ...
class GlinetCircuitOpen(GlinetConnectionError): ...


# =====================================================
# TYPED RESPONSES (HA 2026+ aligned)
# =====================================================

class AuthResult(TypedDict):
    sid: str
    mode: str


class SystemInfo(TypedDict, total=False):
    hostname: str
    model: str
    firmware: str


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
    """
    HA 2026.1+ native GL.iNet client

    DESIGN GOALS:
    - DataUpdateCoordinator compatible
    - no entity-level polling logic
    - strict session correctness
    - safe concurrency + single-flight requests
    - circuit breaker protection
    - deterministic backend selection
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
        self._base_url = str(URL(base_url).with_path("").with_query(""))
        self._timeout = ClientTimeout(total=timeout)

        self._close_session = close_session

        self._sid: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._rpc_id = 1

        # locks (HA safe concurrency model)
        self._auth_lock = asyncio.Lock()
        self._rpc_lock = asyncio.Lock()
        self._singleflight_lock = asyncio.Lock()

        # circuit breaker
        self._circuit = CircuitBreaker()

        # session health
        self._last_success = 0.0

        # backend cache
        self._mode: Optional[str] = None

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
    # BACKEND DETECTION (stable + cached)
    # =====================================================

    async def _detect_backend(self):
        if self._mode:
            return

        gl = 0
        luci = 0

        try:
            r = await self._post("/rpc", {
                "jsonrpc": "2.0",
                "id": self._rpc_id,
                "method": "challenge",
                "params": {"username": "root"},
            })
            if isinstance(r.get("result"), dict):
                gl += 1
        except Exception:
            pass

        try:
            r = await self._post("/cgi-bin/luci/rpc/auth", {
                "method": "login",
                "params": ["root", "test"],
                "id": self._rpc_id,
            })
            if isinstance(r, dict) and "result" in r:
                luci += 1
        except Exception:
            pass

        self._mode = "luci" if luci >= gl else "gl"

    # =====================================================
    # AUTH HASHING (gli4py-compatible minimal set)
    # =====================================================

    def _hash(self, username: str, password: str, salt: str, nonce: str) -> str:
        a = hashlib.md5((password + salt).encode()).hexdigest()
        return hashlib.md5(f"{username}:{a}:{nonce}".encode()).hexdigest()

    # =====================================================
    # HTTP CORE (split auth vs rpc)
    # =====================================================

    async def _post(self, path: str, payload: dict) -> dict:
        url = str(URL(self._base_url) / path.lstrip("/"))

        try:
            async with self._session.post(
                url,
                json=payload,
                timeout=self._timeout,
            ) as resp:

                text = await resp.text()

                if resp.status >= 400:
                    raise GlinetConnectionError(text[:200])

                try:
                    return await resp.json(content_type=None)
                except Exception:
                    return json.loads(text or "{}")

        except asyncio.TimeoutError as e:
            raise GlinetTimeoutError() from e
        except ClientError as e:
            raise GlinetConnectionError(str(e)) from e

    # =====================================================
    # SID VALIDATION (strict)
    # =====================================================

    async def _validate_sid(self, sid: str) -> bool:
        try:
            r = await self._rpc_call("system", "board", sid=sid)
            return isinstance(r, dict) and r != {}
        except Exception:
            return False

    # =====================================================
    # LOGIN (single-flight + backoff safe)
    # =====================================================

    async def login(self, username: str, password: str) -> AuthResult:
        async with self._auth_lock:

            if self._healthy():
                return {"sid": self._sid, "mode": self._mode}

            self._username = username
            self._password = password

            await self._detect_backend()

            for attempt in range(3):
                sid = await self._try_login(username, password)

                if sid and await self._validate_sid(sid):
                    self._sid = sid
                    self._touch()
                    return {"sid": sid, "mode": self._mode}

                await asyncio.sleep(2 ** attempt)

            self._circuit.record_failure()
            raise GlinetAuthError("Login failed")

    async def _try_login(self, username: str, password: str) -> Optional[str]:

        if self._mode == "luci":
            r = await self._post("/cgi-bin/luci/rpc/auth", {
                "method": "login",
                "params": [username, password],
                "id": self._rpc_id,
            })
            return self._extract_sid(r)

        # GL mode
        challenge = await self._post("/rpc", {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": "challenge",
            "params": {"username": username},
        })

        res = challenge.get("result") or {}
        salt = res.get("salt")
        nonce = res.get("nonce")

        if not salt or not nonce:
            return None

        hashval = self._hash(username, password, salt, nonce)

        r = await self._post("/rpc", {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": "login",
            "params": {"username": username, "hash": hashval},
        })

        return self._extract_sid(r)

    # =====================================================
    # SID EXTRACTION
    # =====================================================

    def _extract_sid(self, resp: dict) -> Optional[str]:
        if not isinstance(resp, dict):
            return None

        r = resp.get("result")

        if isinstance(r, str):
            return r

        if isinstance(r, dict):
            return r.get("sid") or r.get("token")

        return None

    # =====================================================
    # RPC CALL (single-flight + auth recovery)
    # =====================================================

    async def rpc(self, namespace: str, method: str, params: dict | None = None):
        async with self._rpc_lock:

            await self.ensure_session()

            return await self._rpc_call(namespace, method, params=params)

    async def _rpc_call(
        self,
        namespace: str,
        method: str,
        *,
        sid: Optional[str] = None,
        params: dict | None = None,
    ):

        sid = sid or self._sid

        payload = {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": "call",
            "params": [sid, namespace, method, params or {}],
        }

        r = await self._post("/rpc", payload)

        if isinstance(r, dict) and r.get("error"):
            self._circuit.record_failure()

            if "access denied" in str(r["error"]).lower():
                self._sid = None
                await self.ensure_session()
                return await self._rpc_call(namespace, method, params=params)

            raise GlinetApiError(r["error"])

        self._touch()
        return r.get("result")

    # =====================================================
    # SESSION MANAGEMENT
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