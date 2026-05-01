"""Config flow for GL.iNet integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.zeroconf import ZeroconfServiceInfo


from gli4py import GLinet
from gli4py.error_handling import NonZeroResponse
from uplink import AiohttpClient

from .const import DOMAIN, API_PATH, DEFAULT_HOST, DEFAULT_USERNAME, DEFAULT_PASSWORD

_LOGGER = logging.getLogger(__name__)

CONF_MAC = "mac"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): selector.TextSelector(),
        vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)



class CannotConnect(HomeAssistantError):
    pass


class InvalidAuth(HomeAssistantError):
    pass


class TestingHub:
    """GL.iNet connection test using gli4py."""

    def __init__(self, host: str, username: str, hass: HomeAssistant) -> None:
        self.router = GLinet(
            base_url=host + API_PATH,
            client=AiohttpClient(session=async_get_clientsession(hass)),
            sync=False,
        )

        self.username = username
        self.mac = ""
        self.model = ""

    async def connect(self) -> bool:
        try:
            return await self.router.router_reachable(self.username)
        except Exception as e:
            _LOGGER.warning("Connect failed: %s", e)
            return False

    async def authenticate(self, password: str) -> bool:
        try:
            await self.router.login(self.username, password)
            info = await self.router.router_info()

            self.mac = info.get("mac", "")
            self.model = info.get("model", "GL.iNet")

            return True

        except NonZeroResponse:
            return False
        except Exception as e:
            _LOGGER.warning("Auth error: %s", e)
            return False


async def validate_input(data: dict[str, Any], hass: HomeAssistant) -> dict[str, Any]:
    hub = TestingHub(
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        hass=hass,
    )

    if not await hub.connect():
        raise CannotConnect

    if not await hub.authenticate(data[CONF_PASSWORD]):
        raise InvalidAuth

    return {
        "title": f"GL.iNet ({hub.model})",
        CONF_MAC: hub.mac,
        "data": data,
    }


class GlinetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle GL.iNet config flow."""

    VERSION = 1

    async def async_step_zeroconf(self, discovery_info):
        """Handle Zeroconf discovery."""

        hostname = (discovery_info.hostname or "").lower()

        # Filter: only likely GL.iNet devices
        if "gl" not in hostname:
            return self.async_abort(reason="not_glinet")

        return await self.async_step_user(
            {
                CONF_HOST: discovery_info.host,
            }
        )
        
    
    def _normalize_mac(mac: str) -> str:
        """Normalize MAC address for unique_id usage."""
        if not mac:
            return ""
        return mac.lower().replace(":", "").replace("-", "")

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(user_input, self.hass)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as e:
                _LOGGER.exception("Unexpected error: %s", e)
                errors["base"] = "unknown"

            else:
                unique_id = _normalize_mac(info.get(CONF_MAC)) or user_input[CONF_HOST]

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=info["data"],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )