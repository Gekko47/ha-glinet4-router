import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST

from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD


DEFAULT_USER = "root"
DEFAULT_PASS = "goodlife"


class GlinetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.host = None
        self.username = None
        self.password = None

    # ---------------------------------------------------
    # 1. ZEROCONF DISCOVERY ENTRY POINT
    # ---------------------------------------------------
    async def async_step_zeroconf(self, discovery_info):
        """
        Triggered automatically when GL.iNet is found on network.
        """
        self.host = discovery_info.get("host") or discovery_info.get("ip")

        await self.async_set_unique_id(self.host)
        self._abort_if_unique_id_configured()

        return await self.async_step_user()

    # ---------------------------------------------------
    # 2. USER INPUT STEP (credentials)
    # ---------------------------------------------------
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self.host = user_input[CONF_HOST]
            self.username = user_input[CONF_USERNAME]
            self.password = user_input[CONF_PASSWORD]

            # VALIDATE BEFORE CONTINUING
            return await self.async_step_validate()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self.host or "192.168.8.1"): str,
                vol.Required(CONF_USERNAME, default=DEFAULT_USER): str,
                vol.Required(CONF_PASSWORD, default=DEFAULT_PASS): str,
            }),
        )

    # ---------------------------------------------------
    # 3. CONNECTION VALIDATION STEP (NEW)
    # ---------------------------------------------------
    async def async_step_validate(self, user_input=None):
        errors = {}

        from .api import GlinetAPI

        api = GlinetAPI(self.host, self.username, self.password)

        try:
            await api.async_connect()

            # test real call
            await api.async_get_status()

        except Exception:
            errors["base"] = "auth_failed"
            return await self.async_step_user()

        finally:
            await api.async_close()

        return self.async_create_entry(
            title=f"GL.iNet Router ({self.host})",
            data={
                CONF_HOST: self.host,
                CONF_USERNAME: self.username,
                CONF_PASSWORD: self.password,
            },
        )

    # ---------------------------------------------------
    # 4. MANUAL ENTRY FALLBACK
    # ---------------------------------------------------
    async def async_step_import(self, user_input):
        return await self.async_step_user(user_input)