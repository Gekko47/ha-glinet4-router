from __future__ import annotations

import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN, API_PATH
from .services import async_setup_services, async_unload_services
from .glinet_aiohttp_client import GLinetClient
from .fast_coordinator import GlinetFastCoordinator
from .slow_coordinator import GlinetSlowCoordinator
from .options_flow import GlinetOptionsFlow

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "switch", "button"]

STORE_VERSION = 1
STORE_KEY = "glinet_auth_store"
CONFIG_VERSION = 1


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
# AUTH BROKER (SINGLE SOURCE OF TRUTH)
# =========================================================
class GlinetAuthBroker:
    """
    Handles:
    - login lifecycle
    - SID persistence
    - SID validation
    - safe recovery after HA restart or router reboot
    """

    def __init__(self, hass: HomeAssistant, api: GLinetClient, entry_id: str):
        self.hass = hass
        self.api = api
        self.entry_id = entry_id

        self._lock = asyncio.Lock()
        self.store = Store(hass, STORE_VERSION, f"{STORE_KEY}_{entry_id}")

        self.username: str | None = None
        self.password: str | None = None

    # -----------------------------------------------------
    async def set_credentials(self, username: str, password: str):
        self.username = username
        self.password = password

    # -----------------------------------------------------
    async def load_sid(self) -> bool:
        """Restore SID and validate it safely."""
        data = await self.store.async_load()
        if not data or "sid" not in data:
            return False

        self.api.sid = data["sid"]

        try:
            if await self.api.async_validate_session():
                _LOGGER.debug("Restored valid SID")
                return True
        except Exception:
            pass

        _LOGGER.debug("Stored SID invalid, clearing")
        self.api.sid = None

        try:
            await self.store.async_delete()
        except Exception:
            _LOGGER.debug("Failed to delete invalid SID store")

        return False

    # -----------------------------------------------------
    async def save_sid(self):
        if self.api.sid:
            await self.store.async_save({"sid": self.api.sid})

    # -----------------------------------------------------
    async def login(self):
        """Performs fresh login using stored credentials."""
        if not self.username or not self.password:
            raise RuntimeError("Missing credentials")

        await self.api.login(self.username, self.password)
        await self.save_sid()

    # -----------------------------------------------------
    async def ensure(self):
        """
        Single entrypoint for authentication.
        Fully concurrency-safe.
        """
        async with self._lock:
            if self.api.sid:
                return

            if await self.load_sid():
                return

            await self.login()


# =========================================================
# MIGRATION
# =========================================================
async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to new version."""
    _LOGGER.debug("Migrating from version %s", entry.version)

    if entry.version == 1:
        # Future migrations go here
        pass

    hass.config_entries.async_update_entry(entry, version=CONFIG_VERSION)

    _LOGGER.info("Migration complete, new version: %s", entry.version)
    return True


# =========================================================
# ENTRY SETUP
# =========================================================
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    host = normalize_host(entry.data["host"])
    session = async_get_clientsession(hass)

    # Register options flow update listener
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    # Initialize options with defaults if not present
    if not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={
                "fast_interval": 30,
                "slow_interval": 300,
                "timeout": 10,
            },
        )

    # Get intervals from options
    fast_interval = entry.options.get("fast_interval", 30)
    slow_interval = entry.options.get("slow_interval", 300)
    timeout = entry.options.get("timeout", 10)

    # API CLIENT
    api = GLinetClient(
        session=session,
        base_url=f"http://{host}{API_PATH}",
        timeout=timeout,
    )

    # AUTH BROKER
    auth = GlinetAuthBroker(hass, api, entry.entry_id)

    await auth.set_credentials(
        entry.data["username"],
        entry.data["password"],
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "auth": auth,
    }

    # AUTH INITIALIZATION (RESTORE OR LOGIN)
    try:
        await auth.ensure()
    except Exception as e:
        _LOGGER.exception("GL.iNet authentication failed: %s", e)
        return False

    # COORDINATORS (with configurable intervals from options)
    fast = GlinetFastCoordinator(hass, api, interval=fast_interval)
    slow = GlinetSlowCoordinator(hass, api, interval=slow_interval)

    hass.data[DOMAIN][entry.entry_id].update(
        {
            "fast_coordinator": fast,
            "slow_coordinator": slow,
        }
    )

    # -----------------------------------------------------
    # INITIAL DATA LOAD
    # -----------------------------------------------------
    await asyncio.gather(
        fast.async_config_entry_first_refresh(),
        slow.async_config_entry_first_refresh(),
        return_exceptions=True,
    )

    # -----------------------------------------------------
    # DEVICE REGISTRY
    # -----------------------------------------------------
    system_info = (fast.data or {}).get("system_info") or {}

    mac = system_info.get("mac") or system_info.get("hwaddr") or host

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, mac)},
        manufacturer="GL.iNet",
        model=system_info.get("model", "Router"),
        name=f"GL.iNet Router ({host})",
        sw_version=system_info.get("firmware_version"),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("GL.iNet integration ready (robust SID persistence enabled)")

    return True


# =========================================================
# OPTIONS UPDATE LISTENER
# =========================================================
async def async_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


# =========================================================
# UNLOAD
# =========================================================
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if unload_ok and data:
        for key in ("fast_coordinator", "slow_coordinator"):
            coord = data.get(key)
            if coord and hasattr(coord, "async_stop"):
                try:
                    await coord.async_stop()
                except Exception:
                    _LOGGER.debug("%s shutdown failed", key)

        api = data.get("api")
        if api:
            try:
                await api.close()
            except Exception:
                _LOGGER.debug("API close failed")

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)
        await async_unload_services(hass)

    return unload_ok