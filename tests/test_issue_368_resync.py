"""Test issue 368 debounced resync."""

from unittest.mock import AsyncMock, MagicMock, patch

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.core import HomeAssistant
from OWNd.message import OWNLightingEvent
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.myhome.const import CONF_BROADCAST_RESYNC, area_of_where
from custom_components.myhome.gateway import MyHOMEGatewayHandler


def test_area_of_where():
    """Test area_of_where logic."""
    assert area_of_where("12") == "1"
    assert area_of_where("0115") == "1"
    assert area_of_where("0015") == "00"
    assert area_of_where("1003") == "100"
    assert area_of_where("invalid") is None
    assert area_of_where(None) is None


@pytest.fixture
def mock_gateway_handler(hass: HomeAssistant):
    """Fixture to provide a mocked gateway handler."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {}
    entry.options = {CONF_BROADCAST_RESYNC: True}

    with patch("custom_components.myhome.gateway.OWNGateway"):
        handler = MyHOMEGatewayHandler(hass, entry, generate_events=False)
        handler.gateway.mac = "00:00:00:00:00:00"
        handler.send_status_request = AsyncMock()
        return handler


@pytest.mark.asyncio
async def test_resync_group(hass: HomeAssistant, mock_gateway_handler: MyHOMEGatewayHandler):
    """Test group frame debouncing."""
    msg = MagicMock(spec=OWNLightingEvent)
    msg.is_translation = False
    msg.is_group = True
    msg.group = "6"
    msg.is_area = False
    msg.is_general = False

    await mock_gateway_handler._process_message(msg)

    # Fast forward time to trigger timer
    async_fire_time_changed(hass, dt_util.utcnow() + dt_util.dt.timedelta(seconds=1))
    await hass.async_block_till_done()

    mock_gateway_handler.send_status_request.assert_called_once()
    arg = mock_gateway_handler.send_status_request.call_args[0][0]
    assert arg.where == "#6"


@pytest.mark.asyncio
async def test_resync_group_with_echo(hass: HomeAssistant, mock_gateway_handler: MyHOMEGatewayHandler):
    """Test group frame followed by point frame prevents resync."""
    msg_grp = MagicMock(spec=OWNLightingEvent)
    msg_grp.is_translation = False
    msg_grp.is_group = True
    msg_grp.group = "6"
    msg_grp.is_area = False
    msg_grp.is_general = False

    await mock_gateway_handler._process_message(msg_grp)

    # A point frame comes in
    msg_pt = MagicMock(spec=OWNLightingEvent)
    msg_pt.is_translation = False
    msg_pt.is_group = False
    msg_pt.is_area = False
    msg_pt.is_general = False

    await mock_gateway_handler._process_message(msg_pt)

    async_fire_time_changed(hass, dt_util.utcnow() + dt_util.dt.timedelta(seconds=1))
    await hass.async_block_till_done()

    # The sweep should have been aborted
    mock_gateway_handler.send_status_request.assert_not_called()


@pytest.mark.asyncio
async def test_resync_general(hass: HomeAssistant, mock_gateway_handler: MyHOMEGatewayHandler):
    """Test general sweep requests."""
    msg = MagicMock(spec=OWNLightingEvent)
    msg.is_translation = False
    msg.is_group = False
    msg.is_area = False
    msg.is_general = True

    with patch.object(mock_gateway_handler, "_known_light_areas", return_value=["1", "00", "100"]):
        await mock_gateway_handler._process_message(msg)

        async_fire_time_changed(hass, dt_util.utcnow() + dt_util.dt.timedelta(seconds=1))
        await hass.async_block_till_done()

        assert mock_gateway_handler.send_status_request.call_count == 3
        wheres = [call[0][0].where for call in mock_gateway_handler.send_status_request.call_args_list]
        assert "1" in wheres
        assert "00" in wheres
        assert "100" in wheres


@pytest.mark.asyncio
async def test_resync_off(hass: HomeAssistant, mock_gateway_handler: MyHOMEGatewayHandler):
    """Test resync off."""
    mock_gateway_handler.broadcast_resync = False

    msg = MagicMock(spec=OWNLightingEvent)
    msg.is_translation = False
    msg.is_group = True
    msg.group = "6"
    msg.is_area = False
    msg.is_general = False

    await mock_gateway_handler._process_message(msg)

    async_fire_time_changed(hass, dt_util.utcnow() + dt_util.dt.timedelta(seconds=1))
    await hass.async_block_till_done()

    mock_gateway_handler.send_status_request.assert_not_called()

