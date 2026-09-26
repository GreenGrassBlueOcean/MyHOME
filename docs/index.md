# MyHOME for Home Assistant

Welcome to the official documentation for the **MyHOME** Home Assistant integration.

This integration connects your BTicino / Legrand MyHOME SCS bus systems via OpenWebNet IP & Serial gateways (such as **F454**, **MH200**, **MH200N**, **MH201**, **MH202**, **MyHomeServer1**, **F461**, or **Legrand 3578 USB**) directly into Home Assistant.

---

## 🌟 Next-Gen Architecture: v2.0

The v2.0 architecture represents a complete modernization of the integration, featuring:

- **UI-First Configuration**: Streamlined gateway setup, automatic on-wire bus discovery, and device management via Home Assistant's native Config Flow and Options Flow (with backward compatibility for existing `myhome.yaml` files and SCS groups).
- **Native Automation Device Triggers**: Automate physical CEN (`WHO = 15`) and CEN+ (`WHO = 25`) scenario pushbuttons directly in Home Assistant's automation builder (Short press, Long press, Release, and Rotary Encoder dials).
- **In-Band Diagnostic Bus Monitor**: Real-time Lovelace card (`custom:myhome-bus-card`) providing live OpenWebNet frame monitoring, filtering, bus sweeping, and 1-click trace export without consuming extra gateway sockets.
- **Diffusione Sonora Dynamic Proxy**: Stream music from Music Assistant or Spotify into BTicino analog audio matrix amplifier zones (`WHO = 16`) with automatic power management and anti-hiss gain staging.
- **Decoupled OWNd 2.0 Engine**: Clean protocol abstraction preventing drift, backed by 1,600+ regression tests with 100% code coverage.

---

## 🧭 Navigation & Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch: __[Getting Started](configuration/README.md)__

    ---

    Step-by-step setup, adding your gateway via Config Flow, and initial bus scan.

-   :material-router-wireless: __[Gateways & Connection](configuration/gateways.md)__

    ---

    F454, MyHomeServer1, MH200N, HMAC authentication, keep-alive, and worker tuning.

-   :material-lightbulb: __[Lighting & Dimming](configuration/lights.md)__

    ---

    SCS on/off relays, dimmers, DALI DT8 tunable white, and RGB colour modes.

-   :material-window-shutter: __[Covers & Shutters](configuration/covers.md)__

    ---

    Timed-cover positioning model, full-run calibration, and hardware status tracking.

-   :material-thermostat: __[Climate & Probes](configuration/climate.md)__

    ---

    Thermoregulation zones, 4-pipe fan-coils, push-driven temperature probes (`WHERE ≥ 100`).

-   :material-speaker: __[Sound System / Audio](configuration/media_player.md)__

    ---

    F441/F441M matrix routing, multiroom streaming proxy, and decoder pooling.

-   :material-gesture-tap-button: __[CEN & CEN+ Triggers](configuration/cen_cenplus.md)__

    ---

    Physical wall buttons, scenario triggers, and ready-to-use blueprints.

-   :material-monitor-dashboard: __[Bus Monitor & Tools](configuration/bus_monitor.md)__

    ---

    Real-time Lovelace bus monitor card, trace capture, and bus sweep utility.

-   :material-wrench: __[Repairs & Diagnostics](diagnostics/repair-issues.md)__

    ---

    Comprehensive resolution guide for Home Assistant Repairs and diagnostic telemetry.

-   :material-arrow-up-bold-circle: __[Upgrade from v0.9.4](migration/upgrade-from-094.md)__

    ---

    Step-by-step roadmap to migrate from legacy v0.9.4 YAML plants to the v2 architecture.

</div>

---

## 📦 Compatibility Matrix

<!-- GATEWAY_PROFILES_START -->
| Gateway Model | Protocol Support | Max Command Workers | Inter-Frame Delay | UPnP Discovery | Notes |
|---|---|---|---|---|---|
| **F454** | OpenWebNet / HMAC | 4 workers | 20 ms | ✅ Port 49153 | Full high-speed multi-session support |
| **F455** | OpenWebNet / HMAC | 4 workers | 20 ms | ✅ Port 49153 | Basic gateway (single SCS bus) |
| **F461** | OpenWebNet / HMAC | 4 workers | 20 ms | ❌ Manual | Compact DIN Ethernet Web Server |
| **MH202** | OpenWebNet / HMAC | 3 workers | 30 ms | ✅ Port 49153 | Modern scenario programmer gateway |
| **MH201** | OpenWebNet | 2 workers | 60 ms | ✅ Port 49153 | Second-generation scenario programmer |
| **MyHomeServer1** | OpenWebNet / HMAC | 4 workers | 20 ms | ✅ SSDP | Cloud/local hybrid gateway |
| **MH200N** | OpenWebNet | 2 workers | 80 ms | ❌ Manual | Second-generation scenario programmer |
| **MH200** *(Legacy)* | OpenWebNet | 1 worker | 150 ms | ❌ Manual | Strict single-session pacing; watchdog hardened |
| **H4890 / AM4890** | OpenWebNet | 2 workers | 100 ms | ❌ Manual | 3.5" Touch screen display IP gateway (Axolute / Livinglight) |
| **F452 / F453AV** | OpenWebNet | 2 workers | 50 ms | ✅ Port 49153 | Audio/video & web server gateway |
| **HL4684** | OpenWebNet | 2 workers | 80 ms | ✅ SSDP | 10" Touch screen display IP gateway |
| **Legrand 3578** | OpenWebNet (Serial) | 2 workers | 50 ms | ❌ Manual (Serial) | USB / Serial gateway & OpenZigBee interface |
<!-- GATEWAY_PROFILES_END -->

---

## 🛠️ Need Help?

- 💬 Join community discussions on the [OpenWebNet-HA GitHub Organization](https://github.com/OpenWebNet-HA/MyHOME/discussions).
- 🐛 Report bugs or submit diagnostic traces via [GitHub Issues](https://github.com/OpenWebNet-HA/MyHOME/issues).
- 📖 Inspect OpenWebNet protocol specifications in the [WHO Catalog](openwebnet-who-specifications.md).
