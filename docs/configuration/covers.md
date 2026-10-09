# Covers & Shutters (WHO = 2)

The **MyHOME** integration provides full control for motorized shutters, blinds, venetian blinds, and curtains operating on OpenWebNet **WHO = 2**.

In v2, setup and management are **100% UI-first**: entities are automatically discovered from the SCS bus, and position calibration is handled natively through Home Assistant buttons and services without requiring manual YAML configuration files.

---

## 🚀 Auto-Discovery

When your gateway connects to Home Assistant:

1. **Dynamic Bus Discovery**: The integration listens to OpenWebNet `WHO = 2` frames and scans the bus.
2. **Device Creation**: Each physical shutter actuator (`WHERE = 1..99` or area/point addresses) is registered as a Home Assistant `cover` device linked to your MyHOME Gateway.
3. **UI Customization**: You can rename the entity, assign it to an Area (e.g. *Living Room*, *Master Bedroom*), or change its icon directly in the Home Assistant UI (**Settings → Devices & Services → Entities**).

---

## 🎛️ Cover Types: Standard vs. Advanced

The integration distinguishes between two types of MyHOME covers:

| Cover Type | Supported Hardware | Position Control (`set_cover_position`) | How Position is Handled |
| :--- | :--- | :---: | :--- |
| **Advanced Covers** | Legrand Céliane `67557`, Axolute `H4661M2`, Livinglight `LN4661M2`, BTicino `F401` (advanced mode) | ✅ Native | Actuator hardware reports exact physical position back to the bus (`Dimension = 10`). |
| **Standard (Timed) Covers** | Standard relay actuators (`F411/2`, `F411U2`, standard `F401`, older flush-mount units) | ✅ Estimated | Actuator has no position feedback. The v2 runtime estimates position from the elapsed share of the **travel time** (`travel_time_down` and `travel_time_up`). |

> [!NOTE]
> Every discovered cover starts as a **timed** cover. Position-reporting hardware is not detected automatically: set `advanced_shutter: true` for that cover in `/config/myhome.yaml` (see [Troubleshooting → Cover position is wrong](troubleshooting.md#cover-position-is-wrong)). Advanced covers refuse `myhome.calibrate_cover` and travel times in `myhome.set_cover_travel_time`, as they do not need a travel time (a Venetian blind with `slat_tilt` still accepts `slat_time` there).

---

## ⏱️ Timed Cover Position Engine

For standard covers without hardware position feedback, the integration provides a software estimator enabling full `open_cover`, `close_cover`, `stop_cover`, and slider-based `set_cover_position` support:

* **Direction-Aware Travel Times**: Because gravity and motor friction cause shutters to fall faster than they rise, the v2 engine tracks separate `travel_time_down` and `travel_time_up` durations (default: `25.0s`).
* **Frame Anchor Timing**: The run timer starts when the direction frame is **written to the gateway**, not when Home Assistant queues it.
* **Echo Suppression**: The gateway relays a momentary stop status (~0.1 s) followed by translation and the actual motor start (~0.55 s). The v2 engine recognizes these as command echoes, re-anchoring the timer to the true motor start rather than falsely treating them as manual stop commands.
* **Motor Start-Up Floor (`min_motor_pulse`)**: A tubular motor needs a moment after the relay closes before the curtain moves. On an F454 with Somfy Ilmo 50 WT motors (20.4 s travel), 1 % steps (~0.2 s) clicked the relay without moving the curtain, while 2 % steps (~0.4 s) moved it ([#466](https://github.com/OpenWebNet-HA/MyHOME/issues/466)). A position change that would run shorter than the configured floor runs for `min_motor_pulse` seconds (default: `0.4 s`, configurable per cover via YAML `min_motor_pulse` or `myhome.set_cover_travel_time`; `0.0` disables), and the estimate books the movement of that longer run: on a 5 s cover with the default 0.4 s floor, 50 % → 51 % ends at 58 %. Other motors may need more or less.
* **Stop Status Re-Anchoring**: When a timed run is stopped, the estimate is provisionally frozen at the stop write. If the gateway relays the stop status (`*2*0*<WHERE>##`) within the echo window (measured at 34–47 ms, median 42 ms on a MyHOMEServer1 and 64–120 ms on an F461), the final position and `last_run_seconds` are re-anchored to `stop status - start anchor` ([#705](https://github.com/OpenWebNet-HA/MyHOME/issues/705)). Gateways that do not relay the stop status keep the write-time freeze.
* **0 % and 100 % Are Full Runs**: Setting position to 0 % or 100 % sends a plain close / open, exactly like the buttons, and lets the motor stop on its limit switch instead of timing a stop. This also happens when the cover already reports 0 % or 100 %, so it is the way to put a drifted estimate back in step. A short move whose run would reach an end becomes a full run to that end too. No stop frame is sent, so the entity reports `opening` / `closing` until the actuator's own stop status arrives, which can be long after the curtain reached the end (about 60 s on one MyHOMEServer1) or never on a gateway that does not relay it. The integration therefore settles on 0 % / 100 % once the stored travel time plus 2 s has passed, without a stop frame. That can be a few seconds before a slow curtain physically arrives; automations waiting for `open` / `closed` see the state change at that point. The open and close buttons are unchanged and still wait for the actuator's status.
* **Resynchronization**: Running a cover to its full travel limit (fully open or fully closed) automatically resets any minor timing drift to 0% or 100%.

> [!NOTE]
> Small moves can still drift. The estimate assumes the curtain moves for the whole run. A motor's start-up time (measured only on the Somfy Ilmo 50 WT in [#466](https://github.com/OpenWebNet-HA/MyHOME/issues/466); another installation measured none on runs of about 0.76 s) is lost on every run, and the slat phase of a roller shutter with slats is booked as travel (one report: a 40 % request from fully closed lifted the curtain only about 18 % of its travel). A series of short moves can therefore book more travel than the curtain made. Send the cover to 0 % or 100 % now and then to re-sync it.
>
> Venetian blinds are handled as a plain lift cover: lift only, no tilt, and no fine positioning.

> [!WARNING]
> **Half the time is not half the height.** The estimate is linear: 50 % means the motor ran for half of the stored travel time. A roller shutter does not move at constant speed — coming down from the top the curtain runs fast on a full roll and is well past the middle at half time; going up from the bottom the first seconds go into gathering the slats and the curtain barely moves. Measured on a 107 cm shutter with exact travel times: `set_cover_position: 50` stopped at 27 cm from the sill coming down and at 37 cm going up, against a true midpoint of about 53 cm, while Home Assistant reported 50 % both times. The end positions (0 % / 100 %) are exact; intermediate positions are approximate and differ by direction. Treat the slider as "roughly there", not as a measurement — this applies to calibrated and manually set times alike.

**Advanced covers** track their own level, but the actuator turns a level change into a timed run the same way, so a 1 % change is just as likely to click without moving. The integration widens a change of less than 2 % to 2 % (50 % → 51 % is sent as 52 %), except while the cover is moving (it then reports the level it started from, so the request goes out as asked), and sends 0 % and 100 % as plain close / open full runs. The 2 % comes from the 20.4 s motor above; a faster motor may need more, and the behaviour of the level command for small changes is inferred from the step commands in that trace, not captured.

---

## 📐 Calibrating Travel Time (Zero YAML)

You never need to edit YAML files to calibrate travel times in v2.

> [!IMPORTANT]
> **Actuator Requirements for Automated Calibration**
> Automated on-bus calibration relies entirely on the actuator emitting a stop frame (`*2*0*<WHERE>##`) at the moment the shutter physically reaches its end stop.
>
> * **Trimmed Actuators**: If the installer trimmed the actuator's mechanical or potentiometer run-time limit to match the physical shutter, automated calibration will measure your shutter travel times accurately down to tenths of a second.
> * **Factory 60 s Cutoff Actuators**: If the actuator run-time was left at the factory default cutoff (~60 s), the actuator will not stop when the shutter reaches the bottom; it will continue running until the 60 s hardware timer expires. The integration detects this condition and **safely rejects the calibration** to prevent saving inaccurate 60 s run times. For these actuators, use [Method 3: Set Explicit Travel Time via Service Action](#method-3-set-explicit-travel-time-via-service-action) instead.
>
> **How to spot your case**: press the button once and watch the first (opening) run. If the motor keeps running for about a minute after the shutter is fully up, your actuator is at its factory limit and cannot be measured over the bus — the button will refuse every time. You will not see the refusal in the UI (the button does not wait for the result): it is logged, and the `myhome_cover_calibration` event reports `phase: failed`. Nothing is stored.
>
> **Which actuators** (from datasheets and user reports, awaiting full hardware traces under #466): the `F411/2`, `F411/4` and `F411U2` have a configurable timed stop — the physical *M* configurator, or 1–60 s in MyHOME_Suite. Setting it a couple of seconds above the real travel allows these to be measured; a run that ends at ~60 s indicates it was left at its factory default `M=0`. The `F401` and the `H4661M2` / `LN4661M2` family learn the real travel themselves (*Push&Learn*), which is the case where the end stop on the bus is genuine.

### Method 1: Automated Calibration Button on Device Page
Every cover device in Home Assistant includes a dedicated configuration button entity (on a position-reporting cover a press is refused, as there is nothing to measure):

* **Entity**: `button.<name>_calibrate_travel_time`
* **Icon**: `mdi:ruler-square-compass`

When you click **Calibrate Travel Time**, the integration performs a fully automated 3-step calibration sequence on the bus:

1. **Full Open (Reference Sync)**: The shutter is driven fully **UP** to reach the mechanical top limit, establishing a reliable reference position.
2. **Full Close (Timed)**: After a brief settling pause, the shutter is driven fully **DOWN**. The integration monitors the OpenWebNet bus to precisely record `travel_time_down` (from motor start to actuator stop frame).
3. **Full Open (Timed)**: After another pause, the shutter is driven fully **UP** back to the top limit, recording `travel_time_up`.
4. **Saved Automatically**: Both measured times are persisted into Home Assistant's config entry (`cover_travel_times`) and shown as the cover's `travel_time_down` / `travel_time_up` attributes, with `calibration_source: measured` and a `calibrated_at` timestamp. The shutter ends in the 100% open position. Progress is published on the event bus as `myhome_cover_calibration` (`phase`: `queued`, `start`, `run`, `done`, `failed`), so you can follow or automate on it.

> [!NOTE]
>
> * **Do not press the button a second time**: The sequence is fully automated. A second press while the run is active is refused (*"… is already being calibrated"*); the button fires the action without waiting for it, so the refusal only shows up in the Home Assistant log, not in the UI. Each run also gives up with *no stop status from the actuator* if no stop frame arrives within 180 s.
> * **Do NOT stop the shutter during calibration — neither from the cover entity nor from the wall**: A stop press from either place puts a plain stop frame (`*2*0*<WHERE>##`) on the bus, which is the very same frame the actuator emits when the shutter reaches its end stop. The integration cannot tell them apart, so it treats the stop as the end of the run and stores the partial elapsed time (e.g. 5–6 seconds) as the calibrated travel time.
> * **How to Abort Safely**: The one safe way out is the `myhome.stop_cover_calibration` action in **Developer Tools → Actions**: it marks the run as interrupted and stores nothing. Call it while the shutter is moving — a call that lands in the one-second pause between two runs is not seen and the next run starts. (Driving the shutter in the *opposite* direction from the wall is also recognised as an interruption, because it arrives as an explicit open/close command rather than a stop — but prefer the action.)

### Method 2: Calibrate All Covers Sequentially
On your gateway device page, click **Calibrate All Covers** (`button.<gateway name>_calibrate_all_covers`, e.g. `button.f454_gateway_calibrate_all_covers`). It calls `myhome.calibrate_cover` for every enabled cover of that gateway; a per-gateway lock runs them **one at a time**, because two motors moving on one paced session would make the timings meaningless. Covers still waiting report `phase: queued`. Position-reporting (advanced) covers are refused with an error in the log and the others continue. `myhome.stop_cover_calibration` stops the running cover and drops the whole queue.

### Method 3: Set Explicit Travel Time via Service Action
If your actuators enforce the 60-second factory cutoff, if your gateway is single-session (such as MH200 / MH200N), or if you already know the exact run duration (e.g. from a handheld stopwatch or technical datasheet), set it directly using the `myhome.set_cover_travel_time` action in **Developer Tools → Actions**.

You rarely need a handheld stopwatch: the integration times **every** run of a timed cover, calibration or not, and exposes the result as plain entity attributes — no card required.

1. Open the cover in Home Assistant (or use its wall switch) and press **Close**.
2. Press **Stop** (entity or wall switch) the moment the shutter reaches the bottom end stop.
3. Go to **Developer Tools → States**, filter on the cover entity: `last_run_seconds` is the motor-start-to-stop time of the run you just made and `last_run_direction` says `close`. The same attributes are listed under **Attributes** in the cover's more-info dialog.
4. Repeat with **Open** for the up time, then pass both numbers to the action (or put the attributes and a **Save** button on your dashboard with [Lovelace Recipe 6](lovelace_recipes.md#recipe-6-shutter-travel-time-workbench-stock-cards-only)):

```yaml
action: myhome.set_cover_travel_time
target:
  entity_id: cover.living_room_shutter
data:
  travel_time_down: 22.5
  travel_time_up: 24.0
  min_motor_pulse: 0.4
```

When setting travel times, the result is stored like a measured calibration, with `calibration_source: manual`, and overwrites whatever a previous calibration attempt may have saved (also visible under `cover_travel_times` in the integration's diagnostics download). When only `min_motor_pulse` is set, existing travel times, source, and calibration timestamps remain untouched. When the numbers you pass were measured on an identical shutter, add `copied_from: cover.<other_shutter>` to record where they came from; `calibration_source` then reads `copied` and the entity is exposed as a `copied_from` attribute.

To forget the measured or manual times and return to the `travel_time` from `myhome.yaml` (or the 25 s default when none is configured):
```yaml
action: myhome.reset_cover_travel_time
target:
  entity_id: cover.living_room_shutter
```

---

## 🪟 Venetian Blinds & Slat Tilt Positioning (Timed Slat Inching)

For Venetian blinds, motorized louvres, and external venetian blinds (EVBs/BSO) with adjustable slat tilt angles, the integration provides timed slat travel (inching):

* **Supported Features**: `SET_TILT_POSITION`, `OPEN_TILT` (100%), `CLOSE_TILT` (0%), and `STOP_TILT`.
* **Device Class**: Sets the entity device class to `blind` (`CoverDeviceClass.BLIND`).
* **Attributes**: Exposes `current_cover_tilt_position` (0–100%), `slat_tilt: true`, and `slat_time: <seconds>`.

### Physical Architecture & Slat Travel Time

Physical BTicino / Legrand MyHOME Venetian blind actuators (such as the F411U2 configured in Venetian mode) control slat tilt angle mechanically through brief motor pulses: when the motor runs, the slats first rotate through their full angular range (typically 1.5–2.5 seconds) before linear curtain lifting or lowering commences.

The integration models this behavior with timed travel:
* When a tilt command is issued, the shutter motor runs in the required direction for a calculated duration:
  $$\text{duration} = \frac{|\text{target\_tilt} - \text{current\_tilt}|}{100} \times \text{slat\_time}$$
* The pulse is timed from the **motor start**, not from the frame write: from the direction status the gateway relays (`*2*1*<WHERE>##` / `*2*2*<WHERE>##`), or, when the gateway relays none, from the write plus the measured 0.55 s motor-start delay (see [Runtime behaviour → Timed covers](runtime_behaviour.md)). Timed from the write, a pulse shorter than about half a second would end before the motor started. Nothing is counted while the frame still waits in the send queue.
* When the target duration elapses, an automatic stop command (`*2*0*<WHERE>##`) halts the motor. The angle is settled when that stop is **written**, not when it was due: the send queue is first-in first-out, so behind other frames (several blinds tilted at once, a busy gateway) the stop leaves late and the slats turn on until then. The angle follows the real motor time at one full rotation per `slat_time`, also past the target, up to 0 % / 100 %. Motor time past a full rotation moves the curtain, and a timed cover's position estimate moves by that time over its curtain travel time (`travel_time - slat_time`; a position-reporting cover reports its own level).
* A new tilt target while the previous pulse's stop still waits in the queue waits for that stop to be written, so it starts from the real angle; the new direction frame could not leave before that stop anyway. Tilt requests run one at a time, and a newer target replaces one still waiting, so a dragged slider sends only where it ended.
* A new target in the **same direction** while the pulse still runs moves the pulse's stop and sends nothing; only a change of direction sends a new direction frame.
* Like any command, a pulse opens an echo window: the stop status the gateway relays right after our direction frame is ignored, so it cannot cancel the pulse's stop and leave the motor running.
* Steps shorter than the cover's `min_motor_pulse` (default **0.4 s**, or 20 % at `slat_time: 2.0`) are skipped: the motor would barely answer while the angle was recorded as changed. This floor has not been measured on a Venetian actuator yet.
* A tilt command while the curtain itself is running is refused (*"… is moving; stop it before tilting the slats"*). The run turns the slats anyway, and a pulse would leave the curtain's travel estimate behind. Opening, closing or setting the position during a pulse ends the pulse at the angle it reached; the new command takes the motor over, and the pulse's own stop is dropped. Setting the position the blind is already at, while a pulse or a run is going, stops the motor there.
* During a curtain run the slats turn first at one full rotation per `slat_time` (towards 100 % when opening, towards 0 % when closing), and only the remaining motor time moves the curtain estimate over `travel_time - slat_time`. A stop status with no run behind it (such as the relay of a pulse's own stop) leaves the angle alone, so slats tilted open on a lowered blind stay open.

### Configuration

Slat tilt and travel duration can be declared in `/config/myhome.yaml`:

```yaml
cover:
  living_room_venetian:
    where: '31'
    name: Living Room Venetian Blind
    slat_tilt: true
    slat_time: 2.0
```

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `slat_tilt` | boolean | `false` | Enables Venetian blind slat tilt controls and sets device class to `blind`. |
| `slat_time` | float | `2.0` | Full slat rotation travel time in seconds (allowed range: `0.5`–`10.0` s). A value set with `myhome.set_cover_travel_time` is stored and wins over this one after a restart, until `myhome.reset_cover_travel_time`. |

Higher tilt is assumed to be *open* (an opening pulse raises the angle). This, and the slat time of real actuators, still awaits a keypad / app capture of a Venetian actuator (#492).

### Protocol Note: Dimension 11 is Shutter Level

In OpenWebNet WHO 2, **Dimension 11** (`*#2*<WHERE>*#11#PRIORITY*LEVEL##`) represents an absolute **Go to level / Shutter position** command, **not** slat tilt angle. Gateway firmwares (MH200N, MyHomeServer1) reject query frames (`*#2*<WHERE>*11##`) with a NACK because Dimension 11 is write-only.

When an actuator or external controller broadcasts a Dimension 11 event (such as `*#2*31*#11#001#1*40##` indicating 40% level), the integration ignores it: the motor needs time to get there and a keypad can stop it midway, so the position only follows the actuator's own status reports (Dimension 10 / status frames).

### Travel Time Calibration & Slat Rotation

End-to-end travel time (`travel_time_down` / `travel_time_up`) includes one full slat rotation (`slat_time`) at the start of the run:
* On a slat blind, linear curtain travel is estimated over `travel_time_down - slat_time` and `travel_time_up - slat_time` after the slats finish rotating.
* Mid-tilt stops do not corrupt or reset linear curtain position estimation.
* Tilt commands are safely rejected if the cover is actively running automated travel-time calibration.

---

## 🏠 General, Area and Group Covers

A cover declared in `/config/myhome.yaml` on a **general** (`where: '0'`), **area** (`where: '1'`, `'00'`, `'100'`) or **group** (`where: '#3'`) address is one button for many shutters: *open*, *close* and *stop* send a single frame to that address, like the general button on a keypad.

Its state comes from the shutters it moves, not from the bus. At the end of a run every actuator reports its own stop (`*2*0*11##`, `*2*0*12##`, …) and none arrives for the general or area address (WHO_2 specification §3.0.1). So the cover shows *opening* / *closing* while any of its shutters is moving, *closed* when all are closed, and the average of their positions:

| Address | Shutters it follows |
| :--- | :--- |
| General `0` | every point-to-point cover of the gateway |
| Area `1`…`9`, `00`, `100` | the covers of that area on the same bus: area `1` is `11`…`19` and `0110`…`0115` |
| Group `#1`…`#255` | the covers listed under `members:`; group membership is programmed in the actuators and cannot be read from the bus |

```yaml
cover:
  all_shutters:
    where: '1'          # area 1: follows covers 11-19 on its own
    name: All shutters
  bedrooms:
    where: '#3'
    name: Bedrooms
    members: ['11', '13']
```

**Behind an F422 interface** (`bus_interface: '02'`, logical `#4#` addressing), physical actuators reside on an isolated secondary SCS bus segment (e.g. `11#4#02` … `22#4#02`).

### 🏛️ The BTicino Way & Real-World Plant Discovery

In large MyHOME installations, F422 interfaces physically segment the SCS bus (e.g., separating ground floor from upper floors or main house from outbuildings/curtain lines). How commands are routed across an F422 is fundamental to reliability:

#### 1. Why Naive Fan-Out Overwhelms F422 Hardware Buffers
In real-world plant operation with an MH200 gateway and F422 interface, an automation triggering 10 individual shutters at sunset (`action: cover.close_cover` targeting 10 individual entities) encountered reproducible dropped frames:
- Home Assistant dispatched 10 concurrent requests via `asyncio.gather()`.
- When fanning out 10 individual point-to-point OpenWebNet commands (`*2*2*14#4#02##`, `*2*2*19#4#02##`, `*2*2*18#4#02##`, …), even with the gateway's worker queue pacing (e.g., 0.15 s per frame), the burst overwhelmed the physical F422 interface's internal FIFO buffer and secondary SCS bus arbitration.
- By the 6th or 7th consecutive command, the F422 buffer overflowed. The gateway returned NACK (`*#*0##`), causing OWNd to cancel delivery and abort motion on the un-acknowledged curtain (e.g. `13#4#02`, "Oost 1"). The shutter remained stuck open while the rest closed.
- Compounding this, a common legacy automation pattern of placing a `delay: 45s` followed by an explicit `cover.stop_cover` sent `*2*0*13#4#02##` 45 seconds later when the bus was quiet again. The actuator acknowledged the stop frame, permanently cementing the stuck shutter in its open position and masking the failure.

#### 2. Native Broadcast: The BTicino Protocol Architecture
BTicino physical keypads and scenario units (such as `LN4660M2` or CEN/CEN+ controls programmed with `A=GEN` or Area `A=1..9`) never send individual point commands. They emit **native OpenWebNet broadcasts**:
- **Main Bus General**: `*2*WHAT*0##`
- **Secondary Bus General via F422**: `*2*WHAT*0#4#<interface>##` (e.g., `*2*2*0#4#02##` for General Down on interface 02, `*2*1*0#4#02##` for General Up, `*2*0*0#4#02##` for General Stop)
- **Secondary Bus Area via F422**: `*2*WHAT*<area>#4#<interface>##` (e.g., `*2*2*1#4#02##`)

The gateway routes the single broadcast frame through the F422 interface onto the secondary bus once. Every actuator on that bus reads the frame off the physical wire simultaneously. All relays energize in unison with **zero queue latency, zero interface congestion, and 100% mechanical synchronization**.

### ⚙️ How the MyHOME Integration Handles Scope Covers

The MyHOME integration implements a dual-layer architecture adhering to both Home Assistant standards and BTicino protocol engineering:

1. **Native Broadcast for General Scope Covers (`where: '0'`)**:
   When `open_cover`, `close_cover`, or `stop_cover` is called on a General cover behind an interface (`where: '0'`, `bus_interface: '02'`), the integration sends the native OpenWebNet broadcast frame directly (`*2*WHAT*0#4#<bus>##`).
   - Actuators on the interface bus respond simultaneously without dropping frames.
   - When the gateway echoes `*2*WHAT*0#4#<bus>##`, the integration scopes the incoming frame strictly to entities on that interface (`interface == "02"`), preserving total bus isolation.
   - When individual actuators reach their end stops and report status frames (`*2*0*11#4#02##`, etc.), Home Assistant tracks each entity and aggregates the General cover's position automatically.

2. **Paced Member Fan-Out (`PACED_FANOUT_DELAY = 0.3s`) for Percentage Positioning**:
   OpenWebNet has no broadcast protocol for percentage positioning (Dimension 10 positioning `*#2*WHERE*#10*LEVEL##` is strictly point-to-point; there is no broadcast level command).
   When `set_cover_position` is called on a scope/group cover, or when non-general scopes must address individual actuators, the integration staggers member commands with a safety interval of **0.3 s (300 ms)**.
   This gives the F422 hardware FIFO buffer adequate time to serialize frames onto the secondary bus, completely eliminating frame loss during multi-cover repositioning.

3. **Keypad Broadcast Reflection**:
   A general or area command from a physical wall switch or scenario unit also moves the individual covers in Home Assistant. A group or area cover whose shutters are not known yet ends its run after its own `travel_time`, so it never stays stuck on *opening* ([#433](https://github.com/OpenWebNet-HA/MyHOME/issues/433)).

### 💡 Automation Best Practices: The Home Assistant & BTicino Way

To ensure maximum reliability and preserve bus health:

#### Recommended: Target the General Scope Cover
Declare a General scope cover in `/config/myhome.yaml` for each bus interface, and target that single entity in your automations:

```yaml
# /config/myhome.yaml
00:03:50:XX:XX:XX:
  cover:
    all_shutters_oost:
      where: "0"
      bus_interface: "02"
      name: "All Shutters East"
```

In your automation:
```yaml
alias: Close Windows at Sunset
triggers:
  - trigger: sun
    event: sunset
    offset: "00:30:00"
actions:
  - action: cover.close_cover
    target:
      entity_id: cover.all_shutters_oost
```

#### Retire the Legacy `delay: 45s` + `stop_cover` Anti-Pattern
In legacy configurations, users often placed a `delay: 45s` followed by `cover.stop_cover` to ensure motors stopped. **This pattern is unnecessary and counterproductive**:
- BTicino actuators (F411, F401, LN4661M2) incorporate hardware limit switches and configurable travel timers (e.g. configurator `M` or MyHOME_Suite cutoff).
- The MyHOME integration automatically calculates direction-aware travel times (`travel_time_down` / `travel_time_up`) and handles stop detection.
- Sending a delayed `cover.stop_cover` floods the bus with redundant frames and can accidentally cement a stalled or out-of-sync shutter. Let the hardware and integration manage motion termination naturally.

### 🪟 Slat Tilt on Scope Covers

**Slat tilt on a scope cover** (with `slat_tilt: true`): on the main bus one scope pulse turns the slats of every member with `slat_tilt`. The members follow that pulse (its direction and stop frames turn their slats and do not count as a curtain run), and the scope cover times and settles it for all of them. A scope tilt is refused while one of its covers is running. Behind an F422 each blind gets its own pulse, **one after the other**: queued together, every stop would wait behind the other blinds' direction frames and the slats would turn on. The last blind therefore moves a few seconds after the first.

---

## 🚪 Impulse Covers: Motorized Gates & Garage Doors (`WHO = 1`)

In BTicino MyHOME installations, motorized garage doors and sliding/swing entrance gates are controlled via **monostable impulse relays** on `WHO = 1` (such as `F411/2` or `F411U2`).

Because monostable relays only send a momentary pulse (`open` / `stop` / `close` / `stop`) with no inherent directional knowledge on the bus, Home Assistant implements the specialized **`MyHOMEImpulseCover`** entity equipped with the **`AccessController`** safety architecture.

### 🛡️ Safety Architecture & Threat Model

> [!CAUTION]
> **HOME ASSISTANT IS A SUPERVISORY AUTOMATION SYSTEM, NOT A CERTIFIED SAFETY SYSTEM**
> Primary entrapment and crush protection (e.g. European Standard **EN 12453 / EN 12445** or North American **UL 325**) **must be provided by the motorized gate or garage door hardware itself**: certified infrared photocells, safety contact edges, and mechanical force limiters built into the motor control board.
> Home Assistant's `AccessController` is designed exclusively to prevent Home Assistant from *causing* an unintended, accidental, or unattended movement.

#### Key Principles of the Human-in-the-Loop Policy:

1. **Zero Direct Movement on Service Calls**:
   Calls to `cover.open_cover`, `close_cover`, or `stop_cover` (whether from dashboards, mobile widgets, voice assistants, or automations) **never pulse the relay directly**. Instead, they create an authenticated approval request for an authorized person.
2. **Cryptographic Single-Use Nonce & User Binding**:
   Each approval request generates a 128-bit CSPRNG token (`secrets.token_urlsafe(16)`), tightly bound to the requesting `user_id`, target entity, and physical direction. Replayed, stale, or forged approval actions are discarded.
3. **Biometric Phone Unlock Requirement**:
   Actionable push notifications to the Companion App enforce `authenticationRequired: true` (iOS FaceID/TouchID, Android biometrics/screen lock). The phone must be actively unlocked by the authorized approver.
4. **Fail-Closed Sensor Direction Checks**:
   A pulse is classified as a pure **OPEN** *only* when the ground-truth state sensor (`closed_sensor_entity_id`) proves the door is closed. In all other states, the pulse is classified as **MAY_CLOSE**, requiring:
   - Verified active safety devices within `safety_check_days`.
   - The user to be on site (`person` entity reports `home`) or visual confirmation via a camera snapshot.
   - Any external close-block switch to report `off`.
   - Any missing, unavailable, or non-binary sensor state immediately fails closed.
5. **Audible / Visual Pre-Warning & Watchdog**:
   Before a close pulse, an optional pre-warning flasher (`prewarn_light`) triggers for `prewarn_seconds`. If a physical wall button is pressed during this countdown, the movement is aborted. After the pulse, an anti-stuck watchdog monitors motion: if the expected state is not reached within `travel_time + watchdog_margin`, a latching fault is asserted with **zero automatic retries**.

### ⚠️ Strict Distinction: Covers vs. Locks

| Physical Device | Required Entity Platform | Why |
| :--- | :--- | :--- |
| **Motorized Gates & Garage Doors** | `cover` (`type: impulse_relay`) | Heavy kinetic machinery with kinetic entrapment/crush risk. Must use `AccessController` with sensor validation and pre-warning. **Never configure a motorized gate or garage as a `lock`**. |
| **Pedestrian Door Strikes** | `lock` (`platform: lock`) | Low-mass momentary electric door buzzers (elettroserrature) that release a pedestrian latch for 1–3 seconds. |

---

## 🔄 Legacy YAML Note

> [!NOTE]
> If you are upgrading from legacy v0.9 installations and still have manual `cover:` blocks in `/config/myhome.yaml`, please refer to the [v0.9.4 Legacy Cover Documentation](../../0.9.4/configuration/covers/) or the [Legacy YAML Migration Guide](../migration/legacy-yaml.md). In v2, all covers are managed dynamically via Home Assistant's native registry.

