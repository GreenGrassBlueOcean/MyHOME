# Migrating from SDomotica to Native MyHOME

This guide provides a step-by-step, zero-touch migration path for users transitioning from the legacy **SDomotica** bridge to the native Home Assistant **MyHOME (OpenWebNet)** integration.

---

## 📌 Overview

Many Legrand & BTicino MyHOME installations were previously integrated into Home Assistant via SDomotica (either through MQTT packages or the custom bridge add-on). In these setups, Home Assistant entity IDs are automatically generated based on each installation's SCS bus addresses and device types:

- **Lights & Relays**: `light.sdomoticabticino<where>`
- **F422 Bus Interfaces**: `light.sdomoticabticino<where>_4_<interface>`
- **Covers & Shutters**: `cover.sdomoticabticino<where>`
- **Climate & Thermoregulation**: `climate.sdomoticabticino_4_<zone>`
- **Audio Sound System**: `media_player.audio_zone_<zone>`
- **Burglar Alarm**: `alarm_control_panel.sdomoticabtalarm`
- **Energy & Power Sensors**: `sensor.sdomoticabticino<where>`
- **Auxiliary Contacts / Binary Sensors**: `binary_sensor.sdomoticabticino<where>`

### Guarantees
1. **Zero Dashboard Changes**: Existing Lovelace cards, entity grids, and charts remain 100% operational with your exact entity IDs.
2. **Zero Automation Changes**: Automations referencing your existing entities continue working without renaming.
3. **Preserved History & Areas**: Historical database statistics and room/area assignments are preserved.

---

## 🚀 Migration Options

You can migrate using either:
1. **The Automated Migration CLI Tool (`scripts/migrate_from_sdomotica.py`)** *(Recommended)*
2. **Direct `myhome.yaml` Configuration**

---

### Option 1: Automated Migration CLI Tool

The MyHOME repository includes a multi-source automated migration utility located at `scripts/migrate_from_sdomotica.py`.

#### Step 1: Preview Entities (Dry Run)
Inspect your installation and preview all discovered entities:

```bash
# Auto-discover from HA config directory:
python scripts/migrate_from_sdomotica.py --config-dir /config --dry-run
```

#### Step 2: Generate `myhome.yaml`
Outputs a clean, schema-compliant `myhome.yaml` pre-keyed to your exact entity IDs:

```bash
python scripts/migrate_from_sdomotica.py --config-dir /config --generate-yaml /config/myhome.yaml --gateway-mac 00:03:50:xx:xx:xx
```

Sample generated `myhome.yaml`:

```yaml
f454:
  mac: "00:03:50:xx:xx:xx"

  light:
    sdomoticabticino_12:
      where: "12"
      name: "Cucina"
    sdomoticabticino_19:
      where: "19"
      name: "Dimmer TV"
      dimmable: true

  cover:
    sdomoticabticino_31:
      where: "31"
      name: "Veranda"
      advanced: false
      travel_time: 20

  climate:
    sdomoticabticino_4_1:
      zone: "1"
      heat: true
      cool: false
      name: "Soggiorno"
```

#### Step 3: In-Place Entity Registry Migration
To seamlessly adopt entities directly inside Home Assistant's entity registry:

```bash
ha core stop
python scripts/migrate_from_sdomotica.py --config-dir /config --migrate-registry --gateway-mac 00:03:50:xx:xx:xx
ha core start
```

---

## 📋 SDomotica Device Mapping Catalog

| SDomotica Type | Description | MyHOME Platform | WHO | Parameters |
| :--- | :--- | :--- | :---: | :--- |
| `Lightbulb` (`can_dim: false`) | Standard on/off light | `light` | 1 | `where: "<addr>"` |
| `Lightbulb` (`can_dim: true`) | Dimmable actuator | `light` | 1 | `where: "<addr>"`, `dimmable: true` |
| `Lightbulb` (`"41#4#01"`) | Light via F422 interface | `light` | 1 | `where: "41"`, `interface: "01"` |
| `Outlets` | Controlled power outlet | `switch` | 1 | `where: "<addr>"`, `class: "outlet"` |
| `Switch` | SCS switch relay | `switch` | 1 | `where: "<addr>"`, `class: "switch"` |
| `Windows` | Standard shutter/blind | `cover` | 2 | `where: "<addr>"`, `advanced: false` |
| `WindowsAdvance` | Position-aware shutter (%) | `cover` | 2 | `where: "<addr>"`, `advanced: true` |
| `Sensor3477` | 3477 Aux contact | `binary_sensor` | 25 | `where: "<addr>"` |
| `Energy` | Central energy meter | `sensor` | 18 | `where: "<addr>"`, `class: "energy"` |
| `F522`, `F523` | Controlled load actuator | `sensor` | 18 | `where: "<addr>"`, `class: "power"` |
| `Thermostat` | 99-zone central heating | `climate` | 4 | `zone: "<addr>"`, `heat: true`, `cool: false` |
| `4ZThermo` | 4-zone heating & cooling | `climate` | 4 | `zone: "<addr>"`, `heat: true`, `cool: true` |
| `TemperatureSensors` | External temperature probe | `sensor` | 4 | `where: "<addr>"`, `class: "temperature"` |
| `SecuritySystem` | Burglar alarm central | `alarm_control_panel` | 5 | `where: "<zone>"` |
