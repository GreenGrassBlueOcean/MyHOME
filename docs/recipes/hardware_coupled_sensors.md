# Hardware-Coupled Sensors & Twilight Curfew Control

This recipe explains how to manage and decouple physical **BTicino MyHOME sensors** (such as external twilight photocells, contact interfaces, or motion sensors) that share an SCS bus address with a lighting actuator.

---

## The "Miracle" Light: Understanding Hardware Coupling

In classic BTicino MyHOME installations, point-to-point automation is achieved through **physical configurator plugs** ($A$ and $PL$). Installers frequently configure a control interface with the **identical $A$ and $PL$ address** as an actuator relay:

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

### What Happens on the Wire
1. **At Dusk**: As natural light fades, the external twilight switch closes its dry contact.
2. **SCS Broadcast**: The **BTicino 3477** contact interface senses this transition and broadcasts an unsolicited lighting command on the bus:
   $$\text{*1*1*98\#\#}$$
3. **Actuator Switching**: Relay Channel 4 on the **F411/4** receives this command and closes, turning on the light.
4. **Manual Control**: When you turn off the light from Home Assistant, an app, or a wall switch, the gateway sends `*1*0*98##`. The actuator opens its relay and the light turns off. Because the 3477 only emits on state transitions (edge-triggered), it does not contest your turn-off command.
5. **At Dawn**: When daylight returns, the twilight photocell opens its contact, causing the 3477 to broadcast `*1*0*98##`.

---

## Architectural Challenges in Home Assistant

1. **Shadowed Sensor State**: Because the 3477 transmits standard `WHO = 1` (Lighting) frames to address `98`, Home Assistant discovers and displays address `98` strictly as a `Light` entity. The physical contact state of the twilight sensor is obscured by the light's state.
2. **No Native Curfew**: Without an automation layer, the light remains on all night until dawn unless manually turned off.
3. **Hardware-Enforced Activation**: Because the command executes directly on the physical SCS bus, the initial turn-on at dusk happens at the hardware level before Home Assistant can intercept it.

---

## Solution Strategy 1: Non-Invasive Dusk Curfew (Blueprint)

If you cannot easily modify physical configurator plugs in electrical panels, use Home Assistant to add an intelligent curfew and synchronization layer on top of the hardware behavior.

### 🌟 Using the Dusk Curfew Blueprint

The integration includes a dedicated automation blueprint designed specifically for hardware-coupled MyHOME sensors:

* **File**: `blueprints/automation/myhome/dusk_curfew.yaml`
* **Features**:
  * **Bedtime Curfew**: Forces the light off at a specified time (e.g., `23:00:00`).
  * **Max Run Duration**: Optional timeout (e.g. 180 minutes) to guarantee the light turns off even on dark winter afternoons.
  * **Companion Synchronization**: When the hardware twilight light turns on at dusk, automatically turns on other outdoor lights (e.g., patio lights, garden spots) and turns them off together at curfew.
  * **Presence Gating**: Optionally turns the light off after a brief timeout if nobody is home.

### Example Automation Configuration

```yaml
alias: "Outdoor Light 98 - Dusk Curfew & Companion Sync"
use_blueprint:
  path: myhome/dusk_curfew.yaml
  input:
    target_light: light.outdoor_facade_light
    curfew_time: "23:00:00"
    max_duration: 240
    sync_lights:
      entity_id:
        - light.garden_pathway
        - light.driveway_spots
    presence_entity: zone.home
    away_timeout: 15
```

---

## Solution Strategy 2: Clean Hardware Decoupling (Full HA Authority)

If you want Home Assistant to have **100% software control** over whether and when the light turns on, you can decouple the 3477 contact interface from the lighting relay.

### Option A: Move 3477 to an Unused Address
1. Locate the **BTicino 3477** module.
2. Change the $PL$ configurator plug to an unused address in Area 9 (e.g., change from $PL=8$ to $PL=10$, where no physical relay exists).
3. **Result**: When darkness falls, the 3477 sends `*1*1*910##`. No physical relay clicks or activates.
4. In Home Assistant, create an automation triggered by the state of `light.light_910` (or the bus event) to command `light.light_98` according to your own schedules, presence conditions, and weather logic.

### Option B: Configure 3477 as a Dry Contact Interface (`WHO = 25`)
1. Reconfigure the 3477 into **Dry Contact Mode** (either using physical configurators or virtual configuration via **MyHOME_Suite**).
2. **Result**: The interface sends OpenWebNet `WHO = 25` events instead of `WHO = 1` lighting commands.
3. In Home Assistant, the device is auto-discovered as an independent **`binary_sensor`** (e.g. `binary_sensor.twilight_sensor`).
4. You now have complete separation of concerns:
   * `binary_sensor.twilight_sensor` accurately tracks daylight/darkness.
   * `light.outdoor_light` remains a pure actuator controlled strictly by Home Assistant.
