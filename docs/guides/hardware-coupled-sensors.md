# Hardware-Coupled Sensors & Twilight Curfew Guide

This guide explains how to identify, manage, and decouple physical **BTicino MyHOME sensors** (such as external twilight photocells, contact interfaces, or motion sensors) that share an SCS bus address with a lighting actuator relay.

---

## Understanding Hardware Coupling

In classic BTicino MyHOME installations, point-to-point automation is established through **physical configurator plugs** (`A` and `PL`). Installers frequently configure a control interface with the **identical `A` and `PL` address** as an actuator relay:

```text
[External Twilight Switch] (Photocell)
         │ dry contact
         ▼
[BTicino 3477 Contact Interface]  (Model 129, Configured: A=9, PL=8)
         │ SCS Bus Event: *1*1*98##
         ▼
[BTicino F411/4 Relay Actuator]   (Model 130, Channel 4: A=9, PL4=8)
         │ relay closure
         ▼
[Outdoor Light Fixture]
```

### Diagnostic Investigation via WHO 1001

You can confirm whether an address is hardware-coupled by querying OpenWebNet diagnostics (`WHO 1001`):

1. **Query Installed Device Models (`DIMENSION 1`)**:
   Send `*#1001*WHERE*1##` (for example, address `98`: `*#1001*98*1##`).
   When two devices share the same address, the gateway returns two separate diagnostic responses:
   - `*#1001*98*1*130*6##`: Identifies **Model 130** (BTicino F411/4 4-relay modular actuator, 6 configurator positions).
   - `*#1001*98*1*129*5##`: Identifies **Model 129** (BTicino 3477 Basic Contact Interface, 5 configurator positions).

2. **Read Back Physical Configurators (`DIMENSION 4`)**:
   Send `*#1001*WHERE*4##` (for address `98`: `*#1001*98*4##`):
   - `*#1001*98*4*9*5*6*7*8*15##`: Reports configurators `A=9`, `PL1=5`, `PL2=6`, `PL3=7`, `PL4=8`, `M=15`. Channel 4 corresponds to `PL4=8`, directly creating SCS lighting address `98`.
   - `*#1001*98*4*9*8*0*0*15*0##`: Reports configurators `A=9`, `PL=8`, `M=0`, configuring the 3477 to broadcast commands directly to address `98`.

> [!NOTE]
> The Model 130 and Model 129 replies above were captured and verified directly on a physical MH200 gateway plant. Readback of inserted physical configurators via `DIMENSION 4` (`*#1001*WHERE*4*...##`) is defined in the OpenWebNet WHO 1001 diagnostic specification; however, some gateway models or older firmware revisions (such as early MH200/MH201 versions) may NACK `DIMENSION 4` requests and only report `DIMENSION 1`.

### What Happens on the Wire

1. **At Dusk**: As ambient light drops, the external twilight switch closes its dry contact.
2. **SCS Broadcast**: The **BTicino 3477** senses the transition and broadcasts an unsolicited lighting command:
   `*1*1*98##`
3. **Actuator Switching**: Relay Channel 4 on the **F411/4** receives this command directly on the SCS bus and closes, illuminating the outdoor light.
4. **Edge-Triggered Behavior & Manual Control**: The 3477 operates strictly on state transitions (edge-triggered). It transmits a single command upon contact closure and does **not** cyclically re-assert state while closed. When you turn off the light from Home Assistant, an app, or an SCS wall switch, the gateway sends `*1*0*98##`. The actuator opens its relay and remains off for the rest of the evening without being overridden by the sensor.
5. **At Dawn**: When daylight returns, the twilight switch contact opens, causing the 3477 to broadcast `*1*0*98##`.

---

## Architectural Challenges in Home Assistant

1. **Hardware-Level Activation**: The initial turn-on at dusk occurs directly on the SCS wire before Home Assistant can intercept or filter it.
2. **Shadowed Sensor State**: Because the 3477 transmits standard `WHO = 1` (Lighting) frames to address `98`, Home Assistant discovers address `98` as a single `Light` entity. The physical state of the photocell contact is obscured by the light relay state.
3. **No Native Curfew**: Without an automation layer, the light remains on all night until dawn unless manually switched off.

---

## Solution Strategy 1: Non-Invasive Dusk Curfew (Blueprint)

If you cannot easily modify physical configurator plugs in electrical panels, use Home Assistant to add an intelligent curfew and companion synchronization layer on top of the hardware behavior.

### 🌟 Using the Dusk Curfew Blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FOpenWebNet-HA%2FMyHOME%2Fblob%2Fv2-phase1-architecture%2Fblueprints%2Fautomation%2Fmyhome%2Fdusk_curfew.yaml)

> [!TIP]
> During the v2 beta development cycle, the badge above points to the `v2-phase1-architecture` branch. You can also import directly from this URL in **Settings → Automations & Scenes → Blueprints → Import Blueprint**.

* **Source File**: `blueprints/automation/myhome/dusk_curfew.yaml`
* **Manual Installation**:
  Download `dusk_curfew.yaml` and save it to `<config>/blueprints/automation/myhome/dusk_curfew.yaml` in your Home Assistant configuration directory.
* **Key Features**:
  - **Bedtime Curfew**: Enforces a strict cutoff time (`curfew_time`, e.g. `23:00:00`) to turn off the hardware-coupled light and all companion lights.
  - **Configurable Morning Curfew End**: Configurable `curfew_end_time` (default `06:00:00`), after which daytime behavior resumes.
  - **Max Run Duration**: Optional timeout (e.g. 180 minutes) to guarantee the light turns off even on dark winter afternoons when dusk occurs early.
  - **Companion Synchronization**: When the hardware twilight light turns on at dusk, automatically illuminates additional outdoor lights (e.g. pathway spots, facade accents) and turns them off together at curfew.
  - **Presence Gating**: Supports `zone.*` (evaluates as away when occupant count is 0), `person.*`, `device_tracker.*`, `group.*`, or `binary_sensor.*`. When occupants are away, reduces the runtime to a configurable `away_timeout`. Dynamic presence tracking automatically turns off lights if occupants leave mid-evening.
  - **Optional Daylight Guard**: Optional `after_sunset_only` (default `false`) gates companion activation to astronomical night. Keep disabled if your twilight photocell trips before sunset on overcast or winter afternoons.
  - **Service & Maintenance Overrides**:
    - **Service Power (Gardener / Power Tools)**: Energizes the circuit immediately on demand during daylight hours, suspends curfew and presence shutoffs, and features a safety auto-reset timer (default 4 hours) so outdoor power is never left on indefinitely.
    - **Safety Lockout (Electrician / Wiring Work)**: Forces the circuit OFF immediately and intercepts/blocks any dusk photocell triggers or indoor wall switch presses while lamps or wiring are being serviced.
    - **Pause Automation**: Leaves lights under manual control, temporarily bypassing all curfew and timer logic.
  - **Reconnection Resilience**: Uses `from: "off"` to ensure temporary gateway drops or Home Assistant restarts (`unavailable -> on`) do not re-run curfew sequences in the middle of the night.
  - **Post-Curfew Safety**: Automatically turns off the light after a 2-minute safety grace period if it is turned on during curfew hours.

### Example Automation Configuration

> [!NOTE]
> By default, the MyHOME integration discovers lights with names reflecting their bus address (e.g. `light.light_98`). If you have renamed your entity in Home Assistant (e.g. `light.outdoor_facade_light`), provide that entity ID in the `target_light` field.

```yaml
alias: "Outdoor Light 98 - Dusk Curfew & Companion Sync"
use_blueprint:
  path: myhome/dusk_curfew.yaml
  input:
    target_light: light.light_98
    curfew_time: "23:00:00"
    curfew_end_time: "06:00:00"
    max_duration: 180
    sync_lights:
      entity_id:
        - light.garden_pathway
        - light.driveway_spots
    presence_entity: zone.home
    away_timeout: 15
    after_sunset_only: false
    # Optional Gardener / Maintenance Override Helper
    override_entity: input_boolean.gardener_power
    override_mode: service_power
    service_timeout_hours: 4
```

### Temporary Overrides: Gardener Power & Electrician Safety

Outdoor lighting circuits frequently double as power lines for garden sockets (lawnmowers, hedge trimmers, pumps) or require maintenance:

1. **Gardener Service Power**: Create a helper (`input_boolean.gardener_power` in **Settings → Devices & Services → Helpers**). When turned on (via a dashboard button or NFC tag by the shed), the automation energizes `light.light_98` immediately and suspends curfew/presence turn-offs. After `service_timeout_hours` (e.g., 4 hours), it automatically turns off the circuit and resets the helper.
2. **Safety Lockout**: When servicing light fixtures or pruning near live cabling, configure `override_mode: safety_lockout` with an `input_boolean.lighting_maintenance_lock` helper. When active, the automation immediately forces the light off and actively suppresses any photocell dusk trips, ensuring 230V is never applied to the circuit while someone is working on it.


---

## Solution Strategy 2: Clean Hardware Decoupling (Full HA Authority)

If you prefer Home Assistant to hold **100% software authority** over whether and when the outdoor lights illuminate, decouple the 3477 contact interface from the lighting relay.

### Option A: Move 3477 to an Unused Address (Physical Decoupling)

1. Locate the **BTicino 3477** module in your electrical panel.
2. Remove the `PL` configurator plug and replace it with an address in Area 9 where no physical relay exists (e.g. change from `PL=8` to `PL=10`).
3. **Result**: At dusk, the 3477 broadcasts `*1*1*910##`. No physical relay clicks or turns on.
4. In Home Assistant, address `910` appears as `light.light_910` (or dispatches a `myhome_event`).
5. Create a standard Home Assistant automation triggered by `light.light_910` turning on to evaluate weather, presence, and schedule before commanding the actual fixture `light.light_98`.

### Option B: Configure 3477 as a Dry Contact Interface (`WHO = 25`)

1. Using **MyHOME_Suite** (Virtual Configuration), reconfigure the 3477 contact interface into **Dry Contact Mode** (`WHO = 25`, virtual address range 1..201).
2. **Result**: The interface transmits OpenWebNet dry contact frames where `WHAT` is `31` for contact closed and `32` for contact open:
   - Contact closed (dusk): `*25*31#1*WHERE##`
   - Contact opened (dawn): `*25*32#1*WHERE##`
3. In Home Assistant, declare the contact in `myhome.yaml` using its configured virtual address (for example `where: "15"`):
   ```yaml
   binary_sensor:
     - who: "25"
       where: "15"
       name: "Twilight Sensor"
       device_class: "opening"
   ```
4. You now have full separation of concerns:
   - `binary_sensor.twilight_sensor` accurately mirrors daylight/darkness in real time.
   - `light.light_98` remains a pure actuator controlled exclusively by Home Assistant schedules, presence logic, and automations.
