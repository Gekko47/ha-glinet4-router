"""GL.iNet Config Flow (HA 2026.4 - Production Hardened)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from aiohttp import (
    ClientConnectorError,
    ClientResponseError,
    ClientError,
)

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, API_PATH
from .glinet_aiohttp_client import (
    GLinetClient,
    GlinetAuthError,
    GlinetConnectionError,
)
from .options_flow import GlinetOptionsFlow

_LOGGER = logging.getLogger(__name__)


# =========================================================
# DEFAULTS
# =========================================================
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = "goodlife"
DEFAULT_HOST = "192.168.8.1"


# =========================================================
# HELPERS
# =========================================================
def normalize_host(host: str) -> str:
    return (host or "").strip().replace("http://", "").replace("https://", "").lower()


def normalize_username(username: str) -> str:
    return (username or "").strip()


def build_auth_schema(default_host: str | None = None):
    return vol.Schema(
        {
            vol.Optional(CONF_HOST, default=default_host or DEFAULT_HOST): selector.TextSelector(),
            vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): selector.TextSelector(),
            vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


# =========================================================
# ERRORS
# =========================================================
class CannotConnect(HomeAssistantError):
    pass


class InvalidAuth(HomeAssistantError):
    pass


class InvalidResponse(HomeAssistantError):
    pass


class HostRequired(HomeAssistantError):
    pass


# =========================================================
# VALIDATION
# =========================================================
async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    host = normalize_host(data.get(CONF_HOST, ""))
    username = normalize_username(data.get(CONF_USERNAME))
    password = data.get(CONF_PASSWORD) or ""

    if not host:
        raise HostRequired

    if not username or not password:
        raise InvalidAuth

    _LOGGER.debug(
        "GL.iNet login attempt host=%s username='%s' len=%d password_len=%d",
        host,
        username,
        len(username),
        len(password),
    )

    api = GLinetClient(
        session=async_get_clientsession(hass),
        base_url=f"http://{host}{API_PATH}",
    )

    try:
        # ---- AUTH ----
        await api.login(username, password)

        # ---- VERIFY API ----
        info = await api.async_get_system_info()

    # -----------------------------
    # AUTH FAILURES
    # -----------------------------
    except GlinetAuthError as e:
        _LOGGER.debug("Auth failed for %s: %s", host, e)
        raise InvalidAuth from e

    # -----------------------------
    # HTTP RESPONSE (must come early)
    # -----------------------------
    except ClientResponseError as e:
        if e.status in (401, 403):
            raise InvalidAuth from e

        _LOGGER.debug("HTTP error from %s: %s", host, e)
        raise CannotConnect from e

    # -----------------------------
    # NETWORK / TRANSPORT
    # -----------------------------
    except (GlinetConnectionError, ClientConnectorError, ClientError) as e:
        _LOGGER.debug("Connection error to %s: %s", host, e)
        raise CannotConnect from e

    # -----------------------------
    # UNKNOWN / BAD API RESPONSE
    # -----------------------------
    except Exception:
        _LOGGER.exception("Unexpected router error during validation")
        raise InvalidResponse

    if not isinstance(info, dict):
        _LOGGER.debug("Invalid system info response: %s", info)
        raise InvalidResponse

    mac = (info.get("mac") or "").lower().strip()

    return {
        "title": f"GL.iNet ({info.get('model', 'Router')})",
        "model": info.get("model") or "GL.iNet",
        "mac": mac,
        "host": host,
        "username": username,
        "password": password,
    }


# =========================================================
# CONFIG FLOW
# =========================================================
class GlinetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    options_flow_handler = GlinetOptionsFlow

    def __init__(self) -> None:
        self._devices: list[dict[str, str]] = []
        self._selected_host: str | None = None

    # -----------------------------------------------------
    async def async_step_user(self, user_input=None):
        devices = self._devices

        if user_input is None and len(devices) == 0:
            self._selected_host = None

            return self.async_show_form(
                step_id="auth",
                data_schema=build_auth_schema(DEFAULT_HOST),
                description_placeholders={
                    "warning": "No GL.iNet devices were discovered. Using default router address."
                },
            )

        if user_input is None and len(devices) == 1:
            self._selected_host = devices[0]["host"]
            return await self.async_step_auth()

        options = [
            {
                "label": f"{d.get('model') or 'GL.iNet'} ({d['host']})",
                "value": d["host"],
            }
            for d in devices
        ]

        options.append({"label": "Manual setup", "value": "manual"})

        schema = vol.Schema(
            {
                vol.Required(
                    "device",
                    default=devices[0]["host"] if devices else "manual",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )

        if user_input is not None:
            choice = user_input["device"]
            self._selected_host = None if choice == "manual" else choice
            return await self.async_step_auth()

        return self.async_show_form(step_id="user", data_schema=schema)

    # -----------------------------------------------------
    async def async_step_auth(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

            except HostRequired:
                errors[CONF_HOST] = "host_required"

            except InvalidAuth:
                errors["base"] = "invalid_auth"

            except CannotConnect:
                errors["base"] = "cannot_connect"

            except InvalidResponse:
                errors["base"] = "invalid_response"

            except Exception:
                _LOGGER.exception("Unexpected config flow error")
                errors["base"] = "unknown"

            else:
                unique_id = info.get("mac") or info.get("host")

                if not unique_id:
                    unique_id = normalize_host(user_input.get(CONF_HOST, ""))

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_HOST: info["host"],
                        CONF_USERNAME: info["username"],
                        CONF_PASSWORD: info["password"],
                    },
                )

        return self.async_show_form(
            step_id="auth",
            data_schema=build_auth_schema(self._selected_host),
            errors=errors,
        )