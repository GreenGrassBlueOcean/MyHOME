# Synthetic Trace: WHO 3 Load Control Measurements & Central Unit Status

Synthetic trace fixture capturing WHO 3 (Load Control) central unit measurement telemetry and load shedding states derived from firmware register disassembly.

## Provenance: Synthetic from Gateway Disassembly

> [!NOTE]
> **Why this trace is synthetic**:
> In physical smart home installations, collecting live wire traffic for central unit load shedding requires intentionally overloading home electrical circuits to force breaker/relay load shedding, which disrupts active domestic appliances and risks equipment damage.
>
> Furthermore, the central unit (`WHERE = 10`) requires gateways hosting the Legrand `bt_energia` daemon (such as the MH202 or F459), which are less prevalent than modern MyHomeServer1 devices.
>
> This trace is **fully synthetic**, deterministically synthesized from static disassembly and runtime analysis of:
> 1. Legrand `bt_energia` gateway daemon (MH202 image `010024` and F459 `020105`).
> 2. Central Unit internal memory register address mappings:
>    - **Dimension 1**: Instantaneous Power ($\text{W}$) &rarr; internal register `$03AA001613`
>    - **Dimension 2**: Voltage ($\text{V}$) &rarr; internal register `$03AA001612`
>    - **Dimension 3**: Current ($\text{A}$) &rarr; internal 2-register pair `$03AA001610` & `$03AA001611`
>    - **Dimension 4**: Power Factor ($\cos \phi$) &rarr; internal 4-register block `$03AA001606` .. `$03AA001609`
>    - **Dimension 0**: Aggregate sequential register read (1 &rarr; 2 &rarr; 3 &rarr; 4)
> 3. `own-firmware-oracle` test harness suite `energy-ts10.cases` (SHA-256: `ae576deb4f97c6af81e22c221f24dadb99f4813610e99e19ed96fc1d137896ad`).

## Plant Profile

| Property | Value |
|---|---|
| Gateway Model | MH202 (firmware 1.0.24, MAC prefix `00:03:50`, WHO 13 code `14`) |
| Subsystem | WHO 3 (Load Control) |
| Target Devices | Central Unit (`WHERE = 10`), Load Shed Actuators (`WHERE = 1`) |

## Captured Sequence (9 Frames)

1. **Aggregate Central Unit Telemetry (Dimension 0)**:
   - `*#3*10*0*230*12*2760*1520##`: Dimension 0 aggregate frame reporting:
     - `power = 230` $\text{W}$
     - `voltage = 12` $\text{V}$
     - `current = 2760.0` $\text{A}$
     - `power_factor = 1520.0`
2. **Individual Dimension Telemetry (Dimensions 1–4)**:
   - `*#3*10*1*230##`: Instantaneous active power ($230\text{ W}$).
   - `*#3*10*2*230##`: Voltage ($230\text{ V}$).
   - `*#3*10*3*120##`: Current ($120.0\text{ A}$).
   - `*#3*10*4*980##`: Power factor ($980.0$).
3. **Load Shedding Execution Lifecycle**:
   - `*3*1*10##`: Central unit activates load control monitoring.
   - `*3*2*1##`: Load node 1 shed / disconnected due to power threshold excursion.
   - `*3*1*1##`: Load node 1 reconnected when power normalizes.
   - `*3*0*10##`: Central unit deactivates load control monitoring.

## Replay Verification

Replayed by `tests/test_who3_load_trace.py`, verifying that all measurements and load control states decode cleanly through OWNd and the MyHOME dispatcher with 0 device health faults.
