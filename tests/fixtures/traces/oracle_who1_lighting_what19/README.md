# Synthetic Trace: Lighting WHAT 19 Anomaly & Autodiagnostic Bitmask Correlation

Synthetic trace fixture capturing the lighting anomaly state (`WHAT = 19`), actuator diagnostic bitmask correlation, disconnected dimmer no-load condition, and subsequent fault recovery.

## Provenance: Synthetic from Firmware Disassembly & Oracle Verification

> [!NOTE]
> **Why this trace is synthetic**:
> Generating physical lighting anomaly (`WHAT = 19`) frames on real installations requires creating hardware fault conditions: physically disconnecting high-voltage wiring on active dimmer channels (e.g. F414 / F411 actuators), tripping output stages, or inducing open-circuit faults. Performing these physical maneuvers on live residential installations is hazardous to human operators and risks damaging sensitive dimmer modules.
>
> This trace is **fully synthetic**, deterministically synthesized from:
> 1. Legrand OpenWebNet lighting daemon `bt_luci` (`0x16ab4` SCS bus status byte `'E'` assigned to decimal `19`, and `0x13dc8` command jump table NACK).
> 2. Diagnostic unpacking library `libdiag.so.0.0` (`0x132e4`, `"D2S89"` routine unpacking 3-byte payload `FBFFF7` into 24-character bitmask `111110111111111111110111`).
> 3. Fleet-wide oracle emulation in `own-firmware-oracle#43` across 10 gateway firmwares (MH200N, MyHomeServer1, F453AV, F459, F460, F461, F454, H4684).

## Plant Profile

| Property | Value |
|---|---|
| Gateway Model | MH200N (firmware 1.1.8, MAC prefix `00:03:50`, WHO 13 code `13`) |
| Subsystems | WHO 1 (Lighting) & WHO 1001 (Autodiagnostics) |
| Target Devices | Dimmer Actuator 74 (`WHERE = 74`), Dimmer Channel 92 (`WHERE = 92`) |

## Captured Sequence (7 Frames)

1. **Baseline Illumination**:
   - `*1*1*74##`: Normal ON state for actuator 74 (`is_on = True`).
2. **Actuator Anomaly State (`WHAT = 19`)**:
   - `*1*19*74##`: Actuator 74 reports anomaly / fault state (`what = 19`). `OWNd` models `is_on = False`, `is_fault = True`.
3. **Diagnostic Bitmask Correlation (Active Hardware Fault)**:
   - `*#1001*74*11*111110111111111111110111##`: WHO 1001 dimension 11 autodiagnostic bitmask with bits 6 and 21 cleared (`FBFFF7`), confirming active hardware fault.
4. **Disconnected Channel / No-Load Condition**:
   - `*1*19*92##`: Disconnected dimmer channel 92 reports WHAT 19.
   - `*#1001*92*11*111111111111111111111111##`: All bits set (`1`). With no fault bits cleared, the light entity resolves safely to `LightState.OFF` rather than `FAULT`, eliminating phantom ON states.
5. **Fault Recovery & State Restoration**:
   - `*1*1*74##`: Physical fault cleared / load reconnected, light commanded ON. Entity safely recovers from fault and returns to `LightState.ON`.
   - `*1*0*74##`: Subsequent normal OFF command cleanly transitions light to `LightState.OFF`.

## Replay Verification

Replayed by `tests/test_who1_lighting_what19_trace.py`, verifying that the MyHOME light entities resolve no-load conditions to `OFF`, detect active hardware faults, recover on reconnection, and register 0 device health faults.
