# MyHOME
Modernized MyHOME Custom Component for Home Assistant

[![test-coverage](https://github.com/GreenGrassBlueOcean/MyHOME/actions/workflows/test-coverage.yaml/badge.svg)](https://github.com/GreenGrassBlueOcean/MyHOME/actions/workflows/test-coverage.yaml)
[![codecov](https://codecov.io/gh/GreenGrassBlueOcean/MyHOME/graph/badge.svg?token=YOUR_TOKEN_HERE)](https://codecov.io/gh/GreenGrassBlueOcean/MyHOME)

*This is a completely modernized, async-native fork of the original integration, specifically hardened for legacy MH200 hardware and modern Home Assistant (2025+).*

## 🌟 Modernization Features

1. **Fully Dynamic Auto-Discovery (No more YAML!):**
   The integration has been completely disentangled from file-system based `myhome.yaml` static configurations. Devices are now registered and configured natively through the Home Assistant UI Device Registry. The integration actively queries the OpenWebNet bus to discover all entities.
   
2. **Native Audio System Support (WHO=16):**
   Full native support for Bticino/MyHome Audio Matrices. Exposes native `media_player` entities for all audio zones with bidirectional state tracking, supporting `turn_on`, `turn_off`, `volume_up/down`, and generic `select_source` integrations routing physical keypad events seamlessly directly to your UI.

3. **MH200 & Stability Hardening:**
   Resolved the fatal "Listener Death" bugs prevalent in the original library. 
   - Strict 120-second active watchdogs drop permanently hung TCP sockets efficiently.
   - Exponential Backoff routines (`2s -> 60s`) guard against embedded gateway DDoS on power restoration.
   - Polling queries (`SCAN_INTERVAL`) drastically reduced by default for passive sensors.
   - Native integration caching (`ConfigEntryNotReady`) entirely eliminates the infamous "Restart required on first installation" crash loop.

## ⚙️ Installation

You can install this integration via HACS!
Upon adding your integration via the UI, it will automatically search for compatible gateways (MH200, F454, MyHomeServer1) over SSDP. Simply follow the UI wizard.

### Advanced Usage & Protocol Handling

The underlying OpenWebNet (`OWNd`) package has been exclusively vendored natively into this component (`custom_components/myhome/ownd`), allowing complete downstream control over exact OpenWebNet protocol implementations to maximize reliability.

*(For legacy OpenWebNet implementation documentation, refer to the original bticino open specs).*
