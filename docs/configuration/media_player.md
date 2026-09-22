# Sound System / Media Player (`WHO = 16`)

This guide explains how to configure and automate the BTicino / Legrand **Diffusione Sonora** (Sound System) in Home Assistant using the MyHOME integration.

---

## 🎵 Subsystem Architecture

In MyHOME systems, multi-room audio is managed by dedicated hardware analog matrices and room amplifiers communicating over the SCS bus using **OpenWebNet WHO = 16**.

### Supported Hardware
- **Audio Matrix**: F441, F441M (4 audio input sources, up to 8 independent stereo room amplifier outputs)
- **Room Amplifiers**: 3484, 3484/1, 3487, F500
- **Audio Controls**: L/N/NT4684, 3529

> [!IMPORTANT]
> **Hardware-Only Analog Matrix**: The BTicino F441 / F441M is a purely analog matrix switcher. It does not contain an Ethernet port or digital audio decoder and cannot stream IP audio by itself. It routes line-level analog signals from physical source inputs (Source 1 to Source 4) to room amplifier outputs (Zone 1 to Zone 9).

---

## 🔀 The Dynamic Proxy Architecture

To bridge modern streaming platforms (such as **Music Assistant**, **Spotify Connect**, or **Squeezelite / LMS**) into the analog BTicino matrix without audio artifacts, the MyHOME integration implements the **Dynamic Proxy** pattern.

```
┌──────────────────────────────────────────────┐
│  Home Assistant / Music Assistant (Player)   │
│  "media_player.living_room_sound"            │
└──────────────────────┬───────────────────────┘
                       │ (Proxy Layer)
                       ▼
         ┌───────────────────────────┐
         │ Decoder Pool Management   │
         │ - Dynamic claim / release │
         │ - Gain staging (+12 dB)   │
         │ - State & metadata mirror │
         └─────┬───────────────┬─────┘
               │               │
      [IP Service Call]   [OpenWebNet SCS Bus]
               │               │
               ▼               ▼
       ┌───────────────┐ ┌───────────────┐
       │ Audio Streamer│ │ F441M Matrix  │
       │ (Squeezelite /│ │ & Amplifier   │
       │  WiiM / Pi)   │ │ (Zone 1..9)   │
       └───────┬───────┘ └───────▲───────┘
               │ Analog Line-In  │
               └─────────────────┘
```

### Source switching

Selecting a source sends the same two frames a wall panel puts on the bus:

| Frame | Meaning |
| :--- | :--- |
| `*16*3*10S##` | Activate source device `S` |
| `*16*3*1ES##` | Route environment `E` to source `S` |

The routing address carries the **environment** digit of the amplifier
address, not the amplifier digit. Amplifier addresses are `EA` — environment
followed by amplifier — so zone `23` lives in environment 2 and is routed with
`121` (source 1) or `122` (source 2). The F441M switches per output and an
output serves a whole environment, so **every amplifier in that environment
follows the switch**. Zones 22 and 23 cannot play different sources; that is
matrix hardware, not an integration limitation.

> Earlier releases refused to send these frames, on the assumption that they
> caused relay clicks on MH200-class gateways. Bus captures on an MH200 show
> clean switching. The real problem was a routing address built from the wrong
> digit, which addressed an environment that did not exist.

### Naming your sources

Each F441M input (S1–S4) has a name field in the integration Options. Fill in
what is physically wired to it and **leave the rest blank**.

- Only named sources are offered in the Home Assistant source list.
- A zone routed to a blank input — typically by someone pressing a stale
  button on a wall panel — is labelled `Source N (not configured)` and logged
  once, so amplified silence or tuner hiss has a visible cause.
- The integration never re-routes the zone by itself. The choice was made at
  the panel, and silently overriding it would be its own surprise. Select a
  configured source to recover.

If no names are configured the legacy `Source 1`–`Source 4` list is used and
nothing is flagged, so existing installations are unaffected.

### The "Hardware Routing First" Model

For streaming, routing is still best left alone: `play_media` never changes
the source by itself.

**Recommended Practice**:

1. **Physical Cabling**: Connect the analog output of your network streamer (e.g. Raspberry Pi running Squeezelite, WiiM Pro, Cambridge Audio) into physical Source 1 on the F441M matrix.
2. **Matrix Configuration**: Configure your room amplifiers (or physical wall panels) to stay routed to Source 1.
3. **Automated Power Sequence**: When a stream starts, the integration proxy:
   - Claims an idle decoder from the shared **Decoder Pool**.
   - Wakes the decoder if it is in standby.
   - Powers ON the BTicino amplifier zone with a smooth `*16*1*WHERE##` command.
   - Forwards the stream URL to the streaming decoder.
   - Mirrors track metadata (title, artist, album art) and state back onto the Home Assistant room entity.
4. **Shutdown & Release**: When playback stops or the zone is turned off, the amplifier powers off (`*16*0*WHERE##`) and the decoder is released back to the idle pool.

---

## 🎛️ Gain Staging & Bus Noise Elimination

Analog SCS audio matrices can suffer from faint ground-loop hum or bus hiss if the input signal level is too low.

The MyHOME integration features **hardware gain staging**:
$$\text{Decoder Volume} = \text{Zone Volume} + \text{Pre-Gain Offset}$$

- Setting `pre_gain` (e.g., `+10%` to `+20%`) drives the network streamer at maximum undistorted line level.
- The room amplifier then operates at lower amplification, pushing the analog noise floor below audibility.

---

## ⚙️ Configuration via Home Assistant UI

You configure the Dynamic Proxy directly via the integration's **Options Flow**:

1. Go to **Settings** -> **Devices & Services** -> **MyHOME**.
2. Click **Configure**.
3. Scroll to the **Audio Decoder Mapping** section:
   - **Decoder Slot 1 Entity**: Select your backend media player (e.g. `media_player.squeezelite_salon`).
   - **Matrix Source Input**: Set to the physical F441M input (e.g. `1` for Source 1).
   - **Pre-Gain Offset**: Enter your pre-gain dB/percentage compensation (e.g. `15`).
   - *(Repeat for Decoders 2 through 4 if you have multiple streaming DACs).*
4. Click **Submit**.

> [!WARNING]
> **Avoid Recursive Loops**: Do NOT select a Music Assistant virtual player as the backend decoder entity. The backend decoder must be the actual hardware device (e.g. `media_player.squeezelite_salon`, `media_player.wiim_dining`), while Music Assistant targets the MyHOME zone entity.

---

## 📻 Standalone Fallback Mode (No Decoders)

If you do not configure any streaming decoders in the Options Flow, the room amplifier entities operate in **Native WHO = 16 Mode**:

- **On / Off**: Toggles the physical amplifier power.
- **Volume**: Controls the hardware volume step (0 to 30) via dimension 1.
- **Source Selection**: Switches the zone's environment between the configured physical sources.
- **Track Controls**: Sends OpenWebNet Next/Previous track commands (`WHAT = 20` / `WHAT = 21`) to compatible Legrand FM/DAB tuners.

---

## 📜 OpenWebNet WHO = 16 Reference Frames

| Action | OpenWebNet Frame | Description |
| :--- | :--- | :--- |
| **Zone Turn ON** | `*16*1*<WHERE>##` | Turns ON amplifier in room `<WHERE>` (1–9). |
| **Zone Turn OFF** | `*16*0*<WHERE>##` | Turns OFF amplifier in room `<WHERE>` (1–9). |
| **Volume UP** | `*16*10*<WHERE>##` | Steps amplifier volume UP. |
| **Volume DOWN** | `*16*11*<WHERE>##` | Steps amplifier volume DOWN. |
| **Set Exact Volume** | `*#16*<WHERE>*#1*<LEVEL>##` | Sets exact volume level (where `<LEVEL>` is 0 to 30). |
| **Activate Source `S`** | `*16*3*10S##` | Switches source device `S` on (`101`–`109`). |
| **Route Environment to Source** | `*16*3*1ES##` | Routes every amplifier of environment `E` to source `S`. |
| **Next Track / Station** | `*16*20*<WHERE>##` | Skips to next preset/track on active source. |
| **Prev Track / Station** | `*16*21*<WHERE>##` | Skips to previous preset/track on active source. |
