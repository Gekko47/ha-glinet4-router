# GL.iNet Router Integration for Home Assistant

A modern Home Assistant integration for monitoring and controlling **GL.iNet routers** using a hardened async API client and coordinator-based architecture.

Designed for **Home Assistant 2026.4+** with HACS compatibility in mind.

---

## 🚀 Features

### 📡 Router Monitoring

Real-time system and network metrics:

- Router uptime
- WAN download/upload throughput
- CPU temperature
- Memory usage
- Disk usage
- Flash usage
- System load (1m / 5m / 15m averages)
- WAN and LAN IP addresses
- Connected device count
- DHCP lease count
- Port forwarding rules
- USB device detection
- Firmware version
- System logs (basic support)

---

### 👥 Connected Devices

Automatically discovered client devices:

- MAC-based device tracking
- Device registry integration
- Per-device attributes:
  - IP address
  - Hostname
  - Interface (WiFi/Ethernet)
  - Signal strength (if available)
  - RX/TX usage (if provided by router)

---

### 📶 WiFi Control

- One switch per WiFi interface
- Enable / disable WiFi radios
- Attributes:
  - SSID
  - Band (2.4GHz / 5GHz)
  - Channel
  - Hidden SSID flag
  - Guest network flag
  - Connected client count

---

### 🔒 VPN Control

- VPN connection status sensor
- VPN enable/disable switch
- Attributes:
  - Connection type
  - Server
  - Status
  - Uptime

---

### 🔘 Router Controls

- Reboot router button
- Service-based control layer (safe entry_id targeting)

---

## 🧠 Architecture

This integration uses a **dual-coordinator model**:

### ⚡ Fast Coordinator
Handles frequent updates:
- Clients
- WiFi state
- VPN status
- Throughput
- WAN status

### 🐢 Slow Coordinator
Handles heavy or rarely changing data:
- System info
- Firmware version
- Device metadata
- Static network configuration

This separation improves:
- Performance
- API load reduction
- State stability in HA

---

## 🔄 Dynamic Updates

- Entities update automatically via coordinators
- Client devices appear/disappear dynamically
- No polling per entity (fully centralized polling model)

---

## 🧩 Device Registry

The integration creates:

### Router Device
- Single GL.iNet router entry in Home Assistant

### Client Devices
- Each MAC address becomes a Home Assistant device
- No entities required per client (lightweight registry model)

---

## 🔍 Discovery

### Supported discovery methods:
- Zeroconf (`_glinet._tcp.local`)
- Manual configuration

---

## ⚙️ Configuration

### Automatic Discovery

1. Go to **Settings → Devices & Services**
2. Look for **GL.iNet Router**
3. Click **Configure**

---

### Manual Setup

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **GL.iNet Router**
4. Enter:
   - Host (e.g. `192.168.8.1`)
   - Username (default: `root`)
   - Password

---

## 🔧 Services

### `glinet.reboot_router`

Reboot a router instance.

**Parameters:**
- `entry_id` (required): Config entry ID

---

## 🔐 Security

- Credentials stored securely in Home Assistant config entries
- No plaintext credential storage
- API token handling is session-based and automatically refreshed
- Sensitive attributes redacted in diagnostics

---

## 🧪 Requirements

- GL.iNet router with compatible firmware (GL.iNet OS 4+ recommended)
- Local network access to router
- Home Assistant **2026.4+**
- Python aiohttp session (provided by HA)

---

## 🐛 Known Limitations

- Zeroconf discovery may not work on VLAN-isolated networks
- API fields vary between firmware versions
- Some routers may not expose:
  - USB devices
  - DHCP leases
  - Port forwarding rules
- VPN state detection depends on firmware response format

---

## 🧰 Troubleshooting

### Router not connecting
- Verify host is reachable from HA
- Check username/password (default often `root`)
- Ensure router API is enabled

### Missing sensors
- Firmware may not expose all endpoints
- Check HA logs for API failures

### Discovery not working
- Ensure multicast/zeroconf is not blocked
- Try manual configuration

Logs:
Settings → System → Logs → GL.iNet Router
---

## 🧠 Design Philosophy

This integration prioritizes:

- Stability over feature explosion
- Centralized state management (coordinators)
- Minimal entity overhead
- Safe API retry logic
- HA-native patterns only

---

## 🤝 Contributing

Pull requests welcome.

Please ensure:
- HA 2026.4 compatibility
- No entity-side polling
- All API access goes through coordinator layer
- HACS lint compliance

---

## 📜 License

MIT License