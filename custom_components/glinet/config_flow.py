"""GL.iNet Config Flow (HA 2026.4 - Zeroconf + Reauth + hardened validation)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from aiohttp import ClientConnectorError, ClientResponseError, ClientError

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, API_PATH
from .glinet_aiohttp_client import GLinetClient
from .options_flow import GlinetOptionsFlow

_LOGGER = logging.getLogger(__name__)


# =========================================================
# HELPERS
# =========================================================
def normalize_host(host: str) -> str:
    """Standardise router host input."""
    return (host or "").strip().replace("http://", "").replace("https://", "").lower()


def build_schema(default_host: str | None = None):
    """Single schema generator (prevents duplication bugs)."""

    return vol.Schema(
        {
            vol.Optional(CONF_HOST, default=default_host or ""): selector.TextSelector(),
            vol.Required(CONF_USERNAME): selector.TextSelector(),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.PASSWORD
                )
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


# =========================================================
# VALIDATION (SOURCE OF TRUTH)
# =========================================================
async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate router credentials and fetch system info."""

    host = normalize_host(data.get(CONF_HOST, ""))

    if not host:
        raise CannotConnect("Host is required")

    api = GLinetClient(
        session=async_get_clientsession(hass),
        base_url=f"http://{host}{API_PATH}",
    )

    try:
        await api.login(data[CONF_USERNAME], data[CONF_PASSWORD])
        info = await api.async_get_system_info()   # ✅ FIXED

    except ClientResponseError as e:
        if e.status in (401, 403):
            raise InvalidAuth("Invalid credentials") from e
        raise CannotConnect("Router rejected request") from e

    except (ClientConnectorError, ClientError) as e:
        raise CannotConnect("Router unreachable") from e

    except Exception:
        _LOGGER.exception("Unexpected router error")
        raise InvalidResponse("Invalid router response") from None

    if not isinstance(info, dict):
        raise InvalidResponse("Invalid system response")

    mac = (info.get("mac") or "").lower().strip()

    return {
        "title": f"GL.iNet ({info.get('model', 'Router')})",
        "model": info.get("model", "GL.iNet"),
        "mac": mac,
        "host": host,
    }


# =========================================================
# CONFIG FLOW
# =========================================================
class GlinetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """GL.iNet router config flow (Zeroconf + Reauth)."""

    VERSION = 1

    options_flow_handler = GlinetOptionsFlow

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    # -----------------------------------------------------
    # USER FLOW
    # -----------------------------------------------------
    async def async_step_user(self, user_input=None):
        return await self.async_step_auth()

    # -----------------------------------------------------
    # ZEROCONF
    # -----------------------------------------------------
    async def async_step_zeroconf(self, discovery_info: dict[str, Any]):
        host = discovery_info.get("ip_address") or discovery_info.get("host")

        if not host:
            return self.async_abort(reason="no_devices_found")

        self._discovered_host = normalize_host(str(host))

        # Try to get MAC for uniqueness check early
        try:
            session = async_get_clientsession(self.hass)
            api = GLinetClient(
                session=session,
                base_url=f"http://{self._discovered_host}{API_PATH}",
            )
            # Attempt basic connection without auth to get MAC
            info = {"host": self._discovered_host}
            unique_id = self._discovered_host
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
        except Exception:
            pass

        return await self.async_step_auth()

    # -----------------------------------------------------
    # AUTH STEP
    # -----------------------------------------------------
    async def async_step_auth(self, user_input=None):
        errors = {}

        schema = build_schema(self._discovered_host)

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

            except InvalidAuth:
                errors["base"] = "invalid_auth"

            except CannotConnect:
                errors["base"] = "cannot_connect"

            except InvalidResponse:
                errors["base"] = "unknown"

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
                        CONF_HOST: normalize_host(user_input.get(CONF_HOST, self._discovered_host or "")),
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="auth",
            data_schema=schema,
            errors=errors,
        )

    # -----------------------------------------------------
    # REAUTH FLOW
    # -----------------------------------------------------
    async def async_step_reauth(self, entry_data: dict[str, Any]):
        entry_id = self.context.get("entry_id")

        if entry_id:
            self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)

        if not self._reauth_entry:
            return self.async_abort(reason="no_entry")

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

            except InvalidAuth:
                errors["base"] = "invalid_auth"

            except CannotConnect:
                errors["base"] = "cannot_connect"

            except InvalidResponse:
                errors["base"] = "unknown"

            except Exception:
                _LOGGER.exception("Unexpected reauth error")
                errors["base"] = "unknown"

            else:
                if not self._reauth_entry:
                    return self.async_abort(reason="no_entry")

                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        CONF_HOST: normalize_host(user_input.get(CONF_HOST, "")),
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )

                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=build_schema(),
            errors=errors,
        )