from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN
from .services import async_setup_services, async_unload_services

PLATFORMS = ["sensor", "binary_sensor", "device_tracker", "switch", "button", "select", "number", "text"]


async def async_setup(hass: HomeAssistant):
    """Set up the GL.iNet router integration."""
    await async_setup_services(hass)
    return True


async def async_unload(hass: HomeAssistant):
    """Unload the GL.iNet router integration."""
    await async_unload_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    from .api import GlinetAPI
    from .coordinator import GlinetCoordinator

    api = GlinetAPI(
        entry.data["host"],
        entry.data["username"],
        entry.data["password"],
    )

    await api.async_connect()

    coordinator = GlinetCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    # Create device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data["host"])},
        manufacturer="GL.iNet",
        model="Router",
        name=f"GL.iNet Router ({entry.data['host']})",
        sw_version=coordinator.data.get("status", {}).get("firmware_version"),
    )

    device_identifiers = (DOMAIN, entry.data["host"])

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "device_identifiers": device_identifiers,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = hass.data[DOMAIN].pop(entry.entry_id)

    await data["api"].async_close()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)