# GL.iNet Router Integration for Home Assistant

A custom Home Assistant integration for monitoring and controlling **GL.iNet routers** using the `gli4py` API.

This integration provides real-time visibility into your router, connected devices, and network activity, along with control over key features like WiFi and VPN.

---

## 🚀 Features

### 📡 Router Monitoring

* Router uptime
* WAN download/upload throughput
* CPU temperature
* Memory usage
* Disk usage
* Flash usage
* System load (1min, 5min, 15min averages)
* WAN/LAN IP addresses
* Connected device count
* DHCP lease count
* Port forwarding rule count
* USB device status
* Firmware version
* System logs

### 👥 Connected Devices

* Automatic discovery of connected clients
* Device tracker entities for each client
* Rich attributes per device:

  * IP address
  * MAC address
  * Hostname
  * Signal strength (WiFi)
  * RX/TX usage
  * Interface details

### 📊 Per-Device Bandwidth

* Individual sensors per client:

  * Download (RX)
  * Upload (TX)

### 🔒 VPN Status & Control

* VPN connection status (binary sensor)
* Enable/disable VPN via switch

### 📶 WiFi Interface Control

* One switch per WiFi interface (e.g. 2.4GHz / 5GHz)
* Guest network enable/disable
* Attributes include:

  * SSID
  * Channel
  * Band
  * Encryption
  * Connected clients

### 🔘 Router Controls

* Reboot button
* LED control switch
* Firmware update button

### 🌐 Network Configuration

* DNS server selection (primary/secondary)
* DHCP lease time configuration
* Port forwarding management
* Firewall rule monitoring

---

## 🔧 Services

The integration provides several services for advanced router configuration:

### `glinet.add_port_forwarding`

Add a port forwarding rule.

**Parameters:**
- `host` (string, required): Router IP address
- `external_port` (integer, required): External port number
- `internal_ip` (string, required): Internal IP address
- `internal_port` (integer, required): Internal port number
- `protocol` (string, optional): Protocol ("tcp", "udp", "both") - default: "tcp"
- `description` (string, optional): Rule description

### `glinet.remove_port_forwarding`

Remove a port forwarding rule.

**Parameters:**
- `host` (string, required): Router IP address
- `rule_id` (string, required): Rule identifier

### `glinet.set_dns_servers`

Set DNS servers.

**Parameters:**
- `host` (string, required): Router IP address
- `primary` (string, required): Primary DNS server IP
- `secondary` (string, required): Secondary DNS server IP

### `glinet.add_static_lease`

Add a static DHCP lease.

**Parameters:**
- `host` (string, required): Router IP address
- `mac` (string, required): MAC address
- `ip` (string, required): IP address to assign
- `hostname` (string, required): Hostname

### `glinet.remove_static_lease`

Remove a static DHCP lease.

**Parameters:**
- `host` (string, required): Router IP address
- `mac` (string, required): MAC address

### `glinet.set_dhcp_config`

Set DHCP configuration.

**Parameters:**
- `host` (string, required): Router IP address
- `lease_time` (integer, optional): Lease time in hours
- `start_ip` (string, optional): DHCP range start IP
- `end_ip` (string, optional): DHCP range end IP
- `gateway` (string, optional): Gateway IP
- `subnet_mask` (string, optional): Subnet mask

### 🔄 Dynamic Updates

* Devices automatically appear/disappear
* Entity state updates via a central coordinator
* All router-related entities are grouped under a single GL.iNet Router device

### 🔍 Auto Discovery

* Zeroconf-based discovery of GL.iNet routers on your network
* Manual setup also supported

### 🧾 Diagnostics

* Built-in diagnostics dump for troubleshooting
* Sensitive data automatically redacted

---

## 📦 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Click **⋮ → Custom repositories**
4. Add this repository URL
5. Select **Integration**
6. Install "GL.iNet Router"
7. Restart Home Assistant

---

## ⚙️ Configuration

### Automatic Discovery

If your router is discoverable via Zeroconf:

1. Go to **Settings → Devices & Services**
2. You should see "GL.iNet Router" discovered
3. Click **Configure**

---

### Manual Setup

If not discovered:

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **GL.iNet Router**
4. Enter:

   * **Host** (default: `192.168.8.1`)
   * **Username** (default: `root`)
   * **Password** (default: `goodlife`)

---

## 🔐 Security

* Credentials are stored securely using Home Assistant’s config entry system
* No passwords are written to disk in plain text
* Diagnostics automatically redact sensitive information

---

## 🧠 How It Works

* Uses `gli4py` to communicate with the router API
* A central **DataUpdateCoordinator** polls the router
* Entities subscribe to coordinator data
* Device tracking is dynamic based on MAC addresses

---

## ⚠️ Requirements

* GL.iNet router running compatible firmware (v4+ recommended)
* Local network access to the router
* Home Assistant 2024.6+
* `gli4py` library with extended API support for:
  - System monitoring (CPU, memory, flash, load)
  - DHCP management
  - Port forwarding
  - DNS configuration
  - USB device detection

---

## 🐛 Known Limitations

* Zeroconf discovery depends on router advertising services
* Some API fields may vary between firmware versions
* VLAN / segmented networks may prevent discovery

---

## 🛠 Troubleshooting

* Ensure router API is accessible from Home Assistant
* Verify credentials (default: root / goodlife)
* Check logs:

  ```
  Settings → System → Logs
  ```

* Service calls may fail if `gli4py` library doesn't support all API endpoints
* Some advanced features require specific GL.iNet firmware versions
* Port forwarding and DHCP services require proper permissions on the router

---

## 🤝 Contributing

Pull requests and issues welcome.

---

## 📜 License

MIT License
