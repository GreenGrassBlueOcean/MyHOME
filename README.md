# MyHOME
Modernized MyHOME Custom Component for Home Assistant

[![test-coverage](https://github.com/GreenGrassBlueOcean/MyHOME/actions/workflows/test-coverage.yaml/badge.svg)](https://github.com/GreenGrassBlueOcean/MyHOME/actions/workflows/test-coverage.yaml)
[![codecov](https://codecov.io/gh/GreenGrassBlueOcean/MyHOME/graph/badge.svg?token=YOUR_TOKEN_HERE)](https://codecov.io/gh/GreenGrassBlueOcean/MyHOME)

*This is a completely modernized, async-native fork of the original integration, specifically hardened for legacy MH200 hardware and modern Home Assistant (2025+).*

## 🌟 Modernization Features

1. **Fully Dynamic Auto-Discovery (No more YAML!):**
   The integration has been completely disentangled from file-system based `myhome.yaml` static configurations. Devices are now registered and configured natively through the Home Assistant UI Device Registry. The integration actively queries the OpenWebNet bus to discover all entities out of the box. Native support for complex **F422 Cross-Bus Routing** (e.g. addresses like `18#4#02`) is also completely handled automatically!
   
2. **Native Audio System Support (WHO=16):**
   Full native support for Bticino/MyHome Audio Matrices. Exposes native `media_player` entities for all audio zones with bidirectional state tracking, supporting `turn_on`, `turn_off`, and `select_source`.
   - **Absolute Volume Tracking:** Full support for `volume_set` parsing and dimension messages (`*#16*where*#1*vol##`), normalizing the 0-31 hardware scale automatically.
   - **Software Mute Emulation:** Since OpenWebNet lacks a native audio Mute function, this integration fully emulates local muting, keeping physical volume levels accurately cached.

3. **MH200 & Stability Hardening:**
   Resolved the fatal "Listener Death" bugs prevalent in the original library. 
   - Strict 120-second active watchdogs drop permanently hung TCP sockets efficiently.
   - Exponential Backoff routines (`2s -> 60s`) guard against embedded gateway DDoS on power restoration.
   - Polling queries (`SCAN_INTERVAL`) drastically reduced by default for passive sensors.
   - Native integration caching (`ConfigEntryNotReady`) entirely eliminates the infamous "Restart required on first installation" crash loop.

## ⚙️ Installation & Configuration

### 1. Install via HACS (Recommended)
You can install this integration as a Custom Repository via HACS!
1. Go to HACS -> Integrations -> Click the three dots (top right) -> Custom repositories
2. Add this repository URL and select `Integration` as the category.
3. Restart Home Assistant.

### 2. Add the Integration in Home Assistant
**Important:** Do *not* use `configuration.yaml` for this integration. The legacy `myhome.yaml` approach has been completely disabled in favor of modern UI-driven architecture.

1. Go to **Settings -> Devices & Services -> Add Integration**.
2. Search for `MyHOME`.
3. The component will automatically search your local network via SSDP for compatible BTicino gateways (e.g., MH200, F454, MyHomeServer1).
4. Enter your gateway's OpenWebNet password when prompted.

### 3. Entity Naming & Discovery
Once connected, the integration strictly uses **Auto-Discovery** to find your Lights, Switches, Covers, and Audio Zones.
Simply use your physical wall switches to interact with your house. Home Assistant will capture the physical bus events, dynamically generate the devices in your dashboard (naming them by their hardware address, e.g., `Light 18`, `Cover 18#4#02`), and store them permanently!

To assign human-readable names (like "Kitchen Lights"):
*   **The Modern Way:** Click on the generated Entity in the Home Assistant UI (`Settings -> Devices`), click the gear icon, and rename it natively.
*   **The Power-User Way:** Use Home Assistant's native [customize.yaml](https://www.home-assistant.io/docs/configuration/customizing-devices/) feature to bulk-rename entities without touching the underlying integration logic.

### Advanced Usage & Protocol Handling

The underlying OpenWebNet (`OWNd`) package has been exclusively vendored natively into this component (`custom_components/myhome/ownd`), allowing complete downstream control over exact OpenWebNet protocol implementations to maximize reliability.

*(For legacy OpenWebNet implementation documentation, refer to the original bticino open specs).*
