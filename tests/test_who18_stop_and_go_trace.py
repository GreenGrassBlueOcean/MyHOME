"""Tests for WHO 18 Stop&Go Circuit Breaker Trace Replay.

Verifies that the synthetic trace fixture derived from Legrand TS10 client
code and firmware oracle suite `energy-ts10.cases` ($06D101023210...)
replays deterministically:
1. Replays 11 frames across breaker open/close, differential test results,
   auto-reset, earth leakage tracking, frequency, and status mask.
2. Verified typed properties:
   - Line numbers (1, 2 from 11, 12).
   - `is_open` / `is_closed`.
   - `differential_test_passed` & `differential_test_result`.
   - `is_auto_reset_active`, `is_tracking_active`.
   - `test_frequency_days`, `status_mask`.
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
from OWNd.message.energy import OWNStopAndGoEvent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import (
    CONF_DEVICE_TYPE,
    CONF_ENTITY,
    CONF_FIRMWARE,
    CONF_MANUFACTURER,
    DOMAIN,
)

TRACES_DIR = Path(__file__).resolve().parent / "fixtures" / "traces" / "oracle_who18_stop_and_go"
STOP_AND_GO_TRACE_FILE = TRACES_DIR / "myhome_trace_oracle_who18_stop_and_go.json"


async def _setup_mh202_gateway(hass: HomeAssistant) -> str:
    """Set up a mock MH202 gateway config entry for trace replaying."""
    mac = "00:03:50:00:02:02"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.0.202",
            CONF_PORT: 20000,
            CONF_PASSWORD: "open",
            CONF_MAC: mac,
            CONF_NAME: "MH202 Gateway",
            CONF_DEVICE_TYPE: "urn:schemas-bticino-it:device:lightingcontrolunit:1",
            CONF_FRIENDLY_NAME: "MH202 Scenarios and Energy Server",
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_FIRMWARE: "1.0.24",
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


@pytest.mark.asyncio
async def test_who18_stop_and_go_trace_decoding_and_states(
    hass: HomeAssistant,
) -> None:
    """Test step-by-step decoding of WHO 18 Stop&Go breaker frames from synthetic trace."""
    mac = await _setup_mh202_gateway(hass)

    with open(STOP_AND_GO_TRACE_FILE, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    frames = [item["raw"] for item in trace_data["frames"]]
    assert len(frames) == 11

    # Frame 0: Line 1 Breaker Closed (*18*22*11##)
    msg0 = OWNMessage.parse(frames[0])
    assert isinstance(msg0, OWNStopAndGoEvent)
    assert msg0.line == 1
    assert msg0.is_closed is True
    assert msg0.is_open is False
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg0)

    # Frame 1: Frequency read (*#18*11*212*10##)
    msg1 = OWNMessage.parse(frames[1])
    assert isinstance(msg1, OWNStopAndGoEvent)
    assert msg1.test_frequency_days == 10
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg1)

    # Frame 2: Breaker Open Trip (*18*21*11##)
    msg2 = OWNMessage.parse(frames[2])
    assert isinstance(msg2, OWNStopAndGoEvent)
    assert msg2.is_open is True
    assert msg2.is_closed is False
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg2)

    # Frame 3: Earth leakage tracking (*18*28*11##)
    msg3 = OWNMessage.parse(frames[3])
    assert isinstance(msg3, OWNStopAndGoEvent)
    assert msg3.is_tracking_active is True
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg3)

    # Frame 4: Differential test positive (*18*23*11##)
    msg4 = OWNMessage.parse(frames[4])
    assert isinstance(msg4, OWNStopAndGoEvent)
    assert msg4.differential_test_passed is True
    assert msg4.differential_test_result == "positive"
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg4)

    # Frame 5: Differential test negative (*18*24*11##)
    msg5 = OWNMessage.parse(frames[5])
    assert isinstance(msg5, OWNStopAndGoEvent)
    assert msg5.differential_test_passed is False
    assert msg5.differential_test_result == "negative"
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg5)

    # Frame 6: Auto reset active (*18*26*11##)
    msg6 = OWNMessage.parse(frames[6])
    assert isinstance(msg6, OWNStopAndGoEvent)
    assert msg6.is_auto_reset_active is True
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg6)

    # Frame 7: Re-close (*18*22*11##)
    msg7 = OWNMessage.parse(frames[7])
    assert isinstance(msg7, OWNStopAndGoEvent)
    assert msg7.is_closed is True
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg7)

    # Frame 8: Tracking disabled (*18*29*11##)
    msg8 = OWNMessage.parse(frames[8])
    assert isinstance(msg8, OWNStopAndGoEvent)
    assert msg8.is_tracking_active is False
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg8)

    # Frame 9: Diagnostic status mask (*#18*11*250*0001##)
    msg9 = OWNMessage.parse(frames[9])
    assert isinstance(msg9, OWNStopAndGoEvent)
    assert msg9.status_mask == "0001"
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg9)

    # Frame 10: Line 2 (*18*22*12##)
    msg10 = OWNMessage.parse(frames[10])
    assert isinstance(msg10, OWNStopAndGoEvent)
    assert msg10.line == 2
    assert msg10.is_closed is True
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg10)

    await hass.async_block_till_done()

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []


@pytest.mark.asyncio
async def test_who18_stop_and_go_full_trace_replay(hass: HomeAssistant) -> None:
    """Replay complete 11-frame Stop&Go trace in batch, verifying zero faults."""
    mac = await _setup_mh202_gateway(hass)

    with open(STOP_AND_GO_TRACE_FILE, "r", encoding="utf-8") as f:
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
    assert replayed == 11

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []
