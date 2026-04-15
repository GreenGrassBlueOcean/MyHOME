"""Test the MyHOME button component."""
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.myhome.button import (
    DisableCommandButtonEntity,
    EnableCommandButtonEntity,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.myhome.const import DOMAIN

async def test_setup_and_unload_entry(hass):
    """Test setup and unload of the button platform."""
    mock_gateway = MagicMock()
    mock_gateway.mac = "mac"
    
    hass.data = {
        DOMAIN: {
            "mac": {
                "platforms": {
                    "button": {
                        "device_1": {
                            "who": "1",
                            "where": "12",
                            "name": "Light 12",
                            "manufacturer": "BTicino",
                            "device_model": "F411",
                            "entities": {}
                        },
                        "device_2": {
                            "who": "1",
                            "where": "13",
                            "interface": "2", # test with bus interface
                            "name": "Light 13",
                            "manufacturer": "BTicino",
                            "device_model": "F411",
                            "entities": {}
                        }
                    }
                },
                "entity": mock_gateway,
            }
        }
    }
    
    config_entry = MagicMock()
    config_entry.data = {"mac": "mac"}
    
    async_add_entities = MagicMock()
    await async_setup_entry(hass, config_entry, async_add_entities)
    
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    
    # Each device gets 1 disable and 1 enable button
    assert len(entities) == 4
    
    # Test unload
    await async_unload_entry(hass, config_entry)
    assert "device_1" not in hass.data[DOMAIN]["mac"]["platforms"]["button"]
    assert "device_2" not in hass.data[DOMAIN]["mac"]["platforms"]["button"]


async def test_disable_button_entity(hass):
    """Test DisableCommandButtonEntity logic."""
    mock_gateway = MagicMock()
    mock_gateway.mac = "mac"
    mock_gateway.send = AsyncMock()
    
    hass.data = {
        DOMAIN: {
            "mac": {
                "platforms": {
                    "button": {
                        "device_1": {
                            "entities": {}
                        }
                    }
                }
            }
        }
    }
    
    # Test without interface
    btn1 = DisableCommandButtonEntity(
        hass=hass,
        platform="button",
        name="Device",
        device_id="device_1",
        who="1",
        where="12",
        interface=None,
        manufacturer="B",
        model="A",
        gateway=mock_gateway,
    )
    
    assert btn1.name == "Lock"
    assert btn1.unique_id == "mac-device_1-disable"
    assert btn1.extra_state_attributes["A"] == "1"
    assert btn1.extra_state_attributes["PL"] == "2"
    assert "Int" not in btn1.extra_state_attributes
    
    await btn1.async_press()
    mock_gateway.send.assert_called_once_with("*14*0*12##")
    mock_gateway.send.reset_mock()
    
    # Test with interface
    btn2 = DisableCommandButtonEntity(
        hass=hass,
        platform="button",
        name="Device",
        device_id="device_1",
        who="1",
        where="13",
        interface="2",
        manufacturer="B",
        model="A",
        gateway=mock_gateway,
    )
    assert btn2.extra_state_attributes["A"] == "1"
    assert btn2.extra_state_attributes["PL"] == "3"
    assert btn2.extra_state_attributes["Int"] == "2"
    
    await btn2.async_press()
    mock_gateway.send.assert_called_once_with("*14*0*13#4#2##")
    
    # Test lifecycle
    await btn1.async_added_to_hass()
    assert hass.data[DOMAIN]["mac"]["platforms"]["button"]["device_1"]["entities"]["disable"] == btn1
    
    await btn1.async_will_remove_from_hass()
    assert "disable" not in hass.data[DOMAIN]["mac"]["platforms"]["button"]["device_1"]["entities"]


async def test_enable_button_entity(hass):
    """Test EnableCommandButtonEntity logic."""
    mock_gateway = MagicMock()
    mock_gateway.mac = "mac"
    mock_gateway.send = AsyncMock()
    
    hass.data = {
        DOMAIN: {
            "mac": {
                "platforms": {
                    "button": {
                        "device_1": {
                            "entities": {}
                        }
                    }
                }
            }
        }
    }
    
    btn1 = EnableCommandButtonEntity(
        hass=hass,
        platform="button",
        name="Device",
        device_id="device_1",
        who="1",
        where="12",
        interface=None,
        manufacturer="B",
        model="A",
        gateway=mock_gateway,
    )
    
    assert btn1.name == "Unlock"
    assert btn1.unique_id == "mac-device_1-enable"
    
    await btn1.async_press()
    mock_gateway.send.assert_called_once_with("*14*1*12##")
    
    # Test lifecycle
    await btn1.async_added_to_hass()
    assert hass.data[DOMAIN]["mac"]["platforms"]["button"]["device_1"]["entities"]["enable"] == btn1
    
    await btn1.async_will_remove_from_hass()
    assert "enable" not in hass.data[DOMAIN]["mac"]["platforms"]["button"]["device_1"]["entities"]
