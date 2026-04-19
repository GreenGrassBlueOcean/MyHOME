# MyHOME
Modernized MyHOME Custom Component for Home Assistant

[![test-coverage](https://github.com/GreenGrassBlueOcean/MyHOME/actions/workflows/test-coverage.yaml/badge.svg)](https://github.com/GreenGrassBlueOcean/MyHOME/actions/workflows/test-coverage.yaml)
[![codecov](https://codecov.io/gh/GreenGrassBlueOcean/MyHOME/graph/badge.svg)](https://codecov.io/gh/GreenGrassBlueOcean/MyHOME)

*This is a completely modernized, async-native fork of the original integration, specifically hardened for legacy MH200 hardware and modern Home Assistant (2025+).*

## 🌟 Modernization Features

1. **Fully Dynamic Auto-Discovery (No more YAML!):**
   The integration has been completely disentangled from file-system based `myhome.yaml` static configurations. Devices are now registered and configured natively through the Home Assistant UI Device Registry. The integration actively queries the OpenWebNet bus to discover all entities out of the box. Native support for complex **F422 Cross-Bus Routing** (e.g. addresses like `18#4#02`) is also completely handled automatically!
   
2. **Native Audio System Support (WHO=16):**
   Full native support for Bticino/MyHome Audio Matrices, compatible with both legacy baseband and **Sound System 2.0 stereo** hardware. Exposes native `media_player` entities for all audio zones with bidirectional state tracking.
   - **Turn On/Off, Source Selection & Volume:** Full support for `turn_on`, `turn_off`, `select_source`, `volume_set`, `volume_up`, and `volume_down`. Source selection correctly addresses stereo amplifier zones (11x–14x).
   - **Absolute Volume Tracking:** Full support for dimension messages (`*#16*where*#1*vol##`), normalizing the 0–31 hardware scale automatically.
   - **Software Mute Emulation:** Since OpenWebNet lacks a native audio Mute function, this integration fully emulates local muting, keeping physical volume levels accurately cached.

3. **Auto-Detect Dimmable Lights:**
   Dimmers are automatically recognized from the OpenWebNet protocol. When the gateway sends a brightness level or brightness preset event, the light entity is promoted from simple on/off to full brightness control with transition support. No manual configuration needed — the integration learns from the bus traffic. A `customize.yaml` fallback is still supported for manual overrides.

4. **Smart Gateway Configuration:**
   The custom setup flow first attempts to auto-discover the gateway's MAC address and model by fetching the UPnP device descriptor directly from known BTicino ports (`http://<IP>:49153/description.xml`). If the gateway does not support UPnP (e.g., older MH200 models), a manual fallback step is presented instead. This eliminates the need to manually look up the MAC address for most modern gateways (F454, MH202, MH201).

5. **MH200 & Stability Hardening:**
   Resolved the fatal "Listener Death" bugs prevalent in the original library. 
   - Strict 120-second active watchdogs drop permanently hung TCP sockets efficiently.
   - Exponential Backoff routines (`2s -> 60s`) guard against embedded gateway DDoS on power restoration.
   - Polling queries (`SCAN_INTERVAL`) drastically reduced by default for passive sensors.
   - Native integration caching (`ConfigEntryNotReady`) entirely eliminates the infamous "Restart required on first installation" crash loop.

6. **Robust Entity Migration & Registry Integrity:**
   The integration includes self-healing logic for entity IDs. On startup, it automatically detects and corrects orphaned or mis-named entities from previous installations, reverting entity IDs back to the standard `light.light_XX` / `cover.cover_XX` format. Legacy `customize.yaml` friendly names are transparently absorbed and applied without requiring any manual re-configuration.

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
4. If no gateways are found automatically, select "Custom" and enter your gateway's IP address and port. The integration will try to auto-detect the MAC address and model via UPnP. If that fails (e.g., on legacy MH200 gateways), a manual entry form is presented.
5. Enter your gateway's OpenWebNet password when prompted.

### 3. Entity Naming & Discovery
Once connected, the integration strictly uses **Auto-Discovery** to find your Lights, Switches, Covers, and Audio Zones.
Simply use your physical wall switches to interact with your house. Home Assistant will capture the physical bus events, dynamically generate the devices in your dashboard (naming them by their hardware address, e.g., `Light 18`, `Cover 18#4#02`), and store them permanently!

To assign human-readable names (like "Kitchen Lights"):
*   **The Modern Way:** Click on the generated Entity in the Home Assistant UI (`Settings -> Devices`), click the gear icon, and rename it natively.
*   **The Power-User Way:** Use Home Assistant's native [customize.yaml](https://www.home-assistant.io/docs/configuration/customizing-devices/) feature to bulk-rename entities without touching the underlying integration logic.

### 4. Audio Zone Controls
Audio zones are automatically discovered as `media_player` entities when any sound system traffic is detected on the bus. The supported features include:

| Feature | Method |
|---|---|
| Turn On/Off | Standard HA media player controls |
| Volume Up/Down | Step-based volume adjustment |
| Volume Slider | Absolute volume set (0–31 → normalized 0.0–1.0) |
| Source Selection | Selects stereo source (1–4) for the specific zone |
| Mute | Software-emulated (caches volume, sets to 0, restores on unmute) |

For **manual OWN commands** (e.g., via the `myhome.send_message` service), refer to the OpenWebNet specification for WHO=16.

### Advanced Usage & Protocol Handling

The underlying OpenWebNet (`OWNd`) package has been exclusively vendored natively into this component (`custom_components/myhome/ownd`), allowing complete downstream control over exact OpenWebNet protocol implementations to maximize reliability.

#### Supported Hardware
| Gateway | UPnP Auto-Discovery | Notes |
|---|---|---|
| F454 | ✅ | Full UPnP support (port 49153) |
| MH202 / MH201 | ✅ | Full UPnP support |
| MH200 | ❌ | Manual MAC entry required; no UPnP descriptor |
| MyHomeServer1 | ✅ | Should work via SSDP |

*(For legacy OpenWebNet implementation documentation, refer to the original bticino open specs).*
