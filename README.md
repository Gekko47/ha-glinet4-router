# GL.iNet Router Integration for Home Assistant

A modern Home Assistant integration for monitoring and controlling **GL.iNet routers** using a hardened async API client, dual-coordinator architecture, and automatic session persistence.

Designed for **Home Assistant 2026.1+** with full HACS compatibility and production-ready resilience.

---

## 🚀 Features

### 📡 Router Monitoring

Real-time system and network metrics:

- Router uptime
- WAN download/upload throughput
- CPU temperature and thermal metrics
- Memory usage (absolute and percentage)
- Disk usage
- Flash usage
- System load (1m / 5m / 15m averages)
- WAN and LAN IP addresses
- Connected device count
- DHCP lease count
- Port forwarding rules
- USB device detection
- Firmware version
- System logs

---

### 👥 Connected Devices

Automatically discovered client devices with dynamic tracking:

- MAC-based device identity
- Device registry integration
- Per-device attributes:
  - IP address
  - Hostname
  - Interface (WiFi/Ethernet)
  - Signal strength (if available)
  - RX/TX usage (if provided by router)
  - Connection status
- Devices appear/disappear dynamically

---

### 📶 WiFi Control

Individual switches per WiFi interface:

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
  - Server address
  - Connection status
  - Uptime tracking

---

### 🔘 Router Controls

- Reboot router button with error handling
- Service-based control layer (safe entry_id targeting)

---

## 🧠 Architecture

This integration uses a **dual-coordinator model** optimized for reliability:

### ⚡ Fast Coordinator (30s default)
Handles frequent updates:
- Connected clients
- WiFi state & radio status
- VPN connection status
- Network throughput
- WAN IP and status

### 🐢 Slow Coordinator (300s default)
Handles heavy or rarely changing data:
- System info & firmware
- Device metadata
- USB device inventory
- DHCP lease configuration
- Port forwarding rules

### Configurable Intervals
All update intervals are **user-configurable** from the integration options:
- Fast coordinator: 10–300 seconds
- Slow coordinator: 30–3600 seconds
- API timeout: 5–60 seconds

---

## 🔐 Authentication & Session Management

### Challenge-Based Authentication
- GL.iNet challenge-response protocol with MD5/SHA256/SHA512 support
- Secure credential handling (never sent in plaintext)
- Automatic SID (session ID) management

### Session Persistence
- SID stored securely in Home Assistant storage
- Automatic session recovery on HA restart
- SID validation on restore
- Single-attempt re-login on session expiration

### Session Keepalive
- Proactive session refresh during idle periods
- Prevents SID expiration on long-running HA instances
- Automatic re-authentication on first use after expiration

---

## 📊 Diagnostics & Debugging

### Built-In Diagnostics
Generate diagnostic reports from **Settings → Devices & Services → GL.iNet Router**:

- API connection state
- Coordinator health (update success rate, last update time)
- System info snapshot
- Data availability per coordinator
- Safely redacted credentials

Useful for troubleshooting connection issues without exposing sensitive data.

---

## 🔄 Dynamic Configuration

### Options Flow (Post-Setup Customization)
Reconfigure without re-adding integration:

- Adjust fast coordinator update interval
- Adjust slow coordinator update interval
- Adjust API request timeout
- Changes take effect immediately

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

### Reconfiguration

1. Go to **Settings → Devices & Services**
2. Select **GL.iNet Router**
3. Click the **three dots → Options**
4. Adjust update intervals and timeouts

---

## 🔧 Services

### `glinet.reboot_router`

Safely reboot a router instance with error handling.

**Parameters:**
- `entry_id` (required): Config entry ID of the router

**Example:**
```yaml
service: glinet.reboot_router
data:
  entry_id: "a1b2c3d4e5f6g7h8"
```

---

## 🔐 Security

- Credentials stored securely in Home Assistant config entries storage
- No plaintext credential storage or logging
- Session IDs (SIDs) managed with automatic validation
- Challenge-response protocol (no password over network)
- Sensitive attributes redacted in diagnostics
- Safe re-authentication on session expiration
- Race-condition proof locking for concurrent API calls

---

## 🧪 Requirements

- GL.iNet router with compatible firmware (GL.iNet OS 4+ recommended)
- Local network access to router
- Home Assistant **2026.1+**
- aiohttp (provided by Home Assistant)

---

## 🐛 Known Limitations

- Zeroconf discovery may not work on VLAN-isolated networks
- API fields vary between firmware versions
- Some routers may not expose:
  - USB devices
  - DHCP leases
  - Port forwarding rules
- VPN state detection depends on firmware response format
- Session IDs may expire after extended network interruptions (auto-recovery enabled)

---

## 🧰 Troubleshooting

### Router not connecting
- Verify host is reachable from HA: `ping <host>`
- Check username/password (default often `root` with empty password)
- Ensure GL.iNet API is enabled on the router
- Check **Settings → Devices & Services → GL.iNet Router → Diagnostics** for detailed error state

### Authentication failures after HA restart
- Session ID recovery is attempted automatically
- If recovery fails, full re-authentication occurs transparently
- Check logs for persistent auth errors

### Missing sensors or devices
- Firmware may not expose all endpoints
- Check **Settings → Devices & Services → GL.iNet Router → Diagnostics** to see coordinator data availability
- View HA logs for API endpoint failures

### Discovery not working
- Ensure multicast/zeroconf is not blocked between HA and router
- Check network VLAN isolation
- Use manual configuration as fallback

### Slow responsiveness
- Increase fast/slow coordinator intervals from Options
- Reduce API timeout if network is reliable
- Check HA system load (coordinators respect HA's update cycle)

### View Logs
**Settings → System → Logs → Filter by `glinet`**

---

## 🧠 Design Philosophy

This integration prioritizes:

- **Stability**: Hardened error handling, race-condition safe concurrency
- **Reliability**: Session persistence, automatic recovery, keepalive mechanisms
- **Performance**: Centralized coordinator model, no entity-level polling
- **Maintainability**: HA-native patterns, clean architecture, comprehensive logging
- **User Control**: Configurable intervals and timeouts
- **Debugging**: Built-in diagnostics, detailed logging

---

## 🤝 Contributing

Pull requests welcome.

Please ensure:
- HA 2026.1+ compatibility
- No entity-side polling
- All API access through coordinator layer
- Coordinator-based architecture maintained
- HACS lint compliance
- Comprehensive error handling

---

## 📜 License

MIT License