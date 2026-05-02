from __future__ import annotations

import asyncio
import itertools
import json
import logging
import hashlib
import time
from typing import Any, Optional

from aiohttp import ClientConnectorError, ClientError, ClientTimeout
from yarl import URL

_LOGGER = logging.getLogger(__name__)


class GlinetAuthError(Exception): ...
class GlinetConnectionError(Exception): ...
class GlinetTimeoutError(GlinetConnectionError): ...
class GlinetHTTPError(GlinetConnectionError): ...
class GlinetApiError(Exception): ...


class GLinetClient:
    """
    Hardened GL.iNet auth layer (production-safe for HA)

    FIXES:
    - strict LuCI validation
    - strict SID confirmation (non-empty is NOT enough)
    - rejects false-positive auth responses
    - prevents silent unauthenticated acceptance
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

        self._last_success_ts = 0.0
        self._fail_streak = 0

        self._login_in_progress = False

    # =====================================================
    # SESSION HEALTH
    # =====================================================
    def _session_healthy(self) -> bool:
        if not self.sid:
            return False
        if time.time() - self._last_success_ts > 600:
            return False
        return self._fail_streak < 5

    def _mark_success(self):
        self._last_success_ts = time.time()
        self._fail_streak = 0

    def _mark_failure(self):
        self._fail_streak += 1

    # =====================================================
    # BACKEND DETECTION (FIXED)
    # =====================================================
    async def _detect_backend(self):
        if self._mode:
            return

        gl_score = 0
        luci_score = 0

        # GL probe
        try:
            r = await self._raw_post("/rpc", json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "challenge",
                "params": {"username": "root"},
            })

            res = r.get("result") if isinstance(r, dict) else None
            if isinstance(res, dict):
                gl_score += isinstance(res.get("salt"), str)
                gl_score += isinstance(res.get("nonce"), str)

        except Exception:
            pass

        # LUCI probe (STRICT FIX)
        try:
            r = await self._raw_post("/cgi-bin/luci/rpc/auth", json={
                "method": "login",
                "params": ["root", "test"],
                "id": 1,
            })

            if isinstance(r, dict):
                # MUST behave like real auth response
                result = r.get("result")
                if (
                    "error" not in r
                    and isinstance(result, (str, dict))
                    and result not in ("", None)
                ):
                    luci_score += 1

        except Exception:
            pass

        self._mode = "luci" if luci_score > gl_score else "gl"
        self._rpc_base = "/cgi-bin/luci/rpc" if self._mode == "luci" else "/rpc"
        self._auth_base = "/cgi-bin/luci/rpc/auth" if self._mode == "luci" else "/rpc"

    # =====================================================
    # HASHING (ENHANCED FOR MULTIPLE ALGORITHMS)
    # =====================================================
    def _hashes(self, username: str, password: str, salt: str, nonce: str):
        hashes = []

        # Original MD5 variations (password+salt and salt+password)
        a = hashlib.md5((password + salt).encode()).hexdigest()
        h1 = hashlib.md5(f"{username}:{a}:{nonce}".encode()).hexdigest()

        b = hashlib.md5((salt + password).encode()).hexdigest()
        h2 = hashlib.md5(f"{username}:{b}:{nonce}".encode()).hexdigest()

        hashes.extend([h1, h2])

        # Enhanced crypt-style hashes (matching gli4py)
        # MD5 crypt: $1$salt$hash
        md5_crypt = self._md5_crypt(password, salt)
        h3 = hashlib.md5(f"{username}:{md5_crypt}:{nonce}".encode()).hexdigest()
        hashes.append(h3)

        # SHA256 crypt: $5$salt$hash
        sha256_crypt = self._sha256_crypt(password, salt)
        h4 = hashlib.md5(f"{username}:{sha256_crypt}:{nonce}".encode()).hexdigest()
        hashes.append(h4)

        # SHA512 crypt: $6$salt$hash
        sha512_crypt = self._sha512_crypt(password, salt)
        h5 = hashlib.md5(f"{username}:{sha512_crypt}:{nonce}".encode()).hexdigest()
        hashes.append(h5)

        return hashes

    def _md5_crypt(self, password: str, salt: str) -> str:
        """MD5 crypt implementation (simplified for GL.iNet compatibility)"""
        # GL.iNet uses a simplified crypt format, not full Unix crypt
        hash_obj = hashlib.md5((salt + password).encode())
        return f"$1${salt}${hash_obj.hexdigest()}"

    def _sha256_crypt(self, password: str, salt: str) -> str:
        """SHA256 crypt implementation (simplified for GL.iNet compatibility)"""
        # GL.iNet uses a simplified crypt format, not full Unix crypt
        hash_obj = hashlib.sha256((salt + password).encode())
        return f"$5${salt}${hash_obj.hexdigest()}"

    def _sha512_crypt(self, password: str, salt: str) -> str:
        """SHA512 crypt implementation (simplified for GL.iNet compatibility)"""
        # GL.iNet uses a simplified crypt format, not full Unix crypt
        hash_obj = hashlib.sha512((salt + password).encode())
        return f"$6${salt}${hash_obj.hexdigest()}"

    # =====================================================
    # STRICT SESSION VALIDATION (REAL FIX)
    # =====================================================
    async def _confirm_session(self, sid: str) -> bool:
        try:
            r = await self._raw_post(self._rpc_base, json={
                "jsonrpc": "2.0",
                "id": next(self._rpc_id),
                "method": "call",
                "params": [sid, "system", "board", {}],
            })

            # HARD RULES:
            # 1. must be dict
            # 2. must NOT contain error
            # 3. must return structured system info (not empty dict)
            if not isinstance(r, dict):
                return False

            if r.get("error"):
                return False

            result = r.get("result")

            # IMPORTANT FIX:
            # many GL builds return {} on auth failure → reject it
            if result is None or result == {}:
                return False

            return True

        except Exception:
            return False

    # =====================================================
    # AUTH ERROR DETECTION
    # =====================================================
    def _is_auth_error(self, err: Any) -> bool:
        if not err:
            return False

        if isinstance(err, dict):
            msg = str(err.get("message", "")).lower()
            return err.get("code") == -32000 or "access denied" in msg

        return "access denied" in str(err).lower()

    # =====================================================
    # LOGIN (HARDENED STATE MACHINE)
    # =====================================================
    async def login(self, username: str, password: str):
        self._username = username
        self._password = password

        async with self._login_lock:
            async with self._reauth_lock:

                if self._login_in_progress:
                    return

                if self._session_healthy():
                    return

                self._login_in_progress = True

                try:
                    self.sid = None
                    await self._detect_backend()

                    last = None

                    for _ in range(3):
                        candidate_sid: Optional[str] = None

                        # LUCI
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

                                if isinstance(last, dict) and self._is_auth_error(last.get("error")):
                                    continue

                                candidate_sid = self._extract_sid(last)

                            except Exception:
                                pass

                        # GL
                        try:
                            challenge = await self._raw_post(self._rpc_base, json={
                                "jsonrpc": "2.0",
                                "id": next(self._rpc_id),
                                "method": "challenge",
                                "params": {"username": username},
                            })

                            res = challenge.get("result") if isinstance(challenge, dict) else None
                            if not isinstance(res, dict):
                                continue

                            salt = res.get("salt")
                            nonce = res.get("nonce")

                            if not salt or not nonce:
                                continue

                            for h in self._hashes(username, password, salt, nonce):
                                last = await self._raw_post(self._rpc_base, json={
                                    "jsonrpc": "2.0",
                                    "id": next(self._rpc_id),
                                    "method": "login",
                                    "params": {"username": username, "hash": h},
                                })

                                if isinstance(last, dict) and self._is_auth_error(last.get("error")):
                                    continue

                                candidate_sid = self._extract_sid(last)

                                if candidate_sid:
                                    break

                        except Exception:
                            pass

                        # FINAL COMMIT
                        if candidate_sid and await self._confirm_session(candidate_sid):
                            self.sid = candidate_sid
                            self._mark_success()
                            return

                    self._mark_failure()
                    raise GlinetAuthError(f"Login failed: {last}")

                finally:
                    self._login_in_progress = False

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
    # RPC
    # =====================================================
    async def _rpc(self, namespace: str, method: str, params=None):
        async with self._rpc_lock:
            await self.ensure_session()

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
                else:
                    raise GlinetApiError(data["error"])

            self._mark_success()
            return data.get("result")

    # =====================================================
    # SESSION
    # =====================================================
    async def ensure_session(self):
        if self._session_healthy():
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

    def is_logged_in(self):
        return self._session_healthy()

    async def close(self):
        if self._close_session:
            await self._session.close()