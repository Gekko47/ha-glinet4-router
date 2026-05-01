from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, API_PATH
from .services import async_setup_services
from .glinet_aiohttp_client import GLinetClient

from .fast_coordinator import GlinetFastCoordinator
from .slow_coordinator import GlinetSlowCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "switch", "button"]


# =========================================================
# HELPERS
# =========================================================
def normalize_host(host: str) -> str:
    return (host or "").strip().replace("http://", "").replace("https://", "")


# =========================================================
# GLOBAL SETUP
# =========================================================
async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await async_setup_services(hass)
    return True


# =========================================================
# ENTRY SETUP
# =========================================================
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:

    hass.data.setdefault(DOMAIN, {})

    host = normalize_host(entry.data["host"])

    # =====================================================
    # API CLIENT
    # =====================================================
    api = GLinetClient(
        session=async_get_clientsession(hass),
        base_url=f"http://{host}{API_PATH}",
    )

    # =====================================================
    # COORDINATORS
    # =====================================================
    fast_coordinator = GlinetFastCoordinator(hass, api)
    slow_coordinator = GlinetSlowCoordinator(hass, api)

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "fast_coordinator": fast_coordinator,
        "slow_coordinator": slow_coordinator,
    }

    # =====================================================
    # INITIAL REFRESH (FAST FIRST)
    # =====================================================
    try:
        await fast_coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.exception("Fast coordinator initial refresh failed")

    try:
        await slow_coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.exception("Slow coordinator initial refresh failed")

    # =====================================================
    # DEVICE REGISTRY (SAFE FALLBACK STRATEGY)
    # =====================================================
    system_info = (fast_coordinator.data or {}).get("system_info") or {}

    mac = (
        system_info.get("mac")
        or (slow_coordinator.data or {}).get("system_info", {}).get("mac")
        or host
    )

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, mac)},
        manufacturer="GL.iNet",
        model=system_info.get("model", "Router"),
        name=f"GL.iNet Router ({host})",
        sw_version=system_info.get("firmware_version"),
    )

    # =====================================================
    # PLATFORMS
    # =====================================================
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


# =========================================================
# ENTRY UNLOAD
# =========================================================
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

        if data:
            api = data.get("api")
            if api:
                await api.close()

            # IMPORTANT: explicitly stop coordinators
            fast = data.get("fast_coordinator")
            slow = data.get("slow_coordinator")

            # safe shutdown if running tasks exist
            for c in (fast, slow):
                if hasattr(c, "async_stop"):
                    try:
                        await c.async_stop()
                    except Exception:
                        _LOGGER.debug("Coordinator shutdown failed")

    return unload_ok