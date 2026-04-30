"""Config flow for GL.iNet router integration."""

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.device_tracker import (
    CONF_CONSIDER_HOME,
    DEFAULT_CONSIDER_HOME,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN, CONF_MAC
from .utils import adjust_mac

from gli_py import GLinet
from gli_py.error_handling import AuthenticationError, NonZeroResponse

_LOGGER = logging.getLogger(__name__)

DEFAULT_USER = "root"
DEFAULT_PASS = "goodlife"


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME, default=DEFAULT_USER): selector.TextSelector(),
        vol.Required(CONF_HOST, default="192.168.8.1"): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
        vol.Required(CONF_PASSWORD, default=DEFAULT_PASS): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(
            CONF_CONSIDER_HOME, default=DEFAULT_CONSIDER_HOME.total_seconds()
        ): vol.All(vol.Coerce(int), vol.Clamp(min=0, max=900)),
    }
)


class TestingHub:
    """Testing class to test connection and authentication."""

    def __init__(self, username: str, host: str, hass: HomeAssistant) -> None:
        """Initialize."""
        self.host = host
        self.username = username
        self.hass = hass
        self.router_mac = ""
        self.router_model = ""

    async def connect(self) -> bool:
        """Test if we can communicate with the host."""
        try:
            client = GLinet(self.host, self.username, "dummy")
            await client.connect()
            return True
        except asyncio.TimeoutError:
            _LOGGER.warning("Connection to %s timed out", self.host)
            return False
        except Exception as e:
            _LOGGER.warning("Failed to connect to %s: %s", self.host, e)
            return False

    async def authenticate(self, password: str) -> bool:
        """Test if we can authenticate with the host."""
        try:
            client = GLinet(self.host, self.username, password)
            await client.connect()
            # Test a simple API call
            status = await client.get_status()
            return True
        except asyncio.TimeoutError:
            _LOGGER.warning("Authentication to %s timed out", self.host)
            return False
        except Exception as e:
            _LOGGER.warning("Failed to authenticate with %s: %s", self.host, e)
            return False


async def validate_input(data: dict[str, Any], hass: HomeAssistant) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    hub = TestingHub(data[CONF_USERNAME], data[CONF_HOST], hass)

    if not await hub.connect():
        raise CannotConnect

    if not await hub.authenticate(data[CONF_PASSWORD]):
        raise InvalidAuth

    # Get router info for unique ID
    client = GLinet(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD])
    await client.connect()
    status = await client.get_status()
    await client.close()

    router_mac = status.get("mac", "")
    router_model = status.get("model", "Router")

    return {
        "title": f"GL.iNet Router ({data[CONF_HOST]})",
        CONF_MAC: router_mac,
        "model": router_model,
        "data": {
            CONF_HOST: data[CONF_HOST],
            CONF_USERNAME: data[CONF_USERNAME],
            CONF_PASSWORD: data[CONF_PASSWORD],
        },
    }
class GlinetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GL.iNet router."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._discovered_data = None

    async def async_step_zeroconf(self, discovery_info):
        """Handle Zeroconf discovery."""
        host = discovery_info.get("host") or discovery_info.get("ip")
        if not host:
            return self.async_abort(reason="no_host")

        # Set unique ID based on host
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()

        # Store discovered data for pre-filling
        self._discovered_data = {
            CONF_HOST: f"http://{host}" if not host.startswith("http") else host,
            CONF_USERNAME: DEFAULT_USER,
            CONF_PASSWORD: DEFAULT_PASS,
        }

        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(user_input, self.hass)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as e:
                _LOGGER.exception("Unexpected exception during setup: %s", e)
                errors["base"] = "unknown"
            else:
                # Use router MAC as unique ID if available
                unique_id = info.get(CONF_MAC, user_input[CONF_HOST])
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=info["data"],
                )

        # Pre-fill with discovered data if available
        defaults = user_input or self._discovered_data or {}

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, defaults
            ),
            errors=errors,
        )

    async def async_step_import(self, user_input):
        """Handle import from configuration.yaml."""
        return await self.async_step_user(user_input)