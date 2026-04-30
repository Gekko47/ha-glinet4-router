from gli4py import GLinet


class GlinetAPI:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.client = GLiNetClient(host)

    async def async_connect(self):
        """Persistent authenticated session."""
        await self.client.login(self.username, self.password)

    async def async_close(self):
        try:
            await self.client.close()
        except Exception:
            pass

    # ---------------- STATUS ----------------
    async def async_get_status(self):
        return await self.client.system.status()

    async def async_get_clients(self):
        return await self.client.clients.list()

    async def async_get_throughput(self):
        return await self.client.system.realtime()

    async def async_get_vpn_status(self):
        return await self.client.vpn.status()

    async def async_get_wifi(self):
        return await self.client.wifi.status()

    # NEW: Additional system information
    async def async_get_system_info(self):
        return await self.client.system.info()

    async def async_get_dhcp_leases(self):
        return await self.client.dhcp.leases()

    async def async_get_port_forwarding(self):
        return await self.client.firewall.port_forwarding()

    async def async_get_firewall_rules(self):
        return await self.client.firewall.rules()

    async def async_get_wan_status(self):
        return await self.client.network.wan()

    async def async_get_lan_status(self):
        return await self.client.network.lan()

    async def async_get_dns_settings(self):
        return await self.client.network.dns()

    async def async_get_usb_devices(self):
        return await self.client.usb.devices()

    async def async_get_logs(self):
        return await self.client.system.logs()

    async def async_get_firmware_status(self):
        return await self.client.system.firmware()

    # ---------------- CONTROL ----------------
    async def async_set_wifi(self, iface, enabled):
        """Enable or disable WiFi interface."""
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        if not iface:
            raise ValueError("interface name cannot be empty")
        return await self.client.wifi.set_enabled(iface, enabled)

    async def async_set_vpn(self, enabled):
        """Enable or disable VPN."""
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        return await self.client.vpn.start() if enabled else await self.client.vpn.stop()

    async def async_reboot(self):
        """Reboot the router."""
        return await self.client.system.reboot()

    # ---------------- ADVANCED CONTROL ----------------
    async def async_set_led(self, enabled):
        """Enable or disable router LEDs."""
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        return await self.client.system.set_led(enabled)

    async def async_set_guest_network(self, enabled):
        """Enable or disable guest network."""
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        return await self.client.wifi.set_guest_network(enabled)

    async def async_add_port_forwarding(self, rule):
        """Add a port forwarding rule."""
        required_fields = ["external_port", "internal_ip", "internal_port"]
        for field in required_fields:
            if field not in rule:
                raise ValueError(f"Missing required field: {field}")

        # Validate IP address
        import ipaddress
        try:
            ipaddress.ip_address(rule["internal_ip"])
        except ValueError:
            raise ValueError(f"Invalid internal IP address: {rule['internal_ip']}")

        # Validate ports
        if not (1 <= rule["external_port"] <= 65535):
            raise ValueError(f"Invalid external port: {rule['external_port']}")
        if not (1 <= rule["internal_port"] <= 65535):
            raise ValueError(f"Invalid internal port: {rule['internal_port']}")

        return await self.client.firewall.add_port_forwarding(rule)

    async def async_delete_port_forwarding(self, rule_id):
        """Delete a port forwarding rule."""
        if not rule_id:
            raise ValueError("rule_id cannot be empty")
        return await self.client.firewall.delete_port_forwarding(rule_id)

    async def async_set_dhcp_settings(self, settings):
        """Set DHCP configuration."""
        if "lease_time" in settings:
            if not isinstance(settings["lease_time"], int) or settings["lease_time"] < 1:
                raise ValueError("lease_time must be a positive integer")

        # Validate IP addresses if provided
        import ipaddress
        ip_fields = ["start_ip", "end_ip", "gateway", "subnet_mask"]
        for field in ip_fields:
            if field in settings:
                try:
                    ipaddress.ip_address(settings[field])
                except ValueError:
                    raise ValueError(f"Invalid IP address for {field}: {settings[field]}")

        return await self.client.dhcp.set_settings(settings)

    async def async_add_static_lease(self, lease):
        """Add a static DHCP lease."""
        required_fields = ["mac", "ip", "hostname"]
        for field in required_fields:
            if field not in lease:
                raise ValueError(f"Missing required field: {field}")

        # Validate MAC address
        import re
        if not re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', lease["mac"]):
            raise ValueError(f"Invalid MAC address format: {lease['mac']}")

        # Validate IP address
        import ipaddress
        try:
            ipaddress.ip_address(lease["ip"])
        except ValueError:
            raise ValueError(f"Invalid IP address: {lease['ip']}")

        return await self.client.dhcp.add_static_lease(lease)

    async def async_delete_static_lease(self, mac):
        """Delete a static DHCP lease."""
        import re
        if not re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', mac):
            raise ValueError(f"Invalid MAC address format: {mac}")
        return await self.client.dhcp.delete_static_lease(mac)

    async def async_set_dns_servers(self, servers):
        """Set DNS servers."""
        if not isinstance(servers, list) or len(servers) != 2:
            raise ValueError("servers must be a list of exactly 2 DNS server addresses")

        import ipaddress
        for server in servers:
            if server:  # Allow empty strings for optional secondary
                try:
                    ipaddress.ip_address(server)
                except ValueError:
                    raise ValueError(f"Invalid DNS server address: {server}")

        return await self.client.network.set_dns(servers)

    async def async_update_firmware(self):
        """Update router firmware."""
        return await self.client.system.update_firmware()