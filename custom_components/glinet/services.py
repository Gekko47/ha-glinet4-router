"""Services for GL.iNet router integration."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN

# Service schemas
ADD_PORT_FORWARDING_SCHEMA = vol.Schema({
    vol.Required("host"): cv.string,
    vol.Required("external_port"): cv.port,
    vol.Required("internal_ip"): cv.string,
    vol.Required("internal_port"): cv.port,
    vol.Required("protocol", default="tcp"): vol.In(["tcp", "udp", "both"]),
    vol.Optional("description"): cv.string,
})

REMOVE_PORT_FORWARDING_SCHEMA = vol.Schema({
    vol.Required("host"): cv.string,
    vol.Required("rule_id"): cv.string,
})

SET_DNS_SERVERS_SCHEMA = vol.Schema({
    vol.Required("host"): cv.string,
    vol.Required("primary"): cv.string,
    vol.Required("secondary"): cv.string,
})

ADD_STATIC_LEASE_SCHEMA = vol.Schema({
    vol.Required("host"): cv.string,
    vol.Required("mac"): cv.string,
    vol.Required("ip"): cv.string,
    vol.Required("hostname"): cv.string,
})

REMOVE_STATIC_LEASE_SCHEMA = vol.Schema({
    vol.Required("host"): cv.string,
    vol.Required("mac"): cv.string,
})

SET_DHCP_CONFIG_SCHEMA = vol.Schema({
    vol.Required("host"): cv.string,
    vol.Optional("lease_time"): cv.positive_int,
    vol.Optional("start_ip"): cv.string,
    vol.Optional("end_ip"): cv.string,
    vol.Optional("gateway"): cv.string,
    vol.Optional("subnet_mask"): cv.string,
})


async def async_setup_services(hass: HomeAssistant):
    """Set up services for GL.iNet router integration."""

    async def handle_add_port_forwarding(call: ServiceCall):
        """Handle adding a port forwarding rule."""
        host = call.data["host"]
        if host not in hass.data[DOMAIN]:
            raise ValueError(f"GL.iNet router {host} not found")

        api = hass.data[DOMAIN][host]["api"]
        rule = {
            "external_port": call.data["external_port"],
            "internal_ip": call.data["internal_ip"],
            "internal_port": call.data["internal_port"],
            "protocol": call.data["protocol"],
            "description": call.data.get("description", ""),
        }

        try:
            await api.async_add_port_forwarding(rule)
            # Refresh coordinator data
            coordinator = hass.data[DOMAIN][host]["coordinator"]
            await coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to add port forwarding rule: {e}")

    async def handle_remove_port_forwarding(call: ServiceCall):
        """Handle removing a port forwarding rule."""
        host = call.data["host"]
        if host not in hass.data[DOMAIN]:
            raise ValueError(f"GL.iNet router {host} not found")

        api = hass.data[DOMAIN][host]["api"]
        rule_id = call.data["rule_id"]

        try:
            await api.async_delete_port_forwarding(rule_id)
            # Refresh coordinator data
            coordinator = hass.data[DOMAIN][host]["coordinator"]
            await coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to remove port forwarding rule: {e}")

    async def handle_set_dns_servers(call: ServiceCall):
        """Handle setting DNS servers."""
        host = call.data["host"]
        if host not in hass.data[DOMAIN]:
            raise ValueError(f"GL.iNet router {host} not found")

        api = hass.data[DOMAIN][host]["api"]
        servers = [
            call.data["primary"],
            call.data["secondary"]
        ]

        try:
            await api.async_set_dns_servers(servers)
            # Refresh coordinator data
            coordinator = hass.data[DOMAIN][host]["coordinator"]
            await coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to set DNS servers: {e}")

    async def handle_add_static_lease(call: ServiceCall):
        """Handle adding a static DHCP lease."""
        host = call.data["host"]
        if host not in hass.data[DOMAIN]:
            raise ValueError(f"GL.iNet router {host} not found")

        api = hass.data[DOMAIN][host]["api"]
        lease = {
            "mac": call.data["mac"],
            "ip": call.data["ip"],
            "hostname": call.data["hostname"],
        }

        try:
            await api.async_add_static_lease(lease)
            # Refresh coordinator data
            coordinator = hass.data[DOMAIN][host]["coordinator"]
            await coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to add static lease: {e}")

    async def handle_remove_static_lease(call: ServiceCall):
        """Handle removing a static DHCP lease."""
        host = call.data["host"]
        if host not in hass.data[DOMAIN]:
            raise ValueError(f"GL.iNet router {host} not found")

        api = hass.data[DOMAIN][host]["api"]
        mac = call.data["mac"]

        try:
            await api.async_delete_static_lease(mac)
            # Refresh coordinator data
            coordinator = hass.data[DOMAIN][host]["coordinator"]
            await coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to remove static lease: {e}")

    async def handle_set_dhcp_config(call: ServiceCall):
        """Handle setting DHCP configuration."""
        host = call.data["host"]
        if host not in hass.data[DOMAIN]:
            raise ValueError(f"GL.iNet router {host} not found")

        api = hass.data[DOMAIN][host]["api"]
        config = {}

        if "lease_time" in call.data:
            config["lease_time"] = call.data["lease_time"]
        if "start_ip" in call.data:
            config["start_ip"] = call.data["start_ip"]
        if "end_ip" in call.data:
            config["end_ip"] = call.data["end_ip"]
        if "gateway" in call.data:
            config["gateway"] = call.data["gateway"]
        if "subnet_mask" in call.data:
            config["subnet_mask"] = call.data["subnet_mask"]

        try:
            await api.async_set_dhcp_settings(config)
            # Refresh coordinator data
            coordinator = hass.data[DOMAIN][host]["coordinator"]
            await coordinator.async_request_refresh()
        except Exception as e:
            raise ValueError(f"Failed to set DHCP configuration: {e}")

    # Register services
    hass.services.async_register(
        DOMAIN, "add_port_forwarding", handle_add_port_forwarding,
        schema=ADD_PORT_FORWARDING_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "remove_port_forwarding", handle_remove_port_forwarding,
        schema=REMOVE_PORT_FORWARDING_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "set_dns_servers", handle_set_dns_servers,
        schema=SET_DNS_SERVERS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "add_static_lease", handle_add_static_lease,
        schema=ADD_STATIC_LEASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "remove_static_lease", handle_remove_static_lease,
        schema=REMOVE_STATIC_LEASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "set_dhcp_config", handle_set_dhcp_config,
        schema=SET_DHCP_CONFIG_SCHEMA
    )


async def async_unload_services(hass: HomeAssistant):
    """Unload services for GL.iNet router integration."""
    services_to_remove = [
        "add_port_forwarding",
        "remove_port_forwarding",
        "set_dns_servers",
        "add_static_lease",
        "remove_static_lease",
        "set_dhcp_config",
    ]

    for service in services_to_remove:
        hass.services.async_remove(DOMAIN, service)