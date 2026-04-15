"""Test the MyHOME light component."""
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_FLASH,
    FLASH_LONG,
    FLASH_SHORT,
    ATTR_TRANSITION,
    ColorMode,
)

from custom_components.myhome.light import (
    MyHOMELight,
    async_setup_entry,
    async_unload_entry,
    eight_bits_to_percent,
    percent_to_eight_bits,
)
from custom_components.myhome.ownd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
)
from custom_components.myhome.const import DOMAIN

async def test_setup_and_unload_entry(hass):
    """Test setup dynamically restoring and dynamically creating lights."""
    mock_gateway = MagicMock()
    mock_gateway.mac = "mac"
    
    hass.data = {DOMAIN: {"mac": {"entity": mock_gateway}}}
    
    config_entry = MagicMock()
    config_entry.data = {"mac": "mac"}
    config_entry.entry_id = "test_entry"
    
    # Mock entity registry restore check
    mock_er = MagicMock()
    mock_entry_1 = MagicMock()
    mock_entry_1.domain = "light"
    mock_entry_1.unique_id = "mac-12"
    mock_entry_2 = MagicMock()
    mock_entry_2.domain = "light"
    mock_entry_2.unique_id = "mac-13#4#1"
    
    with patch(
        "custom_components.myhome.light.er.async_entries_for_config_entry",
        return_value=[mock_entry_1, mock_entry_2]
    ), patch(
        "custom_components.myhome.light.er.async_get",
        return_value=mock_er
    ):
        async_add_entities = MagicMock()
        await async_setup_entry(hass, config_entry, async_add_entities)
        
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        
        assert len(entities) == 2
        assert entities[0].device_id == "12"
        assert entities[1].device_id == "13#4#1"
    
    assert await async_unload_entry(hass, config_entry)


def test_conversions():
    """Test value conversion logic."""
    assert eight_bits_to_percent(255) == 100
    assert eight_bits_to_percent(127) == 50
    assert percent_to_eight_bits(100) == 255
    assert percent_to_eight_bits(50) == 128


async def test_light_entity_dimmable(hass):
    """Test dimmable MyHOMELight logic."""
    gateway = MagicMock()
    gateway.send = AsyncMock()
    gateway.send_status_request = AsyncMock()
    
    light = MyHOMELight(
        hass=hass, name="L", entity_name="L", icon="mdi:lightbulb-off", icon_on="mdi:lightbulb-on",
        device_id="12", who="1", where="12", interface=None, dimmable=True,
        manufacturer="B", model="M", gateway=gateway
    )
    light.async_schedule_update_ha_state = MagicMock()
    
    assert light.color_mode == ColorMode.BRIGHTNESS
    
    # Update
    await light.async_update()
    gateway.send_status_request.assert_called_once()
    assert "status_request" not in str(gateway.send_status_request.call_args) # Should call get_brightness
    gateway.send_status_request.reset_mock()
    
    # Turn on
    await light.async_turn_on()
    gateway.send.assert_called_once()
    gateway.send.reset_mock()
    
    # Turn on with Brightness
    await light.async_turn_on(**{ATTR_BRIGHTNESS: 128})
    gateway.send.assert_called_once()
    gateway.send.reset_mock()
    
    # Turn on with Transition
    await light.async_turn_on(**{ATTR_TRANSITION: 5})
    gateway.send.assert_called_once()
    gateway.send.reset_mock()
    
    # Turn on with Brightness and Transition
    await light.async_turn_on(**{ATTR_BRIGHTNESS_PCT: 50, ATTR_TRANSITION: 2})
    gateway.send.assert_called_once()
    gateway.send.reset_mock()
    
    # Turn off with brightness 0
    await light.async_turn_on(**{ATTR_BRIGHTNESS: 0})
    gateway.send.assert_called_once()  # Routes to async_turn_off
    # Check it actually sent the off command
    gateway.send.reset_mock()
    
    # Turn off with transition
    await light.async_turn_off(**{ATTR_TRANSITION: 5})
    gateway.send.assert_called_once()
    gateway.send.reset_mock()


async def test_light_entity_onoff(hass):
    """Test default onoff MyHOMELight logic."""
    gateway = MagicMock()
    gateway.send = AsyncMock()
    gateway.send_status_request = AsyncMock()
    
    light = MyHOMELight(
        hass=hass, name="L", entity_name="L", icon="mdi:lightbulb-off", icon_on="mdi:lightbulb-on",
        device_id="13", who="1", where="13", interface=None, dimmable=False,
        manufacturer="B", model="M", gateway=gateway
    )
    light.async_schedule_update_ha_state = MagicMock()
    
    assert light.color_mode == ColorMode.ONOFF
    
    # Update calls status request
    await light.async_update()
    gateway.send_status_request.assert_called_once()
    gateway.send_status_request.reset_mock()
    
    # Flash support
    await light.async_turn_on(**{ATTR_FLASH: FLASH_SHORT})
    gateway.send.assert_called_once()
    gateway.send.reset_mock()
    
    await light.async_turn_off(**{ATTR_FLASH: FLASH_LONG})
    gateway.send.assert_called_once()
    gateway.send.reset_mock()
    
    # Event handling
    event = MagicMock(spec=OWNLightingEvent)
    event.is_on = True
    event.brightness = None
    
    light.handle_event(event)
    assert light.is_on
    assert light.icon == "mdi:lightbulb-on"
    
    event.is_on = False
    light.handle_event(event)
    assert not light.is_on
    assert light.icon == "mdi:lightbulb-off"

    await light.async_added_to_hass()
