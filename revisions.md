Summary of Revisions
I've thoroughly reviewed the repository and made several important improvements to ensure it matches the README's promises and follows Home Assistant best practices:

✅ Implemented Missing Features
VPN Control Switch: Added the missing VPN switch that was promised in the README but not implemented. Users can now enable/disable VPN via a switch entity.
🐛 Fixed Code Issues
Duplicate Code: Removed duplicate async_add_entities call in switch.py
Error Handling: Added try/catch blocks in the coordinator to prevent failures if individual API calls fail
Entity Naming: Improved client sensor names to use hostnames instead of MAC addresses for better user experience
🏗️ Added Proper Home Assistant Integration Features
Device Registry: Created a proper router device that groups all related entities together
Unique IDs: Added unique identifiers to all entities for reliable state management
Device Linking: All router-related entities (sensors, switches, binary sensors, buttons) are now linked to the main router device
State Updates: Added coordinator refresh calls after control actions to ensure UI updates immediately
📚 Documentation Updates
Updated README to mention that entities are grouped under a single device
Bumped version to 0.5.0 to reflect the significant improvements
🔍 Cross-Check Results
The integration now fully implements all features listed in the README:

✅ Router monitoring (uptime, WAN throughput)
✅ Connected device tracking with rich attributes
✅ Per-device bandwidth sensors
✅ VPN status and control
✅ WiFi interface control
✅ Router reboot button
✅ Auto-discovery via Zeroconf
✅ Diagnostics with data redaction
The code is now more robust, follows Home Assistant conventions, and provides a better user experience with proper device organization and reliable entity management.

🔄 Recent Updates (Leveraging gli4py Directly)
- **Dependency Update**: Changed manifest.json to use "gli-py" (PyPI package) instead of git dependency for better reliability.
- **Direct gli4py Usage**: Removed the GlinetAPI wrapper class and updated all code to use GLinet from gli_py directly, following the reference integration's approach.
- **Import Changes**: Updated imports from gli4py to gli_py in config_flow.py and __init__.py.
- **API Calls**: Modified coordinator, switches, buttons, and services to call GLinet methods directly (e.g., api.system.status(), api.vpn.start(), api.firewall.add_port_forwarding()).
- **Config Flow**: Updated validation and connection testing to use GLinet directly without the wrapper.
- **Code Simplification**: Eliminated intermediate abstraction layer, making the integration more aligned with gli4py's native API and the reference implementation.