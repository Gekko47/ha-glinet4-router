"""Services for GL.iNet router integration."""

from homeassistant.core import HomeAssistant


async def async_setup_services(hass: HomeAssistant):
    """No router services are supported by the current GL.iNet API."""
    return


async def async_unload_services(hass: HomeAssistant):
    """No services to unload."""
    return