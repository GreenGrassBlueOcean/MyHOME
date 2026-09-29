# MH200 + F441M Multiroom Sound Traces

Authentic on-wire bus frames and diagnostic configuration captured on a live physical MH200 plant with F441/F441M 4-input audio matrix:
- **Gateway**: BTicino MH200
- **Audio Matrix**: Legrand / BTicino F441M (WHO=16 / WHO=22)
- **Sources**:
  - Source 1: Tuner / Radio (`*16*3*101##`)
  - Source 2: Digital Streamer / Cambridge Audio CXN (`*16*3*102##`)
- **Environments & Sound Zones**:
  - Environment 1: zones 14, 17, 18
  - Environment 2: zones 21, 22, 23
  - Environment 3: zones 35, 36 (Eetkamer)

### Validated Protocol Behaviors
1. **Multi-Environment Routing**:
   - `*16*3*122##` -> routes Environment 2 to Source 2 (Streamer).
   - `*16*3*132##` -> routes Environment 3 to Source 2 (Streamer).
2. **Zone Power & Volume Status**:
   - `*16*13*36##` -> zone 36 unmuted / active.
   - `*#16*23*1*19##` -> zone 23 reporting volume level 19.
   - `*#16*35*1*26##` -> zone 35 reporting volume level 26.
3. **Multiroom Grouping & Leader Handover**:
   - Grouping across zones 35 & 36 under Environment 3.
   - Unjoining a group leader without tearing down playback on remaining member zones.
4. **Gain Staging (Option B)**:
   - Locking streamer source output to 100% (0 dBFS line level) to maximize signal-to-noise ratio into the F441 analog matrix, eliminating high-gain bus hissing.

### Live group lifecycle, 2026-09-29 (`live_2026-09-29_group_park_and_resume.json`)
Three rooms (badkamer leads Bureau and Eetkamer) on the Audio Decoder decoder: pause, the anti-hiss switch-off after 60 s that keeps the group, and the resume. The fixture holds the bus frames, the decoder states that were seen, and what Music Assistant did; `tests/test_audio_group_live_replay.py` replays it. Its `findings` list is why each assertion exists.
