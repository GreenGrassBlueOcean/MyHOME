"""Tests for #466: Real-World BTicino F454 and MH202 Gateway Trace Replay.

Verifies that authentic on-wire OpenWebNet traces captured from physical
F454 and MH202 gateways (contributed by @anotherjulien in issue #466 comment 5849027587)
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
    OWNAutomationCommand,
    OWNAutomationEvent,
    OWNCENPlusEvent,
    OWNDryContactEvent,
    OWNEnergyEvent,
    OWNEvent,
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
F454_SWEEP_FILE = TRACES_DIR / "myhome_sweep_F454_all_2026-09-26T16-59-13.json"
MH202_TRACE_FILE = TRACES_DIR / "myhome_trace_MH202_all_2026-09-26T16-59-17.json"


@pytest.mark.asyncio
async def test_f454_sweep_trace_replay_without_exceptions(hass: HomeAssistant) -> None:
    """Replay all 238 on-wire frames from the physical F454 bus sweep capture.

    Ensures every frame across WHO 1 (lights/dimmers), WHO 2 (covers), WHO 4 (climate),
    WHO 9 (auxiliary), WHO 13 (gateway), WHO 14 (actuator lock), WHO 18 (energy),
    and WHO 25 (CEN+/dry contact) replays cleanly through the event dispatcher.
    """
    assert F454_SWEEP_FILE.is_file(), f"Missing trace fixture: {F454_SWEEP_FILE}"

    with open(F454_SWEEP_FILE, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    assert trace_data["gateway"]["model"] == "F454"
    assert trace_data["gateway"]["firmware"] == "2.0.51"
    assert trace_data["gateway"]["identification"]["who13_code"] == "200"

    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 238

    mac = "00:03:50:00:04:54"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.0.2.54",
            CONF_PORT: 20000,
            CONF_PASSWORD: "pass",
            CONF_MAC: mac,
            CONF_NAME: "F454",
            CONF_DEVICE_TYPE: "urn:schemas-bticino-it:device:lightingcontrolunit:1",
            CONF_FRIENDLY_NAME: "F454 Gateway",
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

    replayed = 0
    whos_seen: set[str] = set()

    for item in raw_frames:
        raw = item.get("raw")
        if not raw or raw in ("*#*1##", "*#*0##"):
            continue

        try:
            msg = OWNMessage.parse(raw)
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"Failed to parse authentic F454 frame {raw!r}: {exc}")

        if msg is not None:
            async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
            if hasattr(msg, "who") and msg.who:
                whos_seen.add(str(msg.who))
        replayed += 1

    await hass.async_block_till_done()
    assert replayed == 238

    expected_whos = {"1", "2", "4", "9", "13", "14", "18", "25"}
    assert expected_whos.issubset(whos_seen), (
        f"Missing expected WHOs. Found: {whos_seen}, expected: {expected_whos}"
    )

    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.asyncio
async def test_mh202_trace_replay_without_exceptions(hass: HomeAssistant) -> None:
    """Replay all 314 on-wire frames from the physical MH202 trace capture.

    Ensures every frame across WHO 1 (lights/dimmers), WHO 2 (covers), WHO 4 (climate),
    WHO 9 (auxiliary), WHO 13 (gateway), WHO 14 (actuator lock), WHO 18 (energy),
    and WHO 25 (CEN+/dry contact) replays cleanly through the event dispatcher.
    """
    assert MH202_TRACE_FILE.is_file(), f"Missing trace fixture: {MH202_TRACE_FILE}"

    with open(MH202_TRACE_FILE, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    assert trace_data["gateway"]["model"] == "MH202"
    assert trace_data["gateway"]["firmware"] == "1.0.21"
    assert trace_data["gateway"]["identification"]["who13_code"] == "200"

    raw_frames = trace_data["frames"]
    assert len(raw_frames) == 314

    mac = "00:03:50:00:02:02"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.0.2.202",
            CONF_PORT: 20000,
            CONF_PASSWORD: "pass",
            CONF_MAC: mac,
            CONF_NAME: "MH202",
            CONF_DEVICE_TYPE: "urn:schemas-bticino-it:device:lightingcontrolunit:1",
            CONF_FRIENDLY_NAME: "MH202 Gateway",
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_FIRMWARE: "1.0.21",
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

    replayed = 0
    whos_seen: set[str] = set()

    for item in raw_frames:
        raw = item.get("raw")
        if not raw or raw in ("*#*1##", "*#*0##"):
            continue

        try:
            msg = OWNMessage.parse(raw)
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"Failed to parse authentic MH202 frame {raw!r}: {exc}")

        if msg is not None:
            async_dispatcher_send(hass, f"myhome_message_{mac}", msg)
            if hasattr(msg, "who") and msg.who:
                whos_seen.add(str(msg.who))
        replayed += 1

    await hass.async_block_till_done()
    assert replayed == 314

    expected_whos = {"1", "2", "4", "9", "13", "14", "18", "25"}
    assert expected_whos.issubset(whos_seen), (
        f"Missing expected WHOs. Found: {whos_seen}, expected: {expected_whos}"
    )

    await hass.config_entries.async_unload(entry.entry_id)


def test_actuator_lock_frames() -> None:
    """Verify actuator lock/unlock (WHO 14) frames from the authentic traces.

    Closes critical hardware matrix gap for both F454 and MH202.
    """
    lock_frame = "*14*1*32##"
    unlock_frame = "*14*0*32##"

    msg_lock = OWNMessage.parse(lock_frame)
    assert isinstance(msg_lock, OWNEvent)
    assert msg_lock.who == 14
    assert msg_lock._what == 1
    assert msg_lock.where == "32"

    msg_unlock = OWNMessage.parse(unlock_frame)
    assert isinstance(msg_unlock, OWNEvent)
    assert msg_unlock.who == 14
    assert msg_unlock._what == 0
    assert msg_unlock.where == "32"


def test_energy_meter_f520_telemetry() -> None:
    """Verify F520 energy totalizers and active power telemetry from authentic traces."""
    # Totalizer reading (dimension 51): Sensor 2 total power consumption
    totalizer = OWNMessage.parse("*#18*52*51*14159553##")
    assert isinstance(totalizer, OWNEnergyEvent)
    assert totalizer.who == 18
    assert totalizer.where == "52"
    assert totalizer.dimension == 51
    assert totalizer._total_consumption == 14159553

    # Active power draw reading (dimension 113)
    active_power = OWNMessage.parse("*#18*52*113*1##")
    assert isinstance(active_power, OWNEnergyEvent)
    assert active_power.who == 18
    assert active_power.where == "52"
    assert active_power.dimension == 113
    assert active_power._active_power == 1


def test_cenplus_and_dry_contact_frames() -> None:
    """Verify CEN+ pushbuttons and dry contact interface frames."""
    # CEN+ Pushbutton short press
    btn_short = OWNMessage.parse("*25*21#1*21##")
    assert isinstance(btn_short, OWNCENPlusEvent)
    assert btn_short.who == 25
    assert btn_short._what == 21
    assert btn_short.push_button == 1
    assert btn_short.object == "1"
    assert btn_short.is_short_pressed is True

    # CEN+ Pushbutton release after long press
    btn_rel = OWNMessage.parse("*25*21#2*21##")
    assert isinstance(btn_rel, OWNCENPlusEvent)
    assert btn_rel.who == 25
    assert btn_rel._what == 21
    assert btn_rel.push_button == 2

    # Dry contact transitions from physical contact interface
    dc_off = OWNMessage.parse("*25*32#1*33##")
    assert isinstance(dc_off, OWNDryContactEvent)
    assert dc_off.who == 25
    assert dc_off._what == 32
    assert dc_off.sensor == "3"
    assert dc_off.is_on is False

    dc_on = OWNMessage.parse("*25*31#1*33##")
    assert isinstance(dc_on, OWNDryContactEvent)
    assert dc_on.who == 25
    assert dc_on._what == 31
    assert dc_on.sensor == "3"
    assert dc_on.is_on is True


def test_physical_dimmer_progression_issue_434() -> None:
    """Verify physical wall switch dimming commands and level reporting (Issue #434).

    Confirms that physical 100-level dimmers emit Dimension 1 reports with speed
    parameter rather than Dimension 4.
    """
    # Wall switch physical interactions
    dim_up = OWNMessage.parse("*1*1000#30*14##")
    assert isinstance(dim_up, OWNLightingEvent)
    assert dim_up.who == 1
    assert dim_up._what == 1000
    assert dim_up._what_param == ["30"]
    assert dim_up.where == "14"

    dim_down = OWNMessage.parse("*1*1000#31*14##")
    assert isinstance(dim_down, OWNLightingEvent)
    assert dim_down.who == 1
    assert dim_down._what == 1000
    assert dim_down._what_param == ["31"]
    assert dim_down.where == "14"

    direct_on = OWNMessage.parse("*1*1000#1*14##")
    assert isinstance(direct_on, OWNLightingEvent)
    assert direct_on.who == 1
    assert direct_on._what == 1000
    assert direct_on._what_param == ["1"]
    assert direct_on.where == "14"

    direct_off = OWNMessage.parse("*1*1000#0*14##")
    assert isinstance(direct_off, OWNLightingEvent)
    assert direct_off.who == 1
    assert direct_off._what == 1000
    assert direct_off._what_param == ["0"]
    assert direct_off.where == "14"

    # Dimension 1 physical dimmer status reports with speed parameter
    level_30 = OWNMessage.parse("*#1*14*1*130*5##")
    assert isinstance(level_30, OWNLightingEvent)
    assert level_30.who == 1
    assert level_30.where == "14"
    assert level_30.dimension == 1
    assert level_30.brightness == 30
    assert level_30.transition == 5

    level_100 = OWNMessage.parse("*#1*14*1*200*5##")
    assert isinstance(level_100, OWNLightingEvent)
    assert level_100.who == 1
    assert level_100.where == "14"
    assert level_100.dimension == 1
    assert level_100.brightness == 100
    assert level_100.transition == 5


def test_advanced_cover_positioning_and_presets() -> None:
    """Verify advanced shutter preset commands and Dimension 10 position telemetry."""
    # Preset height command
    preset_cmd = OWNMessage.parse("*#2*31*#11#001*40##")
    assert isinstance(preset_cmd, OWNAutomationCommand)
    assert preset_cmd.who == 2
    assert preset_cmd.where == "31"
    assert preset_cmd.dimension == 11
    assert preset_cmd._dimension_param == ["001"]
    assert preset_cmd._dimension_value == ["40"]

    # Dimension 10 multi-parameter position feedback: 40% open
    dim10_pos40 = OWNMessage.parse("*#2*31*10*10*40*001*0##")
    assert isinstance(dim10_pos40, OWNAutomationEvent)
    assert dim10_pos40.who == 2
    assert dim10_pos40.where == "31"
    assert dim10_pos40.dimension == 10
    assert dim10_pos40.current_position == 40
    assert dim10_pos40._position_unknown is False

    # Dimension 10 movement: closing towards 66%
    dim10_closing = OWNMessage.parse("*#2*31*10*12*66*001*0##")
    assert isinstance(dim10_closing, OWNAutomationEvent)
    assert dim10_closing.who == 2
    assert dim10_closing.current_position == 66
    assert dim10_closing.is_closing is True
