# Synthetic Trace: Stop&Go Automatic Reset Breakers (F16EB) under WHO 18

Synthetic trace fixture capturing the complete operation, protection trip, differential testing, and automatic reclosing sequence of BTicino Stop&Go automatic reset circuit breakers (model F16EB) under WHO 18.

## Provenance: Synthetic from Firmware Disassembly & Reference Client

> [!NOTE]
> **Why this trace is synthetic**:
> Collecting live wire captures from physical Stop&Go installations requires repeatedly tripping mains residual current breakers, inducing physical earth leakage differential faults, and forcibly power-cycling domestic breaker panels. Performing these operations on live consumer units is hazardous to electrical equipment, interrupts household safety protection, and cannot be scheduled arbitrarily.
>
> This trace is **fully synthetic**, deterministically synthesized from:
> 1. Legrand/BTicino Touch Screen 10" client reference stack (`libqtdevices` tag `TS10_1_0_23`, `energy_device.cpp`).
> 2. `own-firmware-oracle` test harness suite `energy-ts10.cases` (SHA-256: `ae576deb4f97c6af81e22c221f24dadb99f4813610e99e19ed96fc1d137896ad`), which proved byte-identical physical SCS bus bytecode generation (`$06D101023210...`) across MH202, MyHomeServer1, F454, and MH200N.

## Plant Profile

| Property | Value |
|---|---|
| Gateway Model | MH202 (firmware 1.0.24, MAC prefix `00:03:50`, WHO 13 code `14`) |
| Subsystem | WHO 18 (Energy Management / Stop&Go) |
| Target Devices | Stop&Go Breaker Line 1 (`WHERE = 11`), Line 2 (`WHERE = 12`) |

## Captured Sequence (11 Frames)

1. **Initial Closed State & Configuration**:
   - `*18*22*11##`: Breaker on Line 1 in closed / normal conductive state.
   - `*#18*11*212*10##`: Self-test periodic frequency configured for 10 days.
2. **Breaker Trip & Fault Tracking**:
   - `*18*21*11##`: Breaker open event (tripped due to residual current detection).
   - `*18*28*11##`: Earth leakage tracking activated by breaker electronics.
3. **Differential Insulation Self-Tests**:
   - `*18*23*11##`: Differential test positive (insulation verified, safe to reclose).
   - `*18*24*11##`: Differential test negative (insulation compromised / persistent fault).
4. **Auto-Reset Reclosing**:
   - `*18*26*11##`: Auto-reset mechanism engaged.
   - `*18*22*11##`: Motorized breaker automatically recloses Line 1.
   - `*18*29*11##`: Earth leakage tracking deactivated.
5. **Internal Status Mask & Multi-Line**:
   - `*#18*11*250*0001##`: Breaker diagnostic status mask read (DIMENSION 250).
   - `*18*22*12##`: Breaker on Line 2 in closed / normal state.

## Replay Verification

Replayed by `tests/test_who18_stop_and_go_trace.py`, verifying that all Stop&Go frames dispatch cleanly with 0 device health faults.
