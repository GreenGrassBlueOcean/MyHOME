import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from homeassistant.core import HomeAssistant

from custom_components.myhome.gateway import MyHOMEGatewayHandler
from custom_components.myhome.const import (
    DOMAIN,
    CONF_SHORT_PRESS,
    CONF_SHORT_RELEASE,
    CONF_LONG_PRESS,
    CONF_LONG_RELEASE,
    CONF_SSDP_LOCATION,
    CONF_SSDP_ST,
    CONF_DEVICE_TYPE,
    CONF_MANUFACTURER,
    CONF_MANUFACTURER_URL,
    CONF_FIRMWARE,
    CONF_UDN,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    CONF_NAME,
    CONF_MAC,
    CONF_FRIENDLY_NAME,
)
from custom_components.myhome.ownd.message import (
    OWNLightingEvent,
    OWNAutomationEvent,
    OWNHeatingCommand,
    OWNCENPlusEvent,
    OWNCENEvent,
    OWNMessage,
    OWNCommand,
)

@pytest.fixture
def mock_config_entry():
    entry = MagicMock()
    entry.data = {
        CONF_HOST: "192.168.1.5",
        CONF_PORT: 20000,
        CONF_PASSWORD: "open",
        CONF_SSDP_LOCATION: "",
        CONF_SSDP_ST: "",
        CONF_DEVICE_TYPE: "Gateway",
        CONF_FRIENDLY_NAME: "GW",
        CONF_MANUFACTURER: "Bticino",
        CONF_MANUFACTURER_URL: "",
        CONF_NAME: "MYHOME",
        CONF_FIRMWARE: "1.0",
        CONF_MAC: "00:11:22:33:44:55",
        CONF_UDN: "1234",
    }
    return entry

@pytest.fixture
def gateway_handler(mock_config_entry):
    mock_hass = MagicMock(spec=HomeAssistant)
    handler = MyHOMEGatewayHandler(mock_hass, mock_config_entry)
    # The bus and async_fire are automatically MagicMocks now.
    return handler

@pytest.mark.asyncio
async def test_listening_loop_lighting(gateway_handler):
    with patch("custom_components.myhome.gateway.OWNEventSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.connect = AsyncMock()
        # Mock what messages the loop gets sequence
        mock_session.get_next = AsyncMock()
        
        # We need three specific lighting events to trigger general, area, group
        msg_gen = MagicMock(spec=OWNLightingEvent)
        msg_gen.is_translation = False
        msg_gen.is_general = True
        msg_gen.is_on = True
        msg_gen.human_readable_log = "L Gen"

        msg_area = MagicMock(spec=OWNLightingEvent)
        msg_area.is_translation = False
        msg_area.is_general = False
        msg_area.is_area = True
        msg_area.is_on = False
        msg_area.area = "1"
        msg_area.human_readable_log = "L Area"

        msg_group = MagicMock(spec=OWNLightingEvent)
        msg_group.is_translation = False
        msg_group.is_general = False
        msg_group.is_area = False
        msg_group.is_group = True
        msg_group.is_on = True
        msg_group.group = "5"
        msg_group.human_readable_log = "L Grp"

        # End sequence with a generic termination so the loop exits
        mock_session.get_next.side_effect = [
            msg_gen,
            msg_area,
            msg_group,
            asyncio.CancelledError() # Breaks the infinite loop gracefully
        ]
        mock_session_class.return_value = mock_session

        mock_send_req = AsyncMock()
        gateway_handler.send_status_request = mock_send_req

        try:
            await gateway_handler.listening_loop()
        except asyncio.CancelledError:
            pass

        # Verify Event Bus fires
        assert gateway_handler.hass.bus.async_fire.call_count >= 3
        # Genernal Light dispatch
        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_general_light_event", {"message": str(msg_gen), "event": "on"})
        # Area Light dispatch
        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_area_light_event", {"message": str(msg_area), "area": "1", "event": "off"})
        # Group Light dispatch
        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_group_light_event", {"message": str(msg_group), "group": "5", "event": "on"})


@pytest.mark.asyncio
async def test_listening_loop_automation(gateway_handler):
    with patch("custom_components.myhome.gateway.OWNEventSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.connect = AsyncMock()
        mock_session.get_next = AsyncMock()
        
        msg_gen = MagicMock(spec=OWNAutomationEvent)
        msg_gen.is_translation = False
        msg_gen.is_general = True
        msg_gen.is_opening = True
        msg_gen.is_closing = False
        msg_gen.human_readable_log = "A Gen"

        msg_area = MagicMock(spec=OWNAutomationEvent)
        msg_area.is_translation = False
        msg_area.is_general = False
        msg_area.is_area = True
        msg_area.is_opening = False
        msg_area.is_closing = True
        msg_area.area = "2"
        msg_area.human_readable_log = "A Area"

        msg_group = MagicMock(spec=OWNAutomationEvent)
        msg_group.is_translation = False
        msg_group.is_general = False
        msg_group.is_area = False
        msg_group.is_group = True
        msg_group.is_opening = False
        msg_group.is_closing = False # triggers "stop"
        msg_group.group = "6"
        msg_group.human_readable_log = "A Grp"

        mock_session.get_next.side_effect = [
            msg_gen,
            msg_area,
            msg_group,
            asyncio.CancelledError()
        ]
        mock_session_class.return_value = mock_session

        gateway_handler.send_status_request = AsyncMock()

        try:
            await gateway_handler.listening_loop()
        except asyncio.CancelledError:
            pass

        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_general_automation_event", {"message": str(msg_gen), "event": "open"})
        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_area_automation_event", {"message": str(msg_area), "area": "2", "event": "close"})
        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_group_automation_event", {"message": str(msg_group), "group": "6", "event": "stop"})


@pytest.mark.asyncio
async def test_listening_loop_other_events(gateway_handler):
    with patch("custom_components.myhome.gateway.OWNEventSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.connect = AsyncMock()
        mock_session.get_next = AsyncMock()
        
        msg_heat = MagicMock(spec=OWNHeatingCommand)
        msg_heat.dimension = 14
        msg_heat.where = "#4"
        
        msg_cenplus = MagicMock(spec=OWNCENPlusEvent)
        msg_cenplus.is_short_pressed = True
        msg_cenplus.object = "1"
        msg_cenplus.push_button = "2"
        msg_cenplus.human_readable_log = "CP"

        msg_cen = MagicMock(spec=OWNCENEvent)
        msg_cen.is_held = True
        msg_cen.is_pressed = False
        msg_cen.object = "3"
        msg_cen.push_button = "4"
        msg_cen.human_readable_log = "C"

        mock_session.get_next.side_effect = [
            msg_heat,
            msg_cenplus,
            msg_cen,
            asyncio.CancelledError()
        ]
        mock_session_class.return_value = mock_session

        gateway_handler.send_status_request = AsyncMock()

        try:
            await gateway_handler.listening_loop()
        except asyncio.CancelledError:
            pass

        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_cenplus_event", {"object": 1, "pushbutton": 2, "event": CONF_SHORT_PRESS})
        gateway_handler.hass.bus.async_fire.assert_any_call("myhome_cen_event", {"object": 3, "pushbutton": 4, "event": CONF_LONG_PRESS})


@pytest.mark.asyncio
async def test_sending_loop(gateway_handler):
    with patch("custom_components.myhome.gateway.OWNCommandSession") as mock_cmd_class:
        mock_cmd_session = MagicMock()
        mock_cmd_session.connect = AsyncMock()
        mock_cmd_session.send = AsyncMock()
        mock_cmd_session.close = AsyncMock()
        mock_cmd_class.return_value = mock_cmd_session

        gateway_handler.sending_workers = [AsyncMock()]
        
        # Add a task
        await gateway_handler.send_buffer.put({"message": "mock_msg", "is_status_request": False})

        # Inject a task to kill the loop cleanly
        async def kill_loop():
            gateway_handler._terminate_sender = True
            return {"message": "kill", "is_status_request": False}

        # Override get to yield one message then kill loop
        gateway_handler.send_buffer.get = AsyncMock(side_effect=[
            {"message": "msg1", "is_status_request": False},
            {"message": "msg2", "is_status_request": True},
        ])

        # Hook to end the while loop manually without causing infinite hangs
        def mock_send(message, is_status_request):
            if message == "msg2":
                gateway_handler._terminate_sender = True

        mock_cmd_session.send.side_effect = mock_send

        await gateway_handler.sending_loop(0)

        assert mock_cmd_session.send.call_count == 2
        mock_cmd_session.close.assert_called_once()
