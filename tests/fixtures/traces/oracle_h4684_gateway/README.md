# Synthetic Trace: BTicino H4684 and Legrand LGRH4684 Gateway Identification

Synthetic trace fixture capturing OpenWebNet WHO 13 (Gateway Management) and WHO 1013 (Gateway Diagnostic) device identification sequences for the BTicino H4684 / Legrand LGRH4684 3.5" Colour Touch Screen family.

## Provenance: Firmware Ground Truth from `bt_device` Reverse-Engineering

> [!NOTE]
> **Why this trace is synthetic**:
> Community plant captures from standalone H4684 / LGRH4684 installations operating as primary OpenWebNet IP gateways are scarce in the repository archives. Unofficial third-party documentation (such as legacy Nmap scripts and MHCatalogue.db extractions) previously recorded conflicting codes, conflating WHO 13 dimension 15 codes (`13`, `20`, `23`) with WHO 1013 dimension 1 diagnostic object model codes (`19`, `26`, `29`).
>
> This trace is **fully synthetic**, deterministically synthesized from:
> 1. **Firmware binary reverse engineering**:
>    Static disassembly of the `bt_device` binary from H4684 firmware 2.0.54 (`TiDisplayColorIP` build `0x02003194`, catalogued in `own-firmware-oracle` PR #26):
>    - Primary dispatch table entries:
>      - `*#1013**1*19*15*5*0##` &rarr; `H4684` / `L4684` (BTicino 3.5" Colour Touch Screen)
>      - `*#1013**1*26*15*5*0##` &rarr; `LGRH4684` (Legrand variant)
>    - WHO 13 Dimension 15 response:
>      - `*#13**15*13##` &rarr; `H4684` (matches official BTicino 2006 specification verbatim)
>      - `*#13**15*20##` &rarr; `LGRH4684` (Legrand brand identifier)
> 2. **`OWNd` Protocol Diagnostic Mapping (PR #96)**:
>    - `OWNGatewayDiagnosticEvent` and `OWNGatewayDiagnosticCommand` mapping codes `19` and `26`.
>    - Binding to `H4684Profile` with aliases `L4684`, `N4684`, `NT4684`, `LGRH4684`, `LGR4684`.
> 3. **`MyHOME` Gateway Identity Resolver**:
>    - `WHO1013_OBJECT_MODELS` mapping `"19": ("H4684", "L4684")` and `"26": ("LGRH4684",)`.
>    - Separate identifier spaces ensuring `resolve()` maps evidence without raising false-positive repair conflicts.

## Plant Profile

| Property | Value |
|---|---|
| Gateway Model | BTicino H4684 3.5" Colour Touch Screen (firmware 2.0.54, MAC prefix `00:03:50`) |
| Alternate Model | Legrand LGRH4684 3.5" Colour Touch Screen |
| Diagnostic Systems | WHO 13 (Gateway Management) & WHO 1013 (Gateway Diagnostic) |
| Resolved Profile | `H4684Profile` |

## Captured Sequence (8 Frames)

1. **H4684 Device Type Request**:
   - `*#13**15##`: Client requests gateway device type under WHO 13.
2. **H4684 Device Type Response**:
   - `*#13**15*13##`: Gateway reports device type code `13` (BTicino 2006 standard table).
3. **H4684 Firmware Version Request**:
   - `*#13**16##`: Client requests gateway firmware version under WHO 13.
4. **H4684 Firmware Version Response**:
   - `*#13**16*2*0*54##`: Gateway reports firmware version `2.0.54`.
5. **H4684 Diagnostic Object Model Request**:
   - `*#1013*0*1##`: Client queries diagnostic object model under WHO 1013.
6. **H4684 Diagnostic Object Model Response**:
   - `*#1013**1*19*15*5*0##`: Gateway reports object model `19` (H4684), `N_CONF` 15, `BRAND` 5, `LINE` 0.
7. **LGRH4684 Device Type Response**:
   - `*#13**15*20##`: Gateway reports device type code `20` (Legrand brand).
8. **LGRH4684 Diagnostic Object Model Response**:
   - `*#1013**1*26*15*5*0##`: Gateway reports object model `26` (LGRH4684), `N_CONF` 15, `BRAND` 5, `LINE` 0.

## Replay Verification

Replayed by `tests/test_h4684_gateway_trace.py`, verifying that both H4684 (`13`/`19`) and LGRH4684 (`20`/`26`) identify deterministically, bind to `H4684Profile`, and create 0 device health faults or identity conflicts.
