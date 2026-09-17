# Installation Guide

This guide covers installing the **MyHOME** integration in Home Assistant.

---

## Prerequisites

- **Home Assistant**: Home Assistant Core 2026.3 or newer.
- **Physical Connection**: An OpenWebNet gateway connected to your local network (Ethernet IP) or via USB / Serial.

---

## Option 1: Installation via HACS (Recommended)

HACS (Home Assistant Community Store) simplifies downloading and updating custom integrations.

1. Open **HACS** in your Home Assistant sidebar.
2. Click the three dots (⋮) in the top-right corner and select **Custom repositories**.
3. Enter the repository URL:
   ```text
   https://github.com/OpenWebNet-HA/MyHOME
   ```
4. Select category: **Integration**.
5. Click **Add**.
6. Search for **MyHOME** in HACS, click **Download**, and choose the latest version (`v2.0` or beta release).
7. Restart Home Assistant:
   - Navigate to **Developer Tools** → **YAML** → **Restart** (or **Settings** → **System** → **Restart**).

---

## Option 2: Manual Installation

> [!CAUTION]
> **Manual Installation Pitfall**: Always extract `myhome` into `custom_components/myhome/`. Never extract into `custom_components/` directly, and never keep backup copies inside `custom_components/` (e.g. `custom_components/myhome_backup/`). In Home Assistant 2026.9+, a stray `__init__.py` in the root of `custom_components/` causes Home Assistant to load *no* custom integrations at all.

1. Download the `myhome.zip` archive from the [Latest Release](https://github.com/OpenWebNet-HA/MyHOME/releases).
2. On your Home Assistant host, navigate to your configuration folder (where `configuration.yaml` is located).
3. Create a `custom_components/` directory if one does not already exist.
4. Extract the contents so that the integration files reside at:
   ```text
   /config/custom_components/myhome/__init__.py
   /config/custom_components/myhome/manifest.json
   ...
   ```
5. Restart Home Assistant.

---

## Next Steps

Once Home Assistant has restarted, proceed to [Gateways & Connection Setup](../configuration/gateways.md) to add your gateway via the UI.
