# #466 MyHomeServer1 sweep with a controlled setpoint experiment

Verbatim bus trace contributed by **@gdluck** on [#466](https://github.com/OpenWebNet-HA/MyHOME/issues/466)
(bus card export, HA 2026.9.4, integration 2.0.0b13, OWNd 2.0.0b8, gateway firmware 3.87.13). Never edit a frame.

| File | Type | Description |
|---|---|---|
| `myhome_sweep_MyHomeServer1_all_2026-09-29T18-20-22.json` | Sweep export (200 frames, buffer truncated) | Lighting status sweep, zone-state sweep of 32 zones (35-70), then setpoint writes on zones 60, 68 and 55. |

## What it shows

- **Setpoint write echo**: `*#4*Z*#14*T*1##` is answered by `*#4*Z*12*T*3##`, `*4*1*Z##` and the temperature; no dimension 7 or 14 echo. An unchanged repeat write gets only the temperature back.
- **Zone 55 (measured 24.6 C)**, setpoint above the room: actuator `*#4*55#1*20*1##`, ~2.3 s later pump call `*4*4001#55*0#3##` + `*#4*0#3*20*1##`.
  Setpoint below: pump stops (`*4*4002#55*0#3##`, `*#4*0#3*20*0##`, `*4*4002*55##`) about 2 s **before** the valve closes (`*#4*55#1*20*0##`).
- `*#1*66*4*100*4##`: unsolicited WHO 1 dimension 4 report on point 66 (undocumented for WHO 1).
- Dimension 12 carries mode `3` on an ordinary manual heating write.
