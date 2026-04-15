"""Test the MyHOME climate component."""
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.climate.const import HVACMode, HVACAction
from homeassistant.const import UnitOfTemperature

from custom_components.myhome.climate import (
    MyHOMEClimate,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.myhome.ownd.message import (
    OWNHeatingEvent,
    CLIMATE_MODE_OFF,
    CLIMATE_MODE_HEAT,
    CLIMATE_MODE_COOL,
    CLIMATE_MODE_AUTO,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_MAIN_HUMIDITY,
    MESSAGE_TYPE_TARGET_TEMPERATURE,
    MESSAGE_TYPE_LOCAL_OFFSET,
    MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE,
    MESSAGE_TYPE_MODE,
    MESSAGE_TYPE_MODE_TARGET,
    MESSAGE_TYPE_ACTION,
)

async def test_setup_and_unload_entry(hass):
    """Test setup and unload of the climate platform."""
    mock_gateway = MagicMock()
    
    hass.data = {
        "myhome": {
            "mac": {
                "platforms": {
                    "climate": {
                        "device_1": {
                            "who": "4",
                            "zone": "1",
                            "name": "Zone 1",
                            "heating_support": True,
                            "cooling_support": True,
                            "fan_support": False,
                            "standalone": True,
                            "central": False,
                            "manufacturer": "BTicino",
                            "device_model": "F454",
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
    assert len(entities) == 1
    climate_entity = entities[0]
    
    assert isinstance(climate_entity, MyHOMEClimate)
    assert climate_entity.name == "Zone 1"
    
    # Test unload
    await async_unload_entry(hass, config_entry)
    assert "device_1" not in hass.data["myhome"]["mac"]["platforms"]["climate"]

async def test_climate_properties_and_hvac_modes(hass):
    """Test climate entity properties and set_hvac_mode."""
    gateway = MagicMock()
    gateway.send = AsyncMock()
    
    climate = MyHOMEClimate(
        hass=hass,
        name="Thermostat",
        device_id="device_1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=False,
        standalone=True,
        central=False,
        manufacturer="B",
        model="M",
        gateway=gateway,
    )
    
    assert climate.temperature_unit == UnitOfTemperature.CELSIUS
    assert HVACMode.AUTO in climate.hvac_modes
    assert HVACMode.HEAT in climate.hvac_modes
    assert HVACMode.COOL in climate.hvac_modes
    assert HVACMode.OFF in climate.hvac_modes
    
    # Test set_hvac_mode OFF
    await climate.async_set_hvac_mode(HVACMode.OFF)
    gateway.send.assert_called_once()
    assert getattr(gateway.send.call_args[0][0], "mode") == CLIMATE_MODE_OFF
    gateway.send.reset_mock()
    
    # Test set_hvac_mode AUTO
    await climate.async_set_hvac_mode(HVACMode.AUTO)
    gateway.send.assert_called_once()
    assert getattr(gateway.send.call_args[0][0], "mode") == CLIMATE_MODE_AUTO
    gateway.send.reset_mock()
    
    # Test set_hvac_mode HEAT
    climate._target_temperature = 22.0
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    gateway.send.assert_called_once()
    # It sends set_temperature with mode HEAT
    assert getattr(gateway.send.call_args[0][0], "mode") == CLIMATE_MODE_HEAT
    assert getattr(gateway.send.call_args[0][0], "set_temperature") == 22.0
    gateway.send.reset_mock()
    
    # Test set_hvac_mode COOL
    await climate.async_set_hvac_mode(HVACMode.COOL)
    gateway.send.assert_called_once()
    assert getattr(gateway.send.call_args[0][0], "mode") == CLIMATE_MODE_COOL
    gateway.send.reset_mock()

async def test_climate_set_temperature(hass):
    """Test setting temperature."""
    gateway = MagicMock()
    gateway.send = AsyncMock()
    
    climate = MyHOMEClimate(
        hass=hass,
        name="Thermostat",
        device_id="device_1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=False,
        standalone=True,
        central=False,
        manufacturer="B",
        model="M",
        gateway=gateway,
    )
    
    # Set temperature when in HEAT mode
    climate._attr_hvac_mode = HVACMode.HEAT
    await climate.async_set_temperature(temperature=23.0)
    gateway.send.assert_called_once()
    assert getattr(gateway.send.call_args[0][0], "mode") == CLIMATE_MODE_HEAT
    assert getattr(gateway.send.call_args[0][0], "set_temperature") == 23.0
    gateway.send.reset_mock()
    
    # Set temperature when in COOL mode
    climate._attr_hvac_mode = HVACMode.COOL
    await climate.async_set_temperature(temperature=24.0)
    gateway.send.assert_called_once()
    assert getattr(gateway.send.call_args[0][0], "mode") == CLIMATE_MODE_COOL
    assert getattr(gateway.send.call_args[0][0], "set_temperature") == 24.0
    gateway.send.reset_mock()
    
    # Set temperature when in AUTO mode
    climate._attr_hvac_mode = HVACMode.AUTO
    await climate.async_set_temperature(temperature=21.0)
    gateway.send.assert_called_once()
    assert getattr(gateway.send.call_args[0][0], "mode") == CLIMATE_MODE_AUTO
    gateway.send.reset_mock()

async def test_climate_handle_events(hass):
    """Test event handling."""
    gateway = MagicMock()
    gateway.log_id = "test"
    
    climate = MyHOMEClimate(
        hass=hass,
        name="Thermostat",
        device_id="device_1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=False,
        standalone=True,
        central=False,
        manufacturer="B",
        model="M",
        gateway=gateway,
    )
    climate.async_schedule_update_ha_state = MagicMock()
    
    # Event: MAIN_TEMPERATURE
    event = MagicMock(spec=OWNHeatingEvent)
    event.message_type = MESSAGE_TYPE_MAIN_TEMPERATURE
    event.main_temperature = 22.5
    climate.handle_event(event)
    assert climate.current_temperature == 22.5
    
    # Event: MAIN_HUMIDITY
    event.message_type = MESSAGE_TYPE_MAIN_HUMIDITY
    event.main_humidity = 55.0
    climate.handle_event(event)
    assert climate.current_humidity == 55.0
    
    # Event: TARGET_TEMPERATURE
    event.message_type = MESSAGE_TYPE_TARGET_TEMPERATURE
    event.set_temperature = 21.0
    climate.handle_event(event)
    assert climate.target_temperature == 21.0
    
    # Event: LOCAL_OFFSET
    event.message_type = MESSAGE_TYPE_LOCAL_OFFSET
    event.local_offset = 1
    climate.handle_event(event)
    assert climate._local_target_temperature == 22.0
    assert climate.target_temperature == 22.0
    
    # Event: LOCAL_TARGET_TEMPERATURE
    event.message_type = MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE
    event.local_set_temperature = 23.0
    climate.handle_event(event)
    assert climate._target_temperature == 22.0 # local_set - local_offset (23-1)
    
    # Event: MODE (HEAT)
    event.message_type = MESSAGE_TYPE_MODE
    event.mode = CLIMATE_MODE_HEAT
    climate.handle_event(event)
    assert climate.hvac_mode == HVACMode.HEAT
    
    # Event: MODE (OFF)
    event.mode = CLIMATE_MODE_OFF
    climate.handle_event(event)
    assert climate.hvac_mode == HVACMode.OFF
    assert climate.hvac_action == HVACAction.OFF
    
    # Event: MODE_TARGET (AUTO with set temp)
    event.message_type = MESSAGE_TYPE_MODE_TARGET
    event.mode = CLIMATE_MODE_AUTO
    event.set_temperature = 22.5
    climate.handle_event(event)
    assert climate.hvac_mode == HVACMode.AUTO
    assert climate._target_temperature == 22.5
    
    # Event: ACTION
    event.message_type = MESSAGE_TYPE_ACTION
    event.is_active.return_value = True
    event.is_heating.return_value = True
    climate.handle_event(event)
    assert climate.hvac_action == HVACAction.HEATING

async def test_climate_async_update(hass):
    """Test async update."""
    gateway = MagicMock()
    gateway.send_status_request = AsyncMock()
    
    climate = MyHOMEClimate(
        hass=hass,
        name="Thermostat",
        device_id="device_1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=False,
        standalone=True,
        central=False,
        manufacturer="B",
        model="M",
        gateway=gateway,
    )
    
    await climate.async_update()
    gateway.send_status_request.assert_called_once()
