"""Tests for #612 / #654: MH200N authentic startup sweep, CEN pushbutton, and Scenario 1 trace.

Authentic on-wire bus trace contributed by @Depechie on #612 (comment 6046447690).
Verifies:
- Elimination of motion sensor area sweeps (#614 fix verified against physical MH200N capture)
- Deprecation-free device registry lookup via async_get_device_by_identifier
- Full handling of WHO 17 (OWNSceneEvent) firing myhome_scene_event
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
)
from OWNd.message import OWNCENEvent, OWNMessage, OWNSceneEvent

from custom_components.myhome.const import (
    CONF_SHORT_PRESS,
    DOMAIN,
)
from custom_components.myhome.gateway import MyHOMEGatewayHandler
from custom_components.myhome.gateway_events import GatewayEventDispatcher

TRACES_DIR = Path(__file__).resolve().parent / "fixtures" / "traces" / "issue_612"
TRACE_FILE = TRACES_DIR / "myhome_trace_MH200N_startup_cen_scene_2026-10-07T20-38-24.json"


@pytest.fixture
def gateway_handler() -> MyHOMEGatewayHandler:
    entry = MagicMock()
    entry.entry_id = "entry_612"
    entry.data = {
        CONF_HOST: "10.10.13.148",
        CONF_PORT: 20000,
        CONF_PASSWORD: "open",
        CONF_MAC: "00:03:50:01:75:8b",
    }
    hass = MagicMock()
    hass.data = {}
    handler = MyHOMEGatewayHandler(hass, entry)
    handler.device_registry_id = "gateway_device_612"
    return handler


def test_trace_file_present_and_has_trailing_newline() -> None:
    """Ensure the trace fixture file exists, contains frames, and ends with a trailing newline."""
    assert TRACE_FILE.is_file(), f"Missing trace fixture: {TRACE_FILE}"
    raw_text = TRACE_FILE.read_text(encoding="utf-8")
    assert raw_text.endswith("\n"), "Trace file missing trailing newline"
    data = json.loads(raw_text)
    assert len(data.get("frames", [])) == 193


def test_trace_contains_no_motion_sensor_area_sweeps() -> None:
    """Empirically verify PR #614: No motion sensor area sweeps (*#1*00## or *#1*1##) exist in the trace."""
    data = json.loads(TRACE_FILE.read_text(encoding="utf-8"))
    frames = [f["raw"] for f in data["frames"]]

    # Verify no area sweep frames are emitted
    assert "*#1*00##" not in frames
    assert "*#1*1##" not in frames
    assert "*#1*2##" not in frames

    # Verify initial discovery sweep *#1*0## is present
    initial_sweeps = [f for f in frames if f == "*#1*0##"]
    assert len(initial_sweeps) == 1


def test_trace_cen_and_scene_events_parse() -> None:
    """Validate that the trace's CEN and Scene frames parse with accurate properties."""
    cen_frame = "*15*03*61##"
    scene_start_frame = "*17*1*1##"
    scene_stop_frame = "*17*2*1##"

    cen_msg = OWNMessage.parse(cen_frame)
    assert isinstance(cen_msg, OWNCENEvent)
    assert cen_msg.object == "61"
    assert cen_msg.push_button == 3
    assert cen_msg.is_pressed is True

    scene_start = OWNMessage.parse(scene_start_frame)
    assert isinstance(scene_start, OWNSceneEvent)
    assert scene_start.scenario == "1"
    assert scene_start.state == 1
    assert scene_start.is_on is True
    assert scene_start.is_enabled is None
    assert scene_start.human_readable_log == "Scene 1 is started."

    scene_stop = OWNMessage.parse(scene_stop_frame)
    assert isinstance(scene_stop, OWNSceneEvent)
    assert scene_stop.scenario == "1"
    assert scene_stop.state == 2
    assert scene_stop.is_on is False
    assert scene_stop.is_enabled is None
    assert scene_stop.human_readable_log == "Scene 1 is stopped."


@pytest.mark.asyncio
async def test_trace_replay_cen_and_scene_events(gateway_handler: MyHOMEGatewayHandler) -> None:
    """Replay authentic trace and assert CEN and Scene events are dispatched with deprecation-free lookup."""
    data = json.loads(TRACE_FILE.read_text(encoding="utf-8"))
    raw_frames = [f["raw"] for f in data["frames"]]
    messages = [OWNMessage.parse(f) for f in raw_frames]

    mock_dr = MagicMock()
    mock_dr.async_get_device.return_value = None
    mock_dr.async_get_device_by_identifier.return_value = None

    with (
        patch("custom_components.myhome.gateway.OWNEventSession") as session_class,
        patch("homeassistant.helpers.device_registry.async_get", return_value=mock_dr),
    ):
        session = MagicMock()
        session.connect = AsyncMock(return_value={"Success": True})
        session.get_next = AsyncMock(side_effect=[*messages, asyncio.CancelledError()])
        session_class.return_value = session
        gateway_handler.send_status_request = AsyncMock()

        with patch.object(gateway_handler.hass.bus, "async_fire") as fire:
            try:
                await gateway_handler.listening_loop()
            except asyncio.CancelledError:
                pass

    # 1. Assert myhome_cen_event was fired
    fire.assert_any_call(
        "myhome_cen_event",
        {
            "object": 61,
            "pushbutton": 3,
            "event": CONF_SHORT_PRESS,
            "where": "61",
            "gateway_mac": gateway_handler.mac,
            "entry_id": "entry_612",
        },
    )

    # 2. Assert async_get_device_by_identifier was called for CEN unit 61 (no deprecation warning)
    mock_dr.async_get_device_by_identifier.assert_any_call(
        (DOMAIN, f"{gateway_handler.mac}-15-61"),
        config_entry_id="entry_612",
    )
    # Ensure legacy deprecated async_get_device was NOT called
    mock_dr.async_get_device.assert_not_called()

    # 3. Assert CEN unit 61 was registered in device registry
    mock_dr.async_get_or_create.assert_called_once()
    kwargs = mock_dr.async_get_or_create.call_args.kwargs
    assert kwargs["name"] == "CEN Unit 61"
    assert kwargs["identifiers"] == {(DOMAIN, f"{gateway_handler.mac}-15-61")}
    assert kwargs["via_device_id"] == "gateway_device_612"

    # 4. Assert myhome_scene_event was fired for both Scenario 1 start and stop
    fire.assert_any_call(
        "myhome_scene_event",
        {
            "scenario": 1,
            "where": "1",
            "state": 1,
            "is_on": True,
            "is_enabled": None,
            "gateway_mac": gateway_handler.mac,
            "entry_id": "entry_612",
        },
    )
    fire.assert_any_call(
        "myhome_scene_event",
        {
            "scenario": 1,
            "where": "1",
            "state": 2,
            "is_on": False,
            "is_enabled": None,
            "gateway_mac": gateway_handler.mac,
            "entry_id": "entry_612",
        },
    )


@pytest.mark.asyncio
async def test_scene_event_enabled_and_disabled_states(gateway_handler: MyHOMEGatewayHandler) -> None:
    """Test scenario enable (3) and disable (4) states."""
    scene_enabled = OWNMessage.parse("*17*3*2##")
    scene_disabled = OWNMessage.parse("*17*4*2##")

    assert isinstance(scene_enabled, OWNSceneEvent)
    assert scene_enabled.state == 3
    assert scene_enabled.is_enabled is True
    assert scene_enabled.is_on is None
    assert scene_enabled.human_readable_log == "Scene 2 is enabled."

    assert isinstance(scene_disabled, OWNSceneEvent)
    assert scene_disabled.state == 4
    assert scene_disabled.is_enabled is False
    assert scene_disabled.is_on is None
    assert scene_disabled.human_readable_log == "Scene 2 is disabled."

    with patch.object(gateway_handler.hass.bus, "async_fire") as fire:
        await gateway_handler._event_dispatcher.process_message(scene_enabled)
        await gateway_handler._event_dispatcher.process_message(scene_disabled)

    fire.assert_any_call(
        "myhome_scene_event",
        {
            "scenario": 2,
            "where": "2",
            "state": 3,
            "is_on": None,
            "is_enabled": True,
            "gateway_mac": gateway_handler.mac,
            "entry_id": "entry_612",
        },
    )
    fire.assert_any_call(
        "myhome_scene_event",
        {
            "scenario": 2,
            "where": "2",
            "state": 4,
            "is_on": None,
            "is_enabled": False,
            "gateway_mac": gateway_handler.mac,
            "entry_id": "entry_612",
        },
    )


@pytest.mark.asyncio
async def test_scene_event_non_integer_scenario(gateway_handler: MyHOMEGatewayHandler) -> None:
    """Test scenario event with non-integer scenario identifier degrades gracefully."""
    mock_scene = MagicMock(spec=OWNSceneEvent)
    mock_scene.scenario = "A1"
    mock_scene.where = "A1"
    mock_scene.state = 1
    mock_scene.is_on = True
    mock_scene.is_enabled = None
    mock_scene.human_readable_log = "Scene A1 is started."

    with patch.object(gateway_handler.hass.bus, "async_fire") as fire:
        await gateway_handler._event_dispatcher.process_message(mock_scene)

    fire.assert_called_once_with(
        "myhome_scene_event",
        {
            "scenario": "A1",
            "where": "A1",
            "state": 1,
            "is_on": True,
            "is_enabled": None,
            "gateway_mac": gateway_handler.mac,
            "entry_id": "entry_612",
        },
    )

@pytest.mark.asyncio
async def test_scene_event_standby_failover() -> None:
    """Test standby gateway failover behavior for scene events."""
    mock_handler = MagicMock()
    mock_handler.is_standby = True
    mock_handler.is_secondary = False
    mock_handler.generate_events = False
    mock_handler.mac = "00:03:50:01:75:8b"
    mock_handler.log_id = "[Standby GW]"
    mock_handler.config_entry.entry_id = "standby_entry_id"
    primary_gw = MagicMock()
    primary_gw.mac = "00:03:50:99:99:99"
    primary_gw.config_entry.entry_id = "primary_entry_id"
    primary_gw.is_connected = False
    mock_handler._get_primary_gateway.return_value = primary_gw
    mock_handler._profile_supports_who.return_value = True

    dispatcher = GatewayEventDispatcher(mock_handler)
    scene_msg = OWNMessage.parse("*17*1*5##")

    with patch.object(mock_handler.hass.bus, "async_fire") as fire:
        # Primary is offline and profile supports WHO 17 -> failover active, uses primary MAC/entry
        await dispatcher.process_message(scene_msg)

    fire.assert_called_once_with(
        "myhome_scene_event",
        {
            "scenario": 5,
            "where": "5",
            "state": 1,
            "is_on": True,
            "is_enabled": None,
            "gateway_mac": "00:03:50:99:99:99",
            "entry_id": "primary_entry_id",
        },
    )

    # Primary is online -> standby does not fire
    primary_gw.is_connected = True
    fire.reset_mock()
    await dispatcher.process_message(scene_msg)
    fire.assert_not_called()


@pytest.mark.asyncio
async def test_scene_event_delegated_away() -> None:
    """Test that when WHO 17 is delegated away, scene events are not fired."""
    mock_handler = MagicMock()
    mock_handler.is_standby = False
    mock_handler.is_secondary = False
    mock_handler.delegated_away_whos = {17}
    dispatcher = GatewayEventDispatcher(mock_handler)
    scene_msg = OWNMessage.parse("*17*1*1##")

    with patch.object(mock_handler.hass.bus, "async_fire") as fire:
        await dispatcher.process_message(scene_msg)

    fire.assert_not_called()


@pytest.mark.asyncio
async def test_scene_event_without_config_entry(gateway_handler: MyHOMEGatewayHandler) -> None:
    """Test scene event handling when gateway_handler has no config_entry."""
    gateway_handler.config_entry = None
    scene_msg = OWNMessage.parse("*17*1*1##")

    with patch.object(gateway_handler.hass.bus, "async_fire") as fire:
        await gateway_handler._event_dispatcher.process_message(scene_msg)

    fire.assert_called_once_with(
        "myhome_scene_event",
        {
            "scenario": 1,
            "where": "1",
            "state": 1,
            "is_on": True,
            "is_enabled": None,
            "gateway_mac": gateway_handler.mac,
        },
    )


def test_cen_device_registry_fallback_without_async_get_device_by_identifier(
    gateway_handler: MyHOMEGatewayHandler,
) -> None:
    """Ensure older core versions without async_get_device_by_identifier fallback to async_get_device."""

    class LegacyRegistry:
        def __init__(self) -> None:
            self.async_get_device = MagicMock(return_value=None)
            self.async_get_or_create = MagicMock()

    legacy_dr = LegacyRegistry()
    assert not hasattr(legacy_dr, "async_get_device_by_identifier")

    with patch("homeassistant.helpers.device_registry.async_get", return_value=legacy_dr):
        gateway_handler._ensure_cen_device(15, "0512")

    legacy_dr.async_get_device.assert_called()
    legacy_dr.async_get_or_create.assert_called_once()

