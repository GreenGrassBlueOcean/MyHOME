# #445 MyHomeServer1 & LN-4660M2 Centralized Shutter Traces

Authentic on-wire bus traces contributed by **@f18m** (Francesco Montorsi) on [#445](https://github.com/OpenWebNet-HA/MyHOME/issues/445) and [#466 (comment 5853591733)](https://github.com/OpenWebNet-HA/MyHOME/issues/466#issuecomment-5853591733).

## Hardware Profile

- **Gateway Model**: BTicino MyHomeServer1
- **Gateway Manufacturer**: BTicino S.p.A.
- **Connection**: TCP OpenWebNet (Port 20000)
- **Centralized Button Model**: BTicino LN-4660M2 (Livinglight centralized cover control button)
- **Actuators Tested**: 7 SCS cover actuators (`02`, `03`, `04`, `08`, `09`, `0010`, `0011`)
- **Environment**: Home Assistant 2026.9.3, MyHOME integration 2.0.0b13, OWNd 2.0.0b8

## Contributed Files

| File | Type | Frames | Description |
|---|---|---|---|
| `myhome_trace_MyHomeServer1_LN4660M2_centralized_up_then_stop_2026-09-26.json` | Bus Monitor Trace | 16 | LN-4660M2 centralized UP button pressed, followed by STOP button press, showing multi-actuator Dimension 10 position feedback and stop confirmations. |
| `myhome_trace_MyHomeServer1_LN4660M2_centralized_down_then_stop_2026-09-26.json` | Bus Monitor Trace | 26 | LN-4660M2 centralized DOWN button pressed, actuators reaching 0% / mid-travel, followed by STOP button press. |

## Empirical Protocol Discoveries

1. **Centralized General Cover Commands Send Advanced Automation Frames**:
   - Rather than simple point-to-point or basic commands (`*2*1*0##` / `*2*2*0##`), the physical LN-4660M2 centralized controller broadcasts multi-parameter Advanced Automation commands on General address `0`:
     - **Advanced UP (General)**: `*2*11#100#001#1*0##` (WHAT `11`: target 100%, step `001`, priority `1`, WHERE `0`)
     - **Advanced DOWN (General)**: `*2*12#100#001#1*0##` (WHAT `12`: target 100%, step `001`, priority `1`, WHERE `0`)
     - **Advanced STOP (General)**: `*2*10#001#1*0##` (WHAT `10`: step `001`, priority `1`, WHERE `0`)

2. **Telemetry Burst Following Centralized Stop / Limit**:
   - When a centralized movement is stopped or completes, each addressed actuator reports:
     1. Its current Dimension 10 position: `*#2*WHERE*10*10*POS*001*0##`
     2. Individual stop confirmation: `*2*0*WHERE##`

3. **4-Digit Addressing for Automation Actuators**:
   - Actuators on MyHomeServer1 plants can report addresses in 4-digit format (`0010`, `0011`), validating address normalization in the parser and router.
