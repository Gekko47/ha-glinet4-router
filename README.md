# GL.iNet Router Integration for Home Assistant

A modern, reliable Home Assistant integration for **GL.iNet routers**, providing real-time monitoring, device tracking, and router controls through a hardened async API layer.

Designed for **Home Assistant 2026.1+** and fully compatible with **HACS**.

---

## ✨ Features

### 📡 Router Monitoring
- System uptime  
- CPU temperature and load averages  
- Memory, disk, and flash usage  
- WAN / LAN IP addresses  
- Network throughput (download / upload)  
- Firmware version  
- System logs  
- USB device detection (where supported)  

---

### 👥 Connected Devices (Dynamic Tracking)
- Automatic device discovery  
- Stable MAC-based identity tracking  
- Per-device details:
  - IP address  
  - Hostname  
  - Connection type (WiFi / Ethernet)  
  - Connection status  
- Live updates as devices join or leave  

---

### 📶 WiFi Control
- Enable / disable 2.4GHz and 5GHz radios  
- SSID and channel visibility  
- Guest network detection  
- Connected client counts  

---

### 🔒 VPN Control
- VPN status monitoring  
- Enable / disable VPN connection  
- Connection type and server info  
- Uptime tracking  

---

### 🔘 Router Actions
- Reboot router from Home Assistant  
- Safe execution with error handling  
- Multi-router support via entry selection  

---

## 🧭 Setup Experience

### 🔍 Device Selection (NEW)
During setup you can:

- Select the correct router instance  
- Avoid silent auto-selection  
- Support multiple routers on the same network  

---

### 🔐 Secure Login
- Challenge-response authentication  
- No plaintext password exposure after handshake  
- Automatic session handling  
- Seamless reconnection after restart  

---

## ⚙️ Configuration Options

After installation:

- Fast update interval (live data)  
- Slow update interval (system data)  
- API timeout settings  

Changes apply immediately without reinstall.

---

## 📊 Diagnostics

Available via:

**Settings → Devices & Services → GL.iNet Router → Diagnostics**

Includes:

- Connection status  
- Authentication state  
- API health  
- Coordinator update status  
- Redacted sensitive data  

---

## 🧠 Architecture

### ⚡ Fast Coordinator
Real-time data:
- Devices  
- WiFi state  
- VPN status  
- WAN IP and throughput  

### 🐢 Slow Coordinator
System-level data:
- Firmware info  
- USB devices  
- DHCP leases  
- Port forwarding rules  

---

## 🔐 Security

- No plaintext password storage  
- Challenge-response authentication  
- Secure session ID handling  
- Automatic session recovery  
- Multi-router isolation (`entry_id` scoped)  
- Redacted diagnostics output  

---

## 📦 Installation

### 🟢 HACS (Recommended)

1. Open **HACS**  
2. Add this repository  
3. Search for **GL.iNet Router Integration**  
4. Install  
5. Restart Home Assistant  

---

### 🧾 Manual Installation

Copy the integration into your Home Assistant config directory:

custom_components/glinet/

Then restart Home Assistant.

---

## 🧪 Requirements

- GL.iNet router (OS 4+)  
- Home Assistant 2026.1+  
- Local network access  

---

## ⚠️ Known Limitations

- Zeroconf may fail on VLAN-isolated networks  
- Firmware differences affect available data  
- Some routers do not expose USB / DHCP / port forwarding APIs  
- VPN status varies by firmware implementation  

---

## 🧰 Troubleshooting

### Router not connecting
- Verify IP reachability  
- Check credentials (often `root`)  
- Ensure GL.iNet API is enabled  

---

### Missing devices or sensors
- Check firmware support  
- Review Diagnostics panel  

---

### Discovery not working
- Disable VLAN isolation  
- Ensure multicast is allowed  
- Use manual setup if needed  

---

### Logs

Filter Home Assistant logs:

```text
glinet

## 🧠 Design Philosophy

- Stability over complexity  
- Explicit configuration over assumptions  
- Coordinator-first architecture (no entity polling)  
- Safe multi-router support  
- Predictable failure handling  
- Native Home Assistant patterns  

---

## 🤝 Contributing

Please ensure:

- Home Assistant 2026+ compatibility  
- Coordinator-only data access  
- No entity-level polling  
- HACS compliance  
- Robust error handling  
- Multi-router safety (`entry_id` scoped)  

---

## 📜 License

MIT