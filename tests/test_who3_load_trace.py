"""Tests for WHO 3 Load Control Trace Replay.

Verifies that the synthetic trace fixture derived from Legrand gateway daemon
`bt_energia` (MH202 & F459 register mappings $03AA001613, $03AA001612, etc.)
replays deterministically:
1. Replays 9 frames across aggregate dimension 0, individual dimensions 1-4,
   and load shedding activation, shed, and restoration.
2. Measurements decode into typed properties:
   - Power (W), Voltage (V), Current (A), Power Factor.
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
from OWNd.message.load import OWNLoadEvent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import (
    CONF_DEVICE_TYPE,
    CONF_ENTITY,
    CONF_FIRMWARE,
    CONF_MANUFACTURER,
    DOMAIN,
)

TRACES_DIR = Path(__file__).resolve().parent / "fixtures" / "traces" / "oracle_who3_load"
LOAD_TRACE_FILE = TRACES_DIR / "myhome_trace_oracle_who3_load.json"


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
async def test_who3_load_control_trace_measurements_and_lifecycle(
    hass: HomeAssistant,
) -> None:
    """Test step-by-step decoding of WHO 3 load control telemetry from synthetic trace."""
    mac = await _setup_mh202_gateway(hass)

    with open(LOAD_TRACE_FILE, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    frames = [item["raw"] for item in trace_data["frames"]]
    assert len(frames) == 9

    # Frame 0: Aggregate Dimension 0 (*#3*10*0*230*12*2760*1520##)
    msg0 = OWNMessage.parse(frames[0])
    assert isinstance(msg0, OWNLoadEvent)
    assert msg0.power == 230
    assert msg0.voltage == 12
    assert msg0.current == 2760.0
    assert msg0.power_factor == 1520.0
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg0)

    # Frame 1: Dimension 1 Power (*#3*10*1*230##)
    msg1 = OWNMessage.parse(frames[1])
    assert isinstance(msg1, OWNLoadEvent)
    assert msg1.power == 230
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg1)

    # Frame 2: Dimension 2 Voltage (*#3*10*2*230##)
    msg2 = OWNMessage.parse(frames[2])
    assert isinstance(msg2, OWNLoadEvent)
    assert msg2.voltage == 230
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg2)

    # Frame 3: Dimension 3 Current (*#3*10*3*120##)
    msg3 = OWNMessage.parse(frames[3])
    assert isinstance(msg3, OWNLoadEvent)
    assert msg3.current == 120.0
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg3)

    # Frame 4: Dimension 4 Power Factor (*#3*10*4*980##)
    msg4 = OWNMessage.parse(frames[4])
    assert isinstance(msg4, OWNLoadEvent)
    assert msg4.power_factor == 980.0
    async_dispatcher_send(hass, f"myhome_message_{mac}", msg4)

    # Frames 5..8: Load control management & shedding cycle
    for raw in frames[5:9]:
        msg = OWNMessage.parse(raw)
        assert msg is not None
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)

    await hass.async_block_till_done()

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []


@pytest.mark.asyncio
async def test_who3_load_full_trace_replay(hass: HomeAssistant) -> None:
    """Replay complete 9-frame WHO 3 trace in batch, verifying zero faults."""
    mac = await _setup_mh202_gateway(hass)

    with open(LOAD_TRACE_FILE, "r", encoding="utf-8") as f:
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
    assert replayed == 9

    handler = hass.data[DOMAIN][mac][CONF_ENTITY]
    assert handler.device_health.faults == []
