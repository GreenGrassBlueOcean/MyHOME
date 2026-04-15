"""Tests for MyHOME HA platform entities using lightweight mocking.

Strategy: We mock the absolute minimum of the HA framework (hass object,
gateway handler, dispatcher) to test entity construction, state handling,
and command generation. This avoids requiring a full HA test harness while
still covering the entity logic.

References:
- https://developers.home-assistant.io/docs/development_testing
- https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.myhome.ownd.message import (
    OWNSoundEvent,
    OWNSoundCommand,
    OWNLightingEvent,
    OWNLightingCommand,
    OWNAutomationEvent,
    OWNAutomationCommand,
    OWNEvent,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

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


# ── MyHOMEEntity Base ─────────────────────────────────────────────────────

class TestMyHOMEEntity:
    """Test the shared base entity class."""

    def test_entity_construction(self, mock_hass, mock_gateway):
        with patch("custom_components.myhome.myhome_device.Entity.__init__", return_value=None):
            from custom_components.myhome.myhome_device import MyHOMEEntity
            entity = MyHOMEEntity(
                hass=mock_hass,
                name="Test Device",
                platform="light",
                device_id="21",
                who="1",
                where="21",
                manufacturer="BTicino",
                model="Test",
                gateway=mock_gateway,
            )
            assert entity._attr_unique_id == f"{mock_gateway.mac}-21"
            assert entity._attr_should_poll is False
            assert entity._attr_has_entity_name is True
            assert entity._manufacturer == "BTicino"

    def test_entity_default_manufacturer(self, mock_hass, mock_gateway):
        with patch("custom_components.myhome.myhome_device.Entity.__init__", return_value=None):
            from custom_components.myhome.myhome_device import MyHOMEEntity
            entity = MyHOMEEntity(
                hass=mock_hass,
                name="Test Device",
                platform="light",
                device_id="21",
                who="1",
                where="21",
                manufacturer=None,
                model="Test",
                gateway=mock_gateway,
            )
            assert entity._manufacturer == "BTicino S.p.A."

    def test_entity_device_info(self, mock_hass, mock_gateway):
        with patch("custom_components.myhome.myhome_device.Entity.__init__", return_value=None):
            from custom_components.myhome.myhome_device import MyHOMEEntity
            entity = MyHOMEEntity(
                hass=mock_hass,
                name="Test Device",
                platform="light",
                device_id="21",
                who="1",
                where="21",
                manufacturer="BTicino",
                model="F411/4",
                gateway=mock_gateway,
            )
            assert "identifiers" in entity._attr_device_info
            assert entity._attr_device_info["model"] == "F411/4"
            assert entity._attr_device_info["name"] == "Test Device"


# ── MediaPlayer Entity ─────────────────────────────────────────────────────

class TestMediaPlayerEntity:
    """Test MyHOMEMediaPlayer entity logic."""

    @pytest.fixture
    def player(self, mock_hass, mock_gateway):
        with patch("custom_components.myhome.myhome_device.Entity.__init__", return_value=None):
            from custom_components.myhome.media_player import MyHOMEMediaPlayer
            from homeassistant.components.media_player import MediaPlayerState

            p = MyHOMEMediaPlayer(
                hass=mock_hass,
                name="Audio Zone 1",
                entity_name="Audio Zone 1",
                device_id="1#16",
                who="16",
                where="1",
                manufacturer="BTicino",
                model="Audio System",
                gateway=mock_gateway,
            )
            # Override the schedule_update method to avoid HA internals
            p.async_schedule_update_ha_state = MagicMock()
            return p

    def test_initial_state(self, player):
        from homeassistant.components.media_player import MediaPlayerState
        assert player._attr_state == MediaPlayerState.OFF

    def test_source_list(self, player):
        assert len(player._attr_source_list) == 4
        assert "Source 1" in player._attr_source_list

    def test_handle_event_on(self, player):
        from homeassistant.components.media_player import MediaPlayerState
        msg = OWNEvent.parse("*16*0*1##")
        player.handle_event(msg)
        assert player._attr_state == MediaPlayerState.ON
        player.async_schedule_update_ha_state.assert_called()

    def test_handle_event_off(self, player):
        from homeassistant.components.media_player import MediaPlayerState
        msg = OWNEvent.parse("*16*10*1##")
        player.handle_event(msg)
        assert player._attr_state == MediaPlayerState.OFF

    def test_handle_global_source_event(self, player):
        msg = OWNEvent.parse("*16*0*102##")
        player.handle_global_source_event(msg)
        assert player._attr_source == "Source 2"

    def test_handle_global_source_event_not_source(self, player):
        """Non-source events should not change the source."""
        msg = OWNEvent.parse("*16*0*1##")
        player.handle_global_source_event(msg)
        assert player._attr_source is None

    @pytest.mark.asyncio
    async def test_turn_on(self, player):
        await player.async_turn_on()
        player._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, player):
        await player.async_turn_off()
        player._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_volume_up(self, player):
        await player.async_volume_up()
        player._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_volume_down(self, player):
        await player.async_volume_down()
        player._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_source(self, player):
        await player.async_select_source("Source 3")
        player._gateway_handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_source_invalid(self, player):
        """Invalid source should not send any command."""
        await player.async_select_source("Invalid Source")
        player._gateway_handler.send.assert_not_called()

    def test_handle_event_volume(self, player):
        msg = OWNEvent.parse("*#16*1*1*15##")
        player.handle_event(msg)
        assert player._attr_volume_level == pytest.approx(15 / 31.0)
        player.async_schedule_update_ha_state.assert_called()

    @pytest.mark.asyncio
    async def test_async_set_volume_level(self, player):
        await player.async_set_volume_level(0.50)
        # 0.50 * 31.0 = 15.5 -> round to 16
        args, _ = player._gateway_handler.send.call_args
        command = args[0]
        assert str(command) == "*#16*1*#1*16##"

    @pytest.mark.asyncio
    async def test_async_mute_volume(self, player):
        player._attr_volume_level = 0.50
        await player.async_mute_volume(True)
        # Should set volume to 0
        args, _ = player._gateway_handler.send.call_args
        command = args[0]
        assert str(command) == "*#16*1*#1*0##"
        assert player._attr_is_volume_muted is True
        assert player._pre_mute_volume == 0.50

        await player.async_mute_volume(False)
        # Should restore volume to 16 HW units (round(0.50 * 31))
        args, _ = player._gateway_handler.send.call_args
        command = args[0]
        assert str(command) == "*#16*1*#1*16##"
        assert player._attr_is_volume_muted is False

    @pytest.mark.asyncio
    async def test_async_update(self, player):
        await player.async_update()
        player._gateway_handler.send_status_request.assert_called_once()


# ── Platform Setup ─────────────────────────────────────────────────────────

class TestMediaPlayerPlatformSetup:
    """Test the async_setup_entry and async_unload_entry functions."""

    @pytest.mark.asyncio
    async def test_unload_entry(self):
        from custom_components.myhome.media_player import async_unload_entry
        result = await async_unload_entry(MagicMock(), MagicMock())
        assert result is True
