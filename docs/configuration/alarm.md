Burglar Alarm entities are developed for OpenWebNet **WHO = 5** (`alarm_control_panel`).

The integration supports both **Dynamic Bus Auto-Discovery** and explicit **YAML Configuration** via `myhome.yaml`.

---

# Supported Hardware

Central intrusion alarm units and partition devices, including:
- **BTicino 3485** / **3486** Alarm Central Units
- **BTicino HC4600** / **L4600** Keypads and control units
- **BTicino 3481** and zone expansion modules
- Technical alarm transmitters (water/gas leak detectors)

---

# Supported Features & States

The `alarm_control_panel` platform provides:
- **States**:
  - `disarmed` (deactivated / idle / maintenance)
  - `armed_home` (partial / active zone)
  - `armed_away` (total system active / engaged)
  - `triggered` (intrusion alarm, technical alarm, tampering, anti-panic, silent alarm)
- **Features**:
  - `ARM_AWAY` (`*5*1*<where>##`)
  - `ARM_HOME` (`*5*1*<where>##`)
  - `DISARM` (`*5*2*<where>##`)
  - `TRIGGER` (`*5*17*<where>##` panic alarm)
- **Global Broadcast Zone 0 Listening**:
  Entities automatically subscribe to global broadcast zone 0 telemetry (`myhome_update_<mac>_5_0`) alongside their specific zone/partition address (`myhome_update_<mac>_5_<where>`), guaranteeing synchronized state updates across all alarm panels.

---

# Configuration Structure

In your `/config/myhome.yaml`:

```yaml
f454:
  mac: '00:03:50:xx:xx:xx'
  alarm_control_panel:
    central_alarm:
      where: '0'
      name: Central Alarm
      manufacturer: BTicino
      model: 3486
    zone_1:
      where: '1'
      name: Ground Floor Alarm
      manufacturer: BTicino
      model: 3485
```

### Parameters
* `where` (*Required*): The OpenWebNet address of the alarm partition or central unit.
  - `'0'`: Central unit / global system broadcast
  - `'1'` through `'8'`: Specific partition or zone
* `name` (*Required*): Friendly name for the entity in Home Assistant.
* `manufacturer` (*Optional*, default: `BTicino S.p.A.`): Hardware manufacturer string.
* `model` (*Optional*, default: `Burglar Alarm` / `F4201`): Hardware model string.

---

# Dynamic Bus Auto-Discovery & Testing

You do not need to manually configure `myhome.yaml` if your alarm unit communicates on the SCS bus:
1. **Dynamic Auto-Discovery**: Any incoming `OWNAlarmEvent` frame received on the SCS bus (e.g. `*5*1*0##` for arming, `*5*2*0##` for disarming, or `*5*15*0##` for intrusion) automatically discovers and creates the `alarm_control_panel` entity.
2. **Interactive Testing via Bus Monitor**: You can test the platform directly in Home Assistant using the Lovelace `<myhome-bus-card>` Command Injector:
   - **Query Central Status**: `*#5*0##`
   - **Query Zone Status**: `*#5*#1##` (for zone 1)
   - **Arm System**: `*5*1*0##`
   - **Disarm System**: `*5*2*0##`
   - **Trigger Panic**: `*5*17*0##`
   - **Simulate Intrusion Alarm**: `*5*15*0##`
