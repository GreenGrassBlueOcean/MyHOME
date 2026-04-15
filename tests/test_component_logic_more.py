"""Tests for MyHOME HA platform entities handle_event methods using lightweight mocking."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.myhome.ownd.message import (
    OWNEvent
)

@pytest.fixture
def mock_hass():
    """Create a minimal mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.async_create_task = MagicMock()
    return hass

@pytest.fixture
def mock_gateway():
    """Create a minimal mock gateway handler."""
    gw = MagicMock()
    gw.mac = "00:03:50:00:12:34"
    gw.unique_id = "00:03:50:00:12:34"
    gw.log_id = "[Test Gateway]"
    gw.send = AsyncMock()
    gw.send_status_request = AsyncMock()
    return gw

@pytest.fixture
def mock_entity_base_init():
    with patch("custom_components.myhome.myhome_device.Entity.__init__", return_value=None):
        yield

# ── Light Entity ─────────────────────────────────────────────────────────

class TestLightEntity:

    @pytest.fixture
    def light(self, mock_hass, mock_gateway, mock_entity_base_init):
        from custom_components.myhome.light import MyHOMELight
        l = MyHOMELight(
            hass=mock_hass,
            name="Light 1",
            entity_name="Light 1",
            icon="mdi:lightbulb",
            icon_on="mdi:lightbulb-on",
            device_id="1#21",
            who="1",
            where="21",
            interface="l",
            dimmable=False,
            manufacturer="BTicino",
            model="Dimmer",
            gateway=mock_gateway,
        )
        l.async_schedule_update_ha_state = MagicMock()
        return l

    def test_handle_event_on(self, light):
        msg = OWNEvent.parse("*1*1*21##")
        light.handle_event(msg)
        assert light._attr_is_on is True
        light.async_schedule_update_ha_state.assert_called()

    def test_handle_event_off(self, light):
        msg = OWNEvent.parse("*1*0*21##")
        light.handle_event(msg)
        assert light._attr_is_on is False

    @pytest.mark.asyncio
    async def test_async_turn_on(self, light):
        await light.async_turn_on()
        light._gateway_handler.send.assert_called_once()
        assert "*1*1*21#4#l##" in str(light._gateway_handler.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_async_turn_off(self, light):
        await light.async_turn_off()
        light._gateway_handler.send.assert_called_once()
        assert "*1*0*21#4#l##" == str(light._gateway_handler.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_async_update(self, light):
        await light.async_update()
        light._gateway_handler.send_status_request.assert_called()

# ── Switch Entity ─────────────────────────────────────────────────────────

class TestSwitchEntity:

    @pytest.fixture
    def switch(self, mock_hass, mock_gateway, mock_entity_base_init):
        from custom_components.myhome.switch import MyHOMESwitch
        s = MyHOMESwitch(
            hass=mock_hass,
            name="Switch 1",
            entity_name="Switch 1",
            device_id="1#22",
            who="1",
            where="22",
            interface="s",
            device_class="switch",
            icon="mdi:flash",
            icon_on="mdi:flash",
            manufacturer="BTicino",
            model="Relay",
            gateway=mock_gateway,
        )
        s.async_schedule_update_ha_state = MagicMock()
        return s

    def test_handle_event_on(self, switch):
        msg = OWNEvent.parse("*1*1*22##")
        switch.handle_event(msg)
        assert switch._attr_is_on is True
        switch.async_schedule_update_ha_state.assert_called()

    def test_handle_event_off(self, switch):
        msg = OWNEvent.parse("*1*0*22##")
        switch.handle_event(msg)
        assert switch._attr_is_on is False

    @pytest.mark.asyncio
    async def test_async_turn_on(self, switch):
        await switch.async_turn_on()
        switch._gateway_handler.send.assert_called_once()
        assert "*1*1*22#4#s##" == str(switch._gateway_handler.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_async_turn_off(self, switch):
        await switch.async_turn_off()
        switch._gateway_handler.send.assert_called_once()
        assert "*1*0*22#4#s##" == str(switch._gateway_handler.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_async_update(self, switch):
        await switch.async_update()
        switch._gateway_handler.send_status_request.assert_called()

# ── Cover Entity ─────────────────────────────────────────────────────────

class TestCoverEntity:

    @pytest.fixture
    def cover(self, mock_hass, mock_gateway, mock_entity_base_init):
        from custom_components.myhome.cover import MyHOMECover
        c = MyHOMECover(
            hass=mock_hass,
            name="Cover 1",
            entity_name="Cover 1",
            device_id="2#23",
            who="2",
            where="23",
            interface="c",
            advanced=False,
            manufacturer="BTicino",
            model="Blind Actuator",
            gateway=mock_gateway,
        )
        c.async_schedule_update_ha_state = MagicMock()
        return c

    def test_handle_event_up(self, cover):
        msg = OWNEvent.parse("*2*1*23##")
        cover.handle_event(msg)
        assert cover._attr_is_opening is True

    def test_handle_event_down(self, cover):
        msg = OWNEvent.parse("*2*2*23##")
        cover.handle_event(msg)
        assert cover._attr_is_closing is True

    def test_handle_event_stop(self, cover):
        msg = OWNEvent.parse("*2*0*23##")
        cover.handle_event(msg)
        assert cover._attr_is_opening is False
        assert cover._attr_is_closing is False

    @pytest.mark.asyncio
    async def test_async_open_cover(self, cover):
        await cover.async_open_cover()
        cover._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_close_cover(self, cover):
        await cover.async_close_cover()
        cover._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_stop_cover(self, cover):
        await cover.async_stop_cover()
        cover._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update(self, cover):
        await cover.async_update()
        cover._gateway_handler.send_status_request.assert_called()

# ── Button Entities ────────────────────────────────────────────────────────

class TestButtonEntity:

    @pytest.fixture
    def enable_button(self, mock_hass, mock_gateway, mock_entity_base_init):
        from custom_components.myhome.button import EnableCommandButtonEntity
        b = EnableCommandButtonEntity(
            hass=mock_hass,
            platform="button",
            name="Enable Button",
            device_id="25#24",
            who="25",
            where="24",
            interface="b",
            manufacturer="B",
            model="M",
            gateway=mock_gateway,
        )
        b.async_schedule_update_ha_state = MagicMock()
        return b

    @pytest.mark.asyncio
    async def test_async_press_enable(self, enable_button):
        await enable_button.async_press()
        enable_button._gateway_handler.send.assert_called_once()
        assert "*14*1*24#4#b##" in str(enable_button._gateway_handler.send.call_args[0][0])
