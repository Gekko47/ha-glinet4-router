from homeassistant.components.diagnostics import async_redact_data

TO_REDACT = {"password", "mac", "ip"}


async def async_get_config_entry_diagnostics(hass, entry):
    data = hass.data["glinet"][entry.entry_id]

    return async_redact_data(
        {
            "config": dict(entry.data),
            "data": data["coordinator"].data,
        },
        TO_REDACT,
    )