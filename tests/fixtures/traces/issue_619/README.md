# #619 F453AV Gateway Trace (BTicino F414 Dimmer with Load)

Verbatim bus trace contributed by **@nce2704** on [#619 (comment 5972740263)](https://github.com/OpenWebNet-HA/MyHOME/issues/619#issuecomment-5972740263). They are facts: never edit a frame.

## Hardware Profile

- **Gateway Model**: BTicino F453AV (Audio/Video Web Server & Gateway)
- **Firmware**: 1.0 (WHO 13 device code `12`)
- **Actuator Model**: BTicino F414 (Classic 1000 W modular DIN phase-cut dimmer, 60–1000 VA)
- **Actuator Tested**: WHERE `13` (connected to a 35 W halogen lamp)
- **Connection**: TCP OpenWebNet (Port 20000)

## Contributed Files

| File | Type | Description |
|---|---|---|
| `myhome_trace_F453AV_all_2026-10-04T08-28-13.json` | Bus Monitor Trace (23 frames) | Verification of physical F414 dimmer on WHERE `13` with 35 W load, cycling through discrete levels 2..7 (`*1*2*13##` through `*1*7*13##`) and switching OFF (`*1*0*13##`). |

## Sequence of Actions Recorded & Subsystems Verified

1. **Physical F414 Normal Operation With Load (WHO 1)**:
   - Initial OFF state: `*1*0*13##`.
   - Discrete brightness levels: Level 4 (`*1*4*13##`), Level 3 (`*1*3*13##`), Level 2 (`*1*2*13##`), ramp up through Levels 2, 3, 4, 5, 6, 7 (`*1*7*13##`).
   - Normal turn OFF: `*1*0*13##`.
   - Proves that when connected to a closed load circuit, the F414 operates with standard discrete levels 2..7 and discrete OFF `0`, without emitting `WHAT 19`. Unloaded channels emit `WHAT 19` (`*1*19*WHERE##`).

2. **Other Subsystem Traffic**:
   - Gateway identity heartbeat: `*#13**15*12##` (WHO 13 dimension 15 device code 12 = F453AV).
   - Additional lighting endpoints: WHERE `32`, `42`, `33`, `52`, `72` reporting ON/OFF transitions.
