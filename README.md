# MyHOME — OpenWebNet Integration for Home Assistant

[![Current Stable](https://img.shields.io/badge/stable-v0.9.4-blue.svg)](https://github.com/OpenWebNet-HA/MyHOME/releases/tag/0.9.4)
[![Active Beta](https://img.shields.io/badge/beta-v2.0.0b15-orange.svg)](https://github.com/OpenWebNet-HA/MyHOME/releases/tag/2.0.0b15)
[![Validate with hassfest](https://github.com/OpenWebNet-HA/MyHOME/actions/workflows/hassfest.yml/badge.svg)](https://github.com/OpenWebNet-HA/MyHOME/actions/workflows/hassfest.yml)
[![HACS Validation](https://github.com/OpenWebNet-HA/MyHOME/actions/workflows/validate.yml/badge.svg)](https://github.com/OpenWebNet-HA/MyHOME/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![Quality Scale](https://img.shields.io/badge/Quality%20Scale-Platinum%20(54%2F54)-brightgreen.svg)](https://openwebnet-ha.github.io/MyHOME/beta/)
[![Tests](https://img.shields.io/badge/tests-3%2C600%2B%20passing-brightgreen.svg)](https://github.com/OpenWebNet-HA/MyHOME/actions/workflows/test-coverage.yaml)
[![Coverage](https://img.shields.io/badge/coverage-100.0%25-brightgreen.svg)](https://app.codecov.io/gh/OpenWebNet-HA/MyHOME/tree/v2-phase1-architecture)
[![Documentation](https://img.shields.io/badge/Docs-openwebnet--ha.github.io%2FMyHOME-blue.svg)](https://openwebnet-ha.github.io/MyHOME/beta/)
[![Discussions](https://img.shields.io/badge/Discussions-Join-blue?logo=github)](https://github.com/OpenWebNet-HA/MyHOME/discussions)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/OpenWebNet-HA/MyHOME/blob/v2-phase1-architecture/LICENSE)

Modern, async-native Home Assistant integration for **BTicino / Legrand MyHOME** SCS bus systems connected via OpenWebNet IP & Serial gateways.

Maintained by the **[OpenWebNet-HA](https://github.com/OpenWebNet-HA)** community organisation.

[📦 Quick Installation](#-installation) • [🏛️ Supported Hardware](#️-supported-hardware--gateways) • [🌟 Key Features](#-modern-v2-features) • [📚 Full Documentation](https://openwebnet-ha.github.io/MyHOME/beta/) • [💬 Discussions](https://github.com/OpenWebNet-HA/MyHOME/discussions) • [🗺️ Stable v2.0.0 PR #232](https://github.com/OpenWebNet-HA/MyHOME/pull/232)

---

> [!IMPORTANT]
> ### 🛡️ Current Stable Status vs. Active V2 Beta
>
> - **Current Stable Release ([v0.9.4](https://github.com/OpenWebNet-HA/MyHOME/releases/tag/0.9.4))**: The baseline release on `master` for users seeking production stability or running older Home Assistant cores (< 2026.3 / Python < 3.14). HACS installs this version by default when pre-releases are not enabled.
> - **Active Field-Testing Beta ([v2.0.0b15](https://github.com/OpenWebNet-HA/MyHOME/releases/tag/2.0.0b15))**: Modernized async-native architecture, declarative gateway profiles, hardware timers, audio streaming proxy, central climate coordination, and 100% test coverage. Recommended for Home Assistant ≥ 2026.3.
> - **Roadmap to Stable v2.0.0**: Once community field-testing on the beta line is concluded, **[PR #232](https://github.com/OpenWebNet-HA/MyHOME/pull/232)** will merge the V2 architecture directly into `master`, making it the official stable default for all users.
> - **Zero-Friction Migration**: Upgrading to V2 safely preserves all existing device names, custom entity IDs (`light.living_room`), and gateway configurations. Unique IDs migrate automatically (`MAC-WHERE` → `MAC-WHO-WHERE`).

---

## 📦 Installation

> [!CAUTION]
> **⚠️ Never store backup copies inside `/config/custom_components/` (e.g. `myhome.backup`)!**  
> Home Assistant automatically discovers **all** subdirectories containing `manifest.json` under `custom_components`. Backups inside this folder cause startup crashes (`Unable to import component: No module named 'custom_components.myhome.backup'`). Always keep backups **outside** in `/config/myhome_backup/`.

### 🚀 Installing the Active Beta (v2.0.0b15 — Recommended for HA ≥ 2026.3)

> [!TIP]
> **Recommended Beta Install Method**: In **HACS 2.0+**, pre-release toggle switches can get stuck in an *"unavailable"* loop due to upstream registry caching, or show validation warnings before PR #232 merges. Using **Method 1 (Terminal & SSH)** below takes less than 10 seconds, is 100% reliable, and completely preserves your configuration and entity IDs.

#### Method 1: One-Liner via Terminal & SSH Add-on (⭐ Recommended)

Open the **Terminal** in your Home Assistant sidebar and paste:

```bash
cd /config/custom_components
# Move any legacy in-place backup out of custom_components to prevent loader crashes:
[ -d myhome.backup ] && mv myhome.backup /config/myhome_backup_old
# Create a safety backup in /config (outside custom_components) before updating:
[ -d myhome ] && rm -rf /config/myhome_backup && cp -r myhome /config/myhome_backup
# Download and install the latest v2.0.0b15 release:
rm -rf myhome
wget -O myhome_beta.zip https://github.com/OpenWebNet-HA/MyHOME/releases/download/2.0.0b15/myhome.zip
unzip -q myhome_beta.zip -d myhome
rm myhome_beta.zip
ha core restart
```

*(For **Home Assistant Container / Docker**, run on your Docker host:)*
```bash
docker exec -it homeassistant bash -c 'cd /config/custom_components && [ -d myhome.backup ] && mv myhome.backup /config/myhome_backup_old; [ -d myhome ] && rm -rf /config/myhome_backup && cp -r myhome /config/myhome_backup; rm -rf myhome && wget -O myhome_beta.zip https://github.com/OpenWebNet-HA/MyHOME/releases/download/2.0.0b15/myhome.zip && unzip -q myhome_beta.zip -d myhome && rm myhome_beta.zip'
docker restart homeassistant
```

#### Method 2: Manual Installation (Archive / Samba)

1. Download the release package:  
   👉 **[Download myhome.zip (v2.0.0b15)](https://github.com/OpenWebNet-HA/MyHOME/releases/download/2.0.0b15/myhome.zip)** (or browse all [GitHub Releases](https://github.com/OpenWebNet-HA/MyHOME/releases))
2. Open your configuration directory via Samba Share, Studio Code Server, or File Editor.
3. Extract `myhome.zip` directly into `/config/custom_components/myhome/` (overwriting existing files).
4. Restart Home Assistant (**Settings → System → Restart**).

#### Method 3: HACS (Custom Repository)

1. In Home Assistant, open **HACS → Integrations**.
2. Click the top-right menu (`⋮`) → **Custom repositories**.
3. Add repository URL: `https://github.com/OpenWebNet-HA/MyHOME` with type **Integration**.
4. Open the **MyHOME** card in HACS, click `⋮` → **Redownload**, ensure **Show beta versions** is toggled ON, select **`2.0.0b15`**, and click **Download**.
5. Restart Home Assistant.

---

### 🛡️ Installing or Staying on Current Stable (v0.9.4)

If you prefer production stability, wish to wait for the final `v2.0.0` stable merge, or run Home Assistant older than 2026.3:

* **Via HACS (Default)**: Search for **MyHOME** in HACS and click **Download** (keep *Show beta versions* disabled). HACS will automatically install **v0.9.4**.
* **Via Terminal & SSH**:
  ```bash
  cd /config/custom_components
  [ -d myhome ] && rm -rf /config/myhome_backup && cp -r myhome /config/myhome_backup
  rm -rf myhome
  wget -O myhome_stable.zip https://github.com/OpenWebNet-HA/MyHOME/releases/download/0.9.4/myhome.zip
  unzip -q myhome_stable.zip -d myhome
  rm myhome_stable.zip
  ha core restart
  ```
* **Configuration Guide for v0.9.4**: Entity definitions on legacy 0.9.4 use manual YAML configuration. Refer to the [Legacy v0.9.4 Configuration Guide](https://github.com/anotherjulien/MyHOME/wiki/Configuration).

---

## 🏛️ Supported Hardware & Gateways

The integration features declarative hardware profiles that automatically calibrate connection concurrency, inter-frame bus pacing, and query throttles specifically for your gateway model:

| Gateway Model | Protocol Support | Max Command Workers | Inter-Frame Delay | Discovery | Notes |
|---|---|---|---|---|---|
| **F454** | OpenWebNet / HMAC | 4 workers | 50 ms | ✅ UPnP / Port 49153 | Full high-speed multi-session IP gateway |
| **F455** | OpenWebNet / HMAC | 4 workers | 50 ms | ✅ UPnP / Port 49153 | Basic gateway (single SCS bus) |
| **F461** | OpenWebNet / HMAC | 4 workers | 50 ms | ❌ Manual | Compact DIN Ethernet Web Server |
| **MH202** | OpenWebNet / HMAC | 2 workers | 100 ms | ✅ UPnP / Port 49153 | Modern scenario programmer gateway |
| **MH201** | OpenWebNet | 1 worker | 100 ms | ✅ UPnP / Port 49153 | Second-generation scenario programmer |
| **MyHomeServer1** | OpenWebNet / HMAC | 4 workers | 20 ms | ✅ SSDP | Modern cloud/local hybrid gateway |
| **MH200N** | OpenWebNet | 1 worker | 150 ms | ✅ SSDP | Second-generation scenario programmer |
| **MH200** *(Legacy)* | OpenWebNet | 1 worker | 150 ms | ✅ SSDP | Strict single-session pacing; watchdog hardened |
| **H4890 / AM4890** | OpenWebNet | 1 worker | 50 ms | ✅ SSDP | 3.5" Touch screen display IP gateway |
| **F452 / F453AV** | OpenWebNet | 1 worker | 50 ms | ✅ UPnP / Port 49153 | Audio/video & web server gateway |
| **HL4684** | OpenWebNet | 1 worker | 50 ms | ✅ SSDP | 10" Touch screen display IP gateway |
| **Legrand 3578** | OpenWebNet (Serial) | 1 worker | 50 ms | ❌ Manual (Serial) | USB / Serial gateway & OpenZigBee interface |

📖 [Read the full Hardware Gateway Profiles Guide →](https://openwebnet-ha.github.io/MyHOME/beta/configuration/gateways/)

---

## 🌟 Modern V2 Features

### Supported Entity Domains & Automations

| Domain | WHO | Capabilities |
|---|---|---|
| **`light`** | WHO=1 | On/Off, dimmers with smooth software-stepped curves, DALI DT8 Tunable White (2000K–6535K), HS/RGB colour, and hardware-offloaded bus staircase timers (`myhome.turn_on_timed`). |
| **`switch`** | WHO=1 | Relay actuators, auxiliary switches, socket actuators (switch/outlet device classes), and hardware-offloaded bus timers. |
| **`cover`** | WHO=2 | Motorized shutters and roll-ups with state tracking, position-reporting actuators, virtual travel-time positioning, and centralized shutter button triggers. |
| **`climate`** | WHO=4 | Heating, cooling, 4-pipe systems, thermostats, setpoints, fancoil 3-speed modes, offset tracking, and Central Unit 3550 (`#0`) & 4695 (`#0#1`) master coordination. |
| **`alarm_control_panel`** | WHO=5 | Central units (3485/3486), partition states (disarmed / armed away / triggered), and zone 0 broadcast sync. |
| **`binary_sensor`** | WHO=1 / 9 / 25 | Magnetic contacts, door/window sensors, PIR motion, AUX channels (1–9), and dry contact interfaces (F482/3477). |
| **`sensor`** | WHO=1 / 4 / 18 | Power meters, energy counters (total/daily/monthly), temperature probes (3475), and illuminance / lux sensors. |
| **`button`** | WHO=14 / 2 | Hardware actuator lock/unlock for maintenance (WHO=14), and cover travel-time calibration buttons (WHO=2). |
| **`media_player`** | WHO=16 | F441/F441M audio matrix zones, source routing, volume normalization, software mute, and Dynamic Streaming Proxy. |
| **`device_trigger`** | WHO=15 / 25 | Stateless CEN & CEN+ scenario pushbuttons with string-preserved addressing (`"0001"`), MAC isolation, and 8 native UI trigger types. |

### Architectural Highlights

* **Native Hardware Bus Light & Switch Timers (`WHO=1`)**: Offload countdown timers directly onto physical Legrand DIN actuators via `myhome.turn_on_timed` or standard `timer` parameters. The lights turn off automatically even if Home Assistant restarts.
* **Sound System 2.0 & Dynamic Streaming Proxy**: Stream from **Music Assistant**, **Spotify Connect**, or any HA media player to wired BTicino audio zones using an intelligent `DecoderPool` with analog gain-staging and anti-hiss auto-off.
* **Thermoregulation Central Unit Coordination (3550 / 4695)**: Master climate coordination for 99-zone (`#0`) and 4-zone (`#0#1`) central units automatically propagates whole-home heating/cooling modes across all subordinate zones.
* **Multi-Gateway Routing & Plant Isolation**: Namespaced dispatchers eliminate cross-talk across plants combining multiple gateways (e.g. F454 + MH200N).
* **Multi-Tier Priority Command Queue**: High-priority user commands (toggling lights, adjusting shutters) execute ahead of background status polling queries.
* **Self-Healing Diagnostics & Repairs**: Hardware anomalies surface as self-clearing Home Assistant repair issues (`device_health.py`).

---

## 📡 Built-In Bus Monitor Lovelace Card

The integration includes an in-band real-time bus monitor operating over the existing gateway event stream with zero extra sockets:

<p align="center">
  <img src="https://raw.githubusercontent.com/OpenWebNet-HA/MyHOME/v2-phase1-architecture/docs/images/myhome-bus-card.jpg" alt="MyHOME OpenWebNet Bus Monitor Lovelace Card" width="750">
</p>

* **Visual Card Picker**: Add directly from Home Assistant's dashboard editor by searching for **"MyHOME OpenWebNet Bus Monitor"** (`custom:myhome-openwebnet-bus-monitor`).
* **Live Feed & Frame Injector**: Color-coded badges for subsystems, ACK/NACK highlighting, pause/resume, buffer filtering, and manual frame injection with syntax validation.

📖 [Read the Bus Monitor Card Guide →](https://openwebnet-ha.github.io/MyHOME/beta/configuration/bus_monitor/)

---

## 📚 Documentation & Protocol Specifications

Comprehensive guides, specifications, and tutorials are available on our documentation site and wiki:

* 📖 **[Official Documentation Site](https://openwebnet-ha.github.io/MyHOME/beta/)**
  * [Getting Started & Installation](https://openwebnet-ha.github.io/MyHOME/beta/getting-started/installation/)
  * [Hardware Gateway Profiles](https://openwebnet-ha.github.io/MyHOME/beta/configuration/gateways/)
  * [Supported Functions & Subsystems](https://openwebnet-ha.github.io/MyHOME/beta/configuration/supported_functions/)
  * [Sound System & Dynamic Proxy](https://openwebnet-ha.github.io/MyHOME/beta/configuration/media_player/)
  * [CEN & CEN+ Scenario Automations](https://openwebnet-ha.github.io/MyHOME/beta/configuration/cen_cenplus/)
  * [Troubleshooting & Diagnostics](https://openwebnet-ha.github.io/MyHOME/beta/configuration/troubleshooting/)
* 🏛️ **[OpenWebNet Protocol & WHO Specifications Wiki](https://github.com/OpenWebNet-HA/MyHOME/wiki/OpenWebNet-Protocol-&-WHO-Specifications)**
* 🗺️ **[Development Roadmap](https://openwebnet-ha.github.io/MyHOME/beta/roadmap/)** and **[Stable v2.0.0 Pull Request #232](https://github.com/OpenWebNet-HA/MyHOME/pull/232)**

---

## 👥 Community & Credits

This integration is developed and maintained by the **[OpenWebNet-HA](https://github.com/OpenWebNet-HA)** community organization.

- **Community Hub & Discussions**: [GitHub Discussions](https://github.com/OpenWebNet-HA/MyHOME/discussions)
- **Issue Tracker & Traces**: [GitHub Issues](https://github.com/OpenWebNet-HA/MyHOME/issues)
- **Phase 1 & 2 Pull Request**: [PR #232](https://github.com/OpenWebNet-HA/MyHOME/pull/232)

Special thanks to:
* **[@anotherjulien](https://github.com/anotherjulien)** for creating the original MyHOME integration.
* **[@GreenGrassBlueOcean](https://github.com/GreenGrassBlueOcean)** for the modernized v2 architecture, gateway profiles, streaming proxy, and test suite.
* **[@GianlucaCh](https://github.com/GianlucaCh)** for contributing the comprehensive 15-manual BTicino/Legrand specification archive and WHO 24 specs.
* **[@xtimmy86x](https://github.com/xtimmy86x)** for the frontend administration panel and hardware diagnostics.
* All community testers whose authentic on-wire traces keep our CI test suite grounded in real hardware.

---

## 📄 License

Licensed under the [Apache License 2.0](https://github.com/OpenWebNet-HA/MyHOME/blob/v2-phase1-architecture/LICENSE), the same license as Home Assistant Core.
