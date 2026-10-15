"""Tests for WHO 4 Vacation Countdown and Expiration Trace Replay.

Verifies that the synthetic trace fixture derived from Legrand gateway daemon
`bt_termo` (scs2open 0x0000EC74 / expiration 0x0000D2A8) and 3550 Central Unit
firmware 3.0.20 (0x0EF881 SUB.B #1, 0x2414) replays deterministically:
1. Replays 16 frames across initialization, vacation command write, active
   telemetry, 5 daily midnight decrements, and automatic expiration.
2. Central Unit #0 (`climate.climate_zone_0`) correctly tracks:
   - Initial weekly program 1 with `holiday_days = None`.
   - Vacation activation with `holiday_days = 5`.
   - Daily countdowns: 4, 3, 2, 1 remaining days.
   - Automatic expiration restoring weekly program 2 with `holiday_days` cleared.
3. Leaves 0 device health faults across the entire replay cycle.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from OWNd.message import OWNMessage
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import (
    CONF_DEVICE_TYPE,
    CONF_ENTITY,
    CONF_FIRMWARE,
    CONF_MANUFACTURER,
    DOMAIN,
)

TRACES_DIR = Path(__file__).resolve().parent / "fixtures" / "traces" / "oracle_who4_vacation"
VACATION_TRACE_FILE = TRACES_DIR / "myhome_trace_oracle_who4_vacation_cycle.json"


async def _setup_f454_gateway(hass: HomeAssistant) -> str:
    """Set up a mock F454 gateway config entry for trace replaying."""
    mac = "00:03:50:00:04:54"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.0.154",
            CONF_PORT: 20000,
            CONF_PASSWORD: "open",
            CONF_MAC: mac,
            CONF_NAME: "F454 Gateway",
            CONF_DEVICE_TYPE: "urn:schemas-bticino-it:device:lightingcontrolunit:1",
            CONF_FRIENDLY_NAME: "F454 Web Server",
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_FIRMWARE: "2.0.51",
        },
        unique_id=mac,
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.myhome.gateway.OWNSession.test_connection",
            return_value={"Success": True, "Message": None},
        ),
        patch("custom_components.myhome.gateway.MyHOMEGatewayHandler.listening_loop"),
        patch("custom_components.myhome.gateway.MyHOMEGatewayHandler.sending_loop"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    handler._on_event_connection_state_change(True)
    return mac


async def _replay_trace_frames(
    hass: HomeAssistant, mac: str, trace_file: Path
) -> int:
    """Replay all valid frames from a trace file into the dispatcher."""
    assert trace_file.is_file(), f"Missing trace fixture: {trace_file}"
    with open(trace_file, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    replayed = 0
    for item in trace_data["frames"]:
        raw = item.get("raw")
        if not raw or raw in ("*#*1##", "*#*0##"):
            continue

        msg = OWNMessage.parse(raw)
        if msg is not None:
            async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
            replayed += 1

    await hass.async_block_till_done()
    return replayed


@pytest.mark.asyncio
async def test_who4_vacation_step_by_step_countdown_and_expiry(
    hass: HomeAssistant,
) -> None:
    """Test step-by-step vacation countdown and expiration on climate.climate_zone_0.

    Replays frames individually to verify state transitions across time:
    - Initial baseline: Program 1 active, no holiday.
    - Day 0: Vacation mode activated for 5 days with return program 2.
    - Day 1-4: Midnight decrements reduce holiday_days from 4 down to 1.
    - Day 5: Expiration frame *4*1102*#0## restores program 2 and clears holiday_days.
    """
    mac = await _setup_f454_gateway(hass)

    with open(VACATION_TRACE_FILE, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    frames = [item["raw"] for item in trace_data["frames"]]
    assert len(frames) == 16

    # 1. Initial plant state (frames 0..3): temp, season, program 1, subzone
    for raw in frames[0:4]:
        msg = OWNMessage.parse(raw)
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
    await hass.async_block_till_done()

    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0 is not None
    assert state_0.attributes.get("program") == 1
    assert "holiday_days" not in state_0.attributes

    # 2. Vacation activation (frames 4..9): write, status flags, timestamps, bare status
    for raw in frames[4:10]:
        msg = OWNMessage.parse(raw)
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
    await hass.async_block_till_done()

    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0 is not None
    assert state_0.attributes.get("holiday_days") == 5

    # 3. Midnight decrements:
    # Frame 10: Day 1 decrement (*4*13004*#0##) -> 4 days remaining
    msg = OWNMessage.parse(frames[10])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
    await hass.async_block_till_done()
    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0.attributes.get("holiday_days") == 4

    # Frame 11: Day 2 decrement (*4*13003*#0##) -> 3 days remaining
    msg = OWNMessage.parse(frames[11])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
    await hass.async_block_till_done()
    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0.attributes.get("holiday_days") == 3

    # Frame 12: Day 3 decrement (*4*13002*#0##) -> 2 days remaining
    msg = OWNMessage.parse(frames[12])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
    await hass.async_block_till_done()
    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0.attributes.get("holiday_days") == 2

    # Frame 13: Day 4 decrement (*4*13001*#0##) -> 1 day remaining
    msg = OWNMessage.parse(frames[13])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
    await hass.async_block_till_done()
    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0.attributes.get("holiday_days") == 1

    # 4. Vacation expiration (frames 14..15): return program 2, subzone
    for raw in frames[14:16]:
        msg = OWNMessage.parse(raw)
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
    await hass.async_block_till_done()

    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0 is not None
    assert "holiday_days" not in state_0.attributes
    assert state_0.attributes.get("program") == 2

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []


@pytest.mark.asyncio
async def test_who4_vacation_full_trace_replay(hass: HomeAssistant) -> None:
    """Replay entire 16-frame vacation trace cycle in batch.

    Ensures that replaying the complete trace end-to-end:
    1. Replays all 16 frames cleanly through the dispatcher.
    2. Leaves 0 device health faults.
    3. Leaves climate.climate_zone_0 in program 2 with holiday_days cleared.
    """
    mac = await _setup_f454_gateway(hass)
    replayed = await _replay_trace_frames(hass, mac, VACATION_TRACE_FILE)
    assert replayed == 16

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []

    state_0 = hass.states.get("climate.climate_zone_0")
    assert state_0 is not None
    assert state_0.attributes.get("program") == 2
    assert "holiday_days" not in state_0.attributes
