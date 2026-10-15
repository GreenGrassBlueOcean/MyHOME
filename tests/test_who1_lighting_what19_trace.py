"""Tests for WHO 1 Lighting WHAT 19 Anomaly Trace Replay.

Verifies that the synthetic trace fixture derived from Legrand `bt_luci`
(0x16ab4 status byte 'E' to 19) and `libdiag.so.0.0` (0x132e4 bitmask)
replays deterministically:
1. Replays 7 frames across baseline ON, actuator anomaly (WHAT 19), diagnostic
   bitmask correlation, disconnected dimmer channel no-load, and fault recovery.
2. Verified light entity & OWNd semantics:
   - WHAT 19 parses with `unknown_state = 19`, `is_on = None`.
   - Actuator 92 with all-1s mask safely resolves to `off` with `no_load = True` (no phantom ON).
   - Actuator 74 recovers to `on` upon reconnection (*1*1*74##) and then to `off` (*1*0*74##).
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
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from OWNd.message import OWNMessage
from OWNd.message.lighting import OWNLightingEvent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import (
    CONF_DEVICE_TYPE,
    CONF_ENTITY,
    CONF_FIRMWARE,
    CONF_MANUFACTURER,
    DOMAIN,
)

TRACES_DIR = Path(__file__).resolve().parent / "fixtures" / "traces" / "oracle_who1_lighting_what19"
WHAT19_TRACE_FILE = TRACES_DIR / "myhome_trace_oracle_who1_lighting_what19.json"


async def _setup_mh200n_gateway(hass: HomeAssistant) -> str:
    """Set up a mock MH200N gateway config entry for trace replaying."""
    mac = "00:03:50:00:02:00"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.0.200",
            CONF_PORT: 20000,
            CONF_PASSWORD: "open",
            CONF_MAC: mac,
            CONF_NAME: "MH200N Gateway",
            CONF_DEVICE_TYPE: "urn:schemas-bticino-it:device:lightingcontrolunit:1",
            CONF_FRIENDLY_NAME: "MH200N Scenarios Unit",
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_FIRMWARE: "1.1.8",
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
async def test_who1_lighting_what19_step_by_step_and_entity_lifecycle(
    hass: HomeAssistant,
) -> None:
    """Test step-by-step decoding of lighting WHAT 19 anomaly and entity state transitions."""
    mac = await _setup_mh200n_gateway(hass)

    with open(WHAT19_TRACE_FILE, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    frames = [item["raw"] for item in trace_data["frames"]]
    assert len(frames) == 7

    # Frame 0: Actuator 74 Baseline ON (*1*1*74##)
    msg0 = OWNMessage.parse(frames[0])
    assert isinstance(msg0, OWNLightingEvent)
    assert msg0.is_on is True
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg0)
    await hass.async_block_till_done()

    state_74 = hass.states.get("light.light_74")
    assert state_74 is not None
    assert state_74.state == STATE_ON

    # Frame 1: Actuator 74 Anomaly (*1*19*74##)
    msg1 = OWNMessage.parse(frames[1])
    assert isinstance(msg1, OWNLightingEvent)
    assert msg1.unknown_state == 19
    assert msg1.is_on is None
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg1)
    await hass.async_block_till_done()

    state_74 = hass.states.get("light.light_74")
    assert state_74 is not None
    assert state_74.attributes.get("no_load") is True

    # Frame 2: Actuator 74 Autodiagnostic bitmask (*#1001*74*11*111110111111111111110111##)
    msg2 = OWNMessage.parse(frames[2])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg2)
    await hass.async_block_till_done()

    # Frame 3: Actuator 92 No-load disconnected channel (*1*19*92##)
    msg3 = OWNMessage.parse(frames[3])
    assert isinstance(msg3, OWNLightingEvent)
    assert msg3.unknown_state == 19
    assert msg3.is_on is None
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg3)
    await hass.async_block_till_done()

    state_92 = hass.states.get("light.light_92")
    assert state_92 is not None
    assert state_92.state == STATE_OFF
    assert state_92.attributes.get("no_load") is True

    # Frame 4: Actuator 92 Autodiagnostic bitmask all 1s
    msg4 = OWNMessage.parse(frames[4])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg4)
    await hass.async_block_till_done()

    # Frame 5: Actuator 74 Fault Recovery (*1*1*74##)
    msg5 = OWNMessage.parse(frames[5])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg5)
    await hass.async_block_till_done()

    state_74 = hass.states.get("light.light_74")
    assert state_74 is not None
    assert state_74.state == STATE_ON
    assert "no_load" not in state_74.attributes

    # Frame 6: Actuator 74 Normal OFF (*1*0*74##)
    msg6 = OWNMessage.parse(frames[6])
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg6)
    await hass.async_block_till_done()

    state_74 = hass.states.get("light.light_74")
    assert state_74 is not None
    assert state_74.state == STATE_OFF

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []


@pytest.mark.asyncio
async def test_who1_lighting_what19_full_trace_replay(hass: HomeAssistant) -> None:
    """Replay complete 7-frame WHAT 19 trace in batch, verifying zero faults."""
    mac = await _setup_mh200n_gateway(hass)

    with open(WHAT19_TRACE_FILE, "r", encoding="utf-8") as f:
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
    assert replayed == 7

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []
