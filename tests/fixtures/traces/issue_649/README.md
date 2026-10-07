# #649 / MyHomeServer1 Physical Plant Trace (Thermostat Zone 60, Energy Meter 51, Light 43)

Verbatim physical plant bus trace captured from an authentic BTicino MyHomeServer1 gateway by **@gdluck** on [#649 (comment 6046117228)](https://github.com/OpenWebNet-HA/MyHOME/pull/649#issuecomment-6046117228).
Captured live on 2026-10-07 between 20:06 and 20:13 UTC. In MyHOME, physical traces are immutable facts: never edit a frame.

## Hardware Profile

- **Gateway Model**: BTicino MyHomeServer1 (Server MyHOME_Up)
- **Firmware Version**: 3.87.13
- **IP Address**: 192.168.0.218 (port 20000)
- **WHO 13 Identification**: Code `130` (`*#130**1*1*0*3*1*8##`)
- **Plant Devices Under Test**:
  - **Thermostat Zone 60**: Heating zone with no central unit (`#0` absent). Normal operating temperature 23.0 °C.
  - **Energy Meter 51**: BTicino F520 single-phase electricity meter.
  - **Lighting Actuator 43**: Standard relay actuator (non-dimmer).
- **Environment**:
  - Home Assistant: 2026.9.4
  - Integration: 2.0.0b15
  - OWNd Protocol Engine: 2.0.0b10
- **Test Setup**:
  - 37 frames transmitted on COMMAND session 5–12 s apart.
  - 107 frames captured on MONITOR session (`live_test_monitor_2026-10-07.log`).

## Files in this Fixture

| File | Format | Description |
|---|---|---|
| `live_test_monitor_2026-10-07.log` | Raw Monitor Log (107 frames) | Verbatim monitor log lines (`<epoch_timestamp> OWN <frame>`) captured from the physical gateway session. |
| `myhome_trace_MyHomeServer1_live_2026-10-07.json` | JSON Trace Archive (107 frames) | Standard structured trace archive with ISO timestamps, frame metadata, parsed OWNd message types, and human-readable descriptions. |

## Live Plant vs. Firmware Emulator Replay

Reply column: `ACK` = `*#*1##`, `NACK` = `*#*0##`.
"Report" = what the monitor session showed within 3 seconds.
"Emulator" = the MHS1 `bt_termo` / `bt_supervisione` / `bt_luci` replay of the same frame on test addresses under QEMU.

| Frame sent | Live reply | Live report on the monitor | Emulator | Match |
|---|---|---|---|---|
| `*#4*60##` | ACK, 5 frames | dim 0 (`0235`), dim 12 (`0230*3`), `*4*1*60##`, dim 14 (`0230*3`), dim 13 (`00`) | NACK, **no bus frame** | **differs** (see 1 below) |
| `*#4*60*11##` | NACK | – | request sent, no device | = (no fan coil on 60) |
| `*#4*60*19##` | ACK `*#4*60*19*5*0##` | – | request sent | = |
| `*#4*60*20##` | ACK `*#4*60#1*20*0##` | – | request sent | = |
| `*#4*#60##` | NACK | – | not replayed | plant has no central unit |
| `*#4*60*15##`, `15#1` | NACK | – | request sent, no device | = (no slave probe) |
| `*#4*60*14##`, `13##` | ACK with value | – | request sent | = |
| `*#4*60*#14*0230*3##` | ACK | dim 12 `0230*3` + `*4*1*60##` (season **unchanged**) | ACK, `92 17 30 2C` | = |
| `*#4*60*#14*0230*2##` | ACK | `*4*0*60##` + dim 12 (season → conditioning) | ACK, `91 17 30 2C` | = |
| `*#4*60*#14*0230*1##` | ACK | `*4*1*60##` + dim 12 (season → heating), actuator `60#2*20*5` | ACK, `90 17 30 2C` | = |
| `*#4*60*#11*2##`, `#11*0` | ACK | nothing (no fan coil) | ACK | = |
| `*4*303*60##` | ACK | `*4*303*60##` + dim 12 | ACK, `93 17 30 0F` | = |
| `*4*311*60##` | **NACK** | – | NACK, nothing | = |
| `*4*311*#60##` | ACK | **nothing**, zone unchanged | ACK, `D1 00 03 02 C2 17 00 00` | = on acceptance (see 2 below) |
| `*4*102*60##` | ACK | `*4*102*60##` + dim 12 `0070*3` (antifreeze, 7.0 °C) | ACK | = |
| `*4*303*#60##` | ACK | nothing | ACK | = on acceptance (see 2 below) |
| `*4*311*#60##` (again) | ACK | nothing; `*#4*60##` 2 min later still antifreeze | ACK | see 2 below |
| `*#18*51*51##`, `54`, `53`, `113` | ACK | – | ACK / "silent" (waiting for the bus) | = |
| `*#18*51*#1200#1*255##` | ACK | – | ACK | = |
| `*#18*51*1200##` | **NACK** | – | NACK, nothing | = |
| `*18*510#9*51##`, `*#18*51*513#9##`, `*18*59#9*51##`, `*#18*51*516##` | ACK | – | ACK / silent | = |
| `*#1*43##`, `*#1*43*1##` | ACK `*1*0*43##` | – | request sent | = |
| `*1*11*43##` | ACK | `*1*1*43##` (light on; switched off by operator 6 s later) | ACK, `11 00 12 16` | = |
| `*#1*43*#2*0*0*5##` | ACK | `*1*1*43##` at +0.1 s, `*1*0*43##` at **+5.2 s** | ACK, `D1 11 01 42 06 …` | = (5-s timer ran) |
| `*#1*43*2##` | ACK `*#1*43*2*0*0*0##` | – | request sent | = |
| `*1*2*43##` | ACK | nothing (relay, not a dimmer) | ACK, `11 00 12 1D` | = |

## Empirical Findings & Architectural Consequences

### 1. `*#4*Z##` Is Answered Directly from Gateway Cache
When polling a bare zone status query `*#4*Z##`, the real MyHomeServer1 answers immediately within ~1 s with a deterministic 5-frame sequence:
1. `*#4*60*0*0235##` (Dimension 0: current temperature 23.5 °C)
2. `*#4*60*12*0230*3##` (Dimension 12: active setpoint 23.0 °C, generic mode 3)
3. `*4*1*60##` (Season frame: heating season)
4. `*#4*60*14*0230*3##` (Dimension 14: programmed setpoint 23.0 °C, generic mode 3)
5. `*#4*60*13*00##` (Dimension 13: local offset 0.0 °C)

The emulated `bt_termo` binary did not produce a bus frame for `*#4*Z##` because the simulated bus lacked cached device tables. On physical hardware, the gateway maintains the cached plant model and serves `*#4*Z##` without needing to wake the physical bus.

### 2. Central Unit `#Z` Commands Have No Effect Without a Central Unit
Commands using `#Z` targeting (`*4*311*#60##` and `*4*303*#60##`) are accepted with ACK by the gateway translator, but because this plant has no central unit (`#0`), the zone never receives or acts upon them. The zone remained in antifreeze mode (`102`) until a direct zone command (`*#4*60*#14*0230*1##`) was issued.
**Consequence**: On plants without a central unit, sending `#Z` addressing for AUTO modes is a no-op; plain zone commands (`303`, `102`, `#14`, `#11`) are required.

### 3. Setpoint Mode Digits: Digit 3 Preserves Season
- Writing setpoint with **mode digit 3** (`*#4*60*#14*0230*3##`) is ACKed and leaves the existing operating season completely untouched (`*4*1*60##` continues to report).
- Writing with **mode digit 2** (`*#4*60*#14*0230*2##`) flips the zone season to conditioning (`*4*0*60##`).
- Writing with **mode digit 1** (`*#4*60*#14*0230*1##`) flips the zone season to heating (`*4*1*60##`) and activates heating actuator `60#2*20*5`.
This proves that BTicino's client application writes digit 3 for setpoint adjustments specifically to avoid unintended seasonal flips.

### 4. WHO 1 Timers on Physical Actuators
- Variable timer command `*#1*43*#2*0*0*5##` turned relay 43 ON at +0.1 s, followed by an automatic OFF status report at +5.2 s, validating the hardware timing engine on physical relays.
- Dimension 2 query `*#1*43*2##` returns `*#1*43*2*0*0*0##` once expired.
