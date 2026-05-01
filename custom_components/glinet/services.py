from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


async def async_setup_services(hass: HomeAssistant):
    async def reboot_router(call: ServiceCall):
        host = call.data.get("host")

        if not host or host not in hass.data[DOMAIN]:
            raise HomeAssistantError("Router not found")

        api = hass.data[DOMAIN][host]["api"]

        try:
            await api.reboot()  # depends on gli4py support
        except Exception as e:
            raise HomeAssistantError(f"Failed to reboot router: {e}")

    hass.services.async_register(
        DOMAIN,
        "reboot_router",
        reboot_router,
    )


async def async_unload_services(hass: HomeAssistant):
    hass.services.async_remove(DOMAIN, "reboot_router")