from __future__ import annotations

from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


# =========================================================
# DEVICE SYNC
# =========================================================
async def async_sync_devices(hass, entry, fast_coordinator):
    """Sync router + clients into Device Registry."""

    device_registry = dr.async_get(hass)

    data = fast_coordinator.data or {}

    clients = data.get("clients", []) or []

    # =====================================================
    # 1. ROUTER DEVICE
    # =====================================================
    system = data.get("system_info") or {}

    router_mac = system.get("mac") or entry.entry_id

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, router_mac)},
        name=f"GL.iNet Router ({system.get('model', 'Router')})",
        manufacturer="GL.iNet",
        model=system.get("model", "Router"),
        sw_version=system.get("firmware_version"),
    )

    # =====================================================
    # 2. CLIENT DEVICES
    # =====================================================
    for c in clients:
        mac = (c.get("mac") or "").lower().strip()

        if not mac:
            continue

        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, mac)},
            name=c.get("name") or c.get("hostname") or mac,
            manufacturer="GL.iNet",
            model="Client Device",
            suggested_area=c.get("interface"),
            hw_version=c.get("ip"),
        )