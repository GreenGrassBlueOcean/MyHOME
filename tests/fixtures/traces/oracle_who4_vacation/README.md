# Synthetic Trace: WHO 4 Multi-Day Vacation Countdown & Expiry Cycle

Synthetic trace fixture locking the complete multi-day vacation countdown and automatic expiration lifecycle for BTicino 3550 Central Units under WHO 4.

## Provenance: Synthetic from Firmware Disassembly

> [!NOTE]
> **Why this trace is synthetic**:
> Capturing a full 5-day vacation countdown from a physical 3550 central unit requires leaving home automation test harnesses attached across multiple calendar days past consecutive midnights, which is time-prohibitive.
>
> This trace is **fully synthetic**, deterministically synthesized from static disassembly of:
> 1. Legrand gateway OpenWebNet daemon `bt_termo` (`scs2open` routine at `0x0000EC74` & `0x0000ECF8`, expiration routine at `0x0000D2A8`).
> 2. BTicino 3550 99-zone Central Unit firmware (`3550_030020.mot`, Mitsubishi M16C architecture, midnight counter decrement at `0x0EF881`).

## Plant Profile

| Property | Value |
|---|---|
| Gateway Model | F454 (firmware 2.0.51, MAC prefix `00:03:50`) |
| Central Unit | 3550 99-zone Central Unit (`WHERE = #0`) |
| Protocol Subsystem | WHO 4 (Thermoregulation) |

## Captured Sequence (16 Frames)

1. **Initial Baseline State**:
   - `*#4*0*12*0210*3##`: Zone 0 operating state (heating mode 3, setpoint 21.0 °C).
   - `*4*1*0##`: Plant season heating.
   - `*4*1101*#0##`: Active weekly program 1 on Central Unit #0.
   - `*#4*0*13*01##`: Subzone distribution active.
2. **Vacation Activation (5 Days, Return to Program 2)**:
   - `*4*13005#3102*#0##`: Vacation command write with return program 2.
   - `*4*30*#0##`: Central unit status flag update.
   - `*#4*0*20*00*00*00*00*00*00##`: Vacation timer bounds.
   - `*4*13005*#0##`: Bare active vacation telemetry emitted by gateway (without `#P` suffix).
3. **Daily Midnight Decrements**:
   - `*4*13004*#0##`: Day 1 midnight rollover (`00:00:00`) decrements remaining days to 4.
   - `*4*13003*#0##`: Day 2 midnight rollover decrements remaining days to 3.
   - `*4*13002*#0##`: Day 3 midnight rollover decrements remaining days to 2.
   - `*4*13001*#0##`: Day 4 midnight rollover decrements remaining days to 1.
4. **Vacation Expiration & Program Restoration**:
   - `*4*1102*#0##`: Expiration frame clears vacation and restores weekly program 2.
   - `*#4*0*13*01##`: Subzone distribution re-asserted.

## Replay Verification

Replayed by `tests/test_who4_vacation_trace.py` against `climate.climate_zone_0`, verifying clean state transitions and 0 device health faults.
