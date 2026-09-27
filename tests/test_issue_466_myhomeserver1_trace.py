"""Tests for #466: Real-World BTicino MyHomeServer1 Gateway Trace Replay.

Verifies that authentic on-wire OpenWebNet traces captured from a physical
BTicino MyHomeServer1 gateway (contributed by @TheDarkWizard in issue #466 comment 5855690408)
can be deterministically parsed and replayed against the integration state machine
without exceptions or regressions.
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
from OWNd.message import (
    OWNAutomationEvent,
    OWNCENPlusEvent,
    OWNEnergyEvent,
    OWNHeatingEvent,
    OWNLightingCommand,
    OWNLightingEvent,
    OWNMessage,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import (
    CONF_DEVICE_TYPE,
    CONF_ENTITY,
    CONF_FIRMWARE,
    CONF_MANUFACTURER,
    DOMAIN,
)

TRACES_DIR = Path(__file__).resolve().parent / "fixtures" / "traces" / "issue_466"
CEN_SCENARIO_FILE = TRACES_DIR / "myhome_trace_MyHomeServer1_cen_scenario_2026-09-27T13-28-10.json"
GROUP_LIGHTS_FILE = TRACES_DIR / "myhome_trace_MyHomeServer1_group_lights_2026-09-27T13-32-12.json"
CEN_COVER_SCENARIOS_FILE = TRACES_DIR / "myhome_trace_MyHomeServer1_cen_cover_scenarios_2026-09-27T13-47-33.json"
SCENARIOS_DIAGNOSTIC_FILE = TRACES_DIR / "myhome_trace_MyHomeServer1_scenarios_cover_diagnostic_2026-09-27T13-47-33.json"
MONOSTABLE_DIAGNOSTIC_FILE = TRACES_DIR / "myhome_trace_MyHomeServer1_monostable_cover_diagnostic_2026-09-27T13-51-19.json"
BISTABLE_COVER_FILE = TRACES_DIR / "myhome_trace_MyHomeServer1_bistable_cover_2026-09-27T13-54-05.json"


async def _setup_myhomeserver1_gateway(hass: HomeAssistant, mac: str = "00:03:50:00:04:66"):
    """Set up a mock MyHomeServer1 config entry and gateway handler."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 20000,
            CONF_PASSWORD: "pass",
            CONF_MAC: mac,
            CONF_NAME: "MyHomeServer1",
            CONF_DEVICE_TYPE: "urn:schemas-bticino-it:device:lightingcontrolunit:1",
            CONF_FRIENDLY_NAME: "MyHomeServer1 Gateway",
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_FIRMWARE: "2.87.13",
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
    return handler, mac


@pytest.mark.asyncio
async def test_myhomeserver1_cen_scenario_trace_replay(hass: HomeAssistant) -> None:
    """Replay all 8 frames from the CEN+ scenario activation trace.

    Verifies that short-press CEN+ events on address 21 (*25*21#1*21##)
    and subsequent lighting cascade (*1*1*16##, *1*1*18##, *1*1*19##) replay cleanly.
    """
    assert CEN_SCENARIO_FILE.is_file(), f"Missing fixture: {CEN_SCENARIO_FILE}"
    with open(CEN_SCENARIO_FILE, encoding="utf-8") as f:
        trace_data = json.load(f)

    assert trace_data["gateway"]["model"] == "MyHomeServer1"
    assert trace_data["gateway"]["firmware"] == "2.87.13"

    _, mac = await _setup_myhomeserver1_gateway(hass)
    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 8

    cen_plus_events = []
    lighting_events = []

    for item in raw_frames:
        raw = item["raw"]
        msg = OWNMessage.parse(raw)
        if isinstance(msg, OWNCENPlusEvent):
            cen_plus_events.append(msg)
        elif isinstance(msg, OWNLightingEvent):
            lighting_events.append(msg)
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)

    await hass.async_block_till_done()

    assert len(cen_plus_events) == 2
    for event in cen_plus_events:
        assert event.who == 25
        assert event.where == "21"
        assert event.push_button == 1
        assert event.is_short_pressed is True

    assert len(lighting_events) == 6
    for event in lighting_events:
        assert event.who == 1
        assert event.is_on is True
        assert event.where in ("16", "18", "19")


@pytest.mark.asyncio
async def test_myhomeserver1_bistable_cover_trace_replay(hass: HomeAssistant) -> None:
    """Replay all 11 frames from the bistable cover movement trace.

    Verifies the full operational cycle of cover 03:
    1. Advanced DOWN command (*2*1000#12#100#001#1*03##) & Dimension 10 feedback (*#2*03*10*12*100*001*0##)
    2. Mid-travel user STOP (*2*1000#10#001#1*03##) & stopped position at 83% (*#2*03*10*10*83*001*0##)
    3. Advanced UP command (*2*1000#11#100#001#1*03##) & moving status (*#2*03*10*11*83*001*0##)
    4. Limit switch reached STOP at 100% (*#2*03*10*10*100*001*0##)
    5. Legacy directional frames (*2*2*03##, *2*0*03##, *2*1*03##, *2*0*03##)
    """
    assert BISTABLE_COVER_FILE.is_file(), f"Missing fixture: {BISTABLE_COVER_FILE}"
    with open(BISTABLE_COVER_FILE, encoding="utf-8") as f:
        trace_data = json.load(f)

    _, mac = await _setup_myhomeserver1_gateway(hass)
    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 11

    replayed = 0
    automation_events = 0
    dimension_10_events = 0

    for item in raw_frames:
        raw = item["raw"]
        msg = OWNMessage.parse(raw)
        if isinstance(msg, OWNAutomationEvent):
            automation_events += 1
            if msg.dimension == 10:
                dimension_10_events += 1
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
        replayed += 1

    await hass.async_block_till_done()

    assert replayed == 11
    assert automation_events == 11
    assert dimension_10_events == 4  # 4 Dimension 10 position reports


@pytest.mark.asyncio
async def test_myhomeserver1_group_lights_trace_replay(hass: HomeAssistant) -> None:
    """Replay all 16 frames from the Group of Light capture.

    Verifies group toggle commands on group #1 (*1*0*#1## and *1*1*#1##)
    interleaved with individual member fixture echoes on 16, 18, 19.
    """
    assert GROUP_LIGHTS_FILE.is_file(), f"Missing fixture: {GROUP_LIGHTS_FILE}"
    with open(GROUP_LIGHTS_FILE, encoding="utf-8") as f:
        trace_data = json.load(f)

    _, mac = await _setup_myhomeserver1_gateway(hass)
    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 16

    group_commands = []
    member_events = []

    for item in raw_frames:
        raw = item["raw"]
        msg = OWNMessage.parse(raw)
        if isinstance(msg, (OWNLightingCommand, OWNLightingEvent)):
            if msg.where == "#1":
                group_commands.append(msg)
            else:
                member_events.append(msg)
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)

    await hass.async_block_till_done()

    assert len(group_commands) == 4  # 2 off, 2 on
    assert len(member_events) == 12  # 3 fixtures * 4 transitions


@pytest.mark.asyncio
async def test_myhomeserver1_cen_cover_scenarios_replay(hass: HomeAssistant) -> None:
    """Replay all 8 frames from the CEN+ multi-scenario activation trace.

    Verifies:
    1. CEN+ button presses on distinct addresses 21, 22, 23 (*25*21#1*21##, 22##, 23##)
    2. Direct shutter target positioning write to 85% (*#2*03*#11#001#1*85##) and position feedback
    3. Active power telemetry on meters 51 and 52 (*#18*51*113*444##, *#18*52*113*183##)
    """
    assert CEN_COVER_SCENARIOS_FILE.is_file(), f"Missing fixture: {CEN_COVER_SCENARIOS_FILE}"
    with open(CEN_COVER_SCENARIOS_FILE, encoding="utf-8") as f:
        trace_data = json.load(f)

    _, mac = await _setup_myhomeserver1_gateway(hass)
    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 8

    cen_addresses = []
    energy_readings = []

    for item in raw_frames:
        raw = item["raw"]
        msg = OWNMessage.parse(raw)
        if isinstance(msg, OWNCENPlusEvent):
            cen_addresses.append(msg.where)
        elif isinstance(msg, OWNEnergyEvent):
            energy_readings.append((msg.where, msg.dimension))
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)

    await hass.async_block_till_done()

    assert cen_addresses == ["21", "22", "23"]
    assert ("51", 113) in energy_readings
    assert ("52", 113) in energy_readings


@pytest.mark.asyncio
async def test_myhomeserver1_scenarios_cover_diagnostic_replay(hass: HomeAssistant) -> None:
    """Replay all 73 frames from Delete.Scenarios diagnostic trace.

    Covers multi-subsystem traffic:
    - CEN+ triggers (addresses 21, 22, 23)
    - Shutter target positioning to 0% and 100%
    - Energy active power (Dimension 113) and power threshold alarms (Dimension 1200)
    - Thermoregulation zone 2 temperature report at 27.1 °C (*#4*2*0*0271##)
    - WHO 1001 Physical Layer Diagnostics: device ping, identity, firmware, and slot objects
    """
    assert SCENARIOS_DIAGNOSTIC_FILE.is_file(), f"Missing fixture: {SCENARIOS_DIAGNOSTIC_FILE}"
    with open(SCENARIOS_DIAGNOSTIC_FILE, encoding="utf-8") as f:
        trace_data = json.load(f)

    _, mac = await _setup_myhomeserver1_gateway(hass)
    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 73

    whos_seen = set()
    temperatures_seen = []

    for item in raw_frames:
        raw = item["raw"]
        msg = OWNMessage.parse(raw)
        whos_seen.add(msg.who)
        if isinstance(msg, OWNHeatingEvent) and getattr(msg, "main_temperature", None) is not None:
            temperatures_seen.append((msg.where, msg.main_temperature))
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)

    await hass.async_block_till_done()

    assert whos_seen == {2, 4, 18, 25, 1001}
    assert ("2", 27.1) in temperatures_seen


@pytest.mark.asyncio
async def test_myhomeserver1_monostable_cover_diagnostic_replay(hass: HomeAssistant) -> None:
    """Replay all 114 frames from Confid.Cover.-.monostable diagnostic trace.

    Verifies device configuration memory dump via WHO 1001:
    - Session start/stop commands (*1000*5*0## and *1000*6*0##)
    - Dimension 30 slot object assignments
    - Dimension 35 indexed configuration register reads across 84 parameters
    All frames replay without errors or state poisoning.
    """
    assert MONOSTABLE_DIAGNOSTIC_FILE.is_file(), f"Missing fixture: {MONOSTABLE_DIAGNOSTIC_FILE}"
    with open(MONOSTABLE_DIAGNOSTIC_FILE, encoding="utf-8") as f:
        trace_data = json.load(f)

    _, mac = await _setup_myhomeserver1_gateway(hass)
    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 114

    replayed = 0
    for item in raw_frames:
        raw = item["raw"]
        msg = OWNMessage.parse(raw)
        async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
        replayed += 1

    await hass.async_block_till_done()
    assert replayed == 114
