"""Test the MyHOME binary sensor component."""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.myhome.binary_sensor import (
    MyHOMEDryContact,
    MyHOMEAuxiliary,
    MyHOMEMotionSensor,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.myhome.ownd.message import (
    OWNDryContactEvent,
    OWNLightingEvent,
    MESSAGE_TYPE_MOTION,
    MESSAGE_TYPE_PIR_SENSITIVITY,
    MESSAGE_TYPE_MOTION_TIMEOUT,
)
from custom_components.myhome.const import DOMAIN

async def test_setup_and_unload_entry(hass):
    """Test setup and unload of the binary_sensor platform."""
    mock_gateway = MagicMock()
    
    hass.data = {
        DOMAIN: {
            "mac": {
                "platforms": {
                    "binary_sensor": {
                        "device_1": {
                            "who": "25",
                            "where": "12",
                            "name": "Dry Contact",
                            "entity_name": "Contact 1",
                            "inverted": False,
                            "device_class": BinarySensorDeviceClass.WINDOW,
                            "manufacturer": "B",
                            "device_model": "M",
                        },
                        "device_2": {
                            "who": "9",
                            "where": "13",
                            "name": "Aux",
                            "entity_name": "Aux 1",
                            "inverted": True,
                            "device_class": BinarySensorDeviceClass.DOOR,
                            "manufacturer": "B",
                            "device_model": "M",
                        },
                        "device_3": {
                            "who": "1",
                            "where": "14",
                            "name": "Motion",
                            "entity_name": "Motion 1",
                            "inverted": False,
                            "device_class": BinarySensorDeviceClass.MOTION,
                            "manufacturer": "B",
                            "device_model": "M",
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
    
    assert len(entities) == 3
    assert isinstance(entities[0], MyHOMEDryContact)
    assert isinstance(entities[1], MyHOMEAuxiliary)
    assert isinstance(entities[2], MyHOMEMotionSensor)
    
    # Test unload
    await async_unload_entry(hass, config_entry)
    assert "device_1" not in hass.data[DOMAIN]["mac"]["platforms"]["binary_sensor"]

async def test_dry_contact(hass):
    """Test MyHOMEDryContact logic."""
    gateway = MagicMock()
    gateway.send_status_request = AsyncMock()
    
    hass.data = {DOMAIN: {"mac": {"platforms": {"binary_sensor": {"device_1": {"entities": {}}}}}}}
    
    sensor = MyHOMEDryContact(
        hass=hass,
        name="Device",
        entity_name="Sensor 1",
        device_id="device_1",
        who="25",
        where="12",
        inverted=False,
        device_class=BinarySensorDeviceClass.WINDOW,
        manufacturer="M",
        model="M",
        gateway=gateway,
    )
    
    sensor.async_schedule_update_ha_state = MagicMock()
    
    assert sensor.name == "Sensor 1"
    assert sensor.device_class == BinarySensorDeviceClass.WINDOW
    assert not sensor.is_on
    
    # Update state via method
    await sensor.async_update()
    gateway.send_status_request.assert_called_once()
    
    # Handle on event
    event = MagicMock(spec=OWNDryContactEvent)
    event.is_on = True
    sensor.handle_event(event)
    assert sensor.is_on
    
    # Handle off event
    event.is_on = False
    sensor.handle_event(event)
    assert not sensor.is_on
    
    # Test lifecycle
    gateway.mac = "mac"
    await sensor.async_added_to_hass()
    await sensor.async_will_remove_from_hass()

async def test_dry_contact_inverted(hass):
    """Test MyHOMEDryContact logic when inverted."""
    sensor = MyHOMEDryContact(
        hass=hass, name="Device", entity_name="Sensor", device_id="D1",
        who="25", where="12", inverted=True, device_class=BinarySensorDeviceClass.WINDOW,
        manufacturer="M", model="M", gateway=MagicMock(),
    )
    sensor.async_schedule_update_ha_state = MagicMock()
    # Default is false
    event = MagicMock(spec=OWNDryContactEvent)
    event.is_on = True
    sensor.handle_event(event)
    # Since inverted is True, True != True returns False
    assert not sensor.is_on
    
    event.is_on = False
    sensor.handle_event(event)
    assert sensor.is_on

async def test_auxiliary_sensor(hass):
    """Test MyHOMEAuxiliary logic."""
    gateway = MagicMock()
    gateway.mac = "mac"
    hass.data = {DOMAIN: {"mac": {"platforms": {"binary_sensor": {"device_1": {"entities": {}}}}}}}
    
    sensor = MyHOMEAuxiliary(
        hass=hass, name="Device", entity_name="Sensor", device_id="device_1",
        who="9", where="12", inverted=False, device_class=BinarySensorDeviceClass.DOOR,
        manufacturer="M", model="M", gateway=gateway,
    )
    sensor.async_schedule_update_ha_state = MagicMock()
    
    # Update does nothing for AUX
    await sensor.async_update()
    
    event = MagicMock(spec=OWNDryContactEvent)
    event.is_on = True
    sensor.handle_event(event)
    assert sensor.is_on
    
    # Lifecycle
    await sensor.async_added_to_hass()
    await sensor.async_will_remove_from_hass()

async def test_motion_sensor(hass):
    """Test MyHOMEMotionSensor logic."""
    gateway = MagicMock()
    gateway.mac = "mac"
    gateway.send_status_request = AsyncMock()
    
    hass.data = {DOMAIN: {"mac": {"platforms": {"binary_sensor": {"device_1": {"entities": {}}}}}}}
    
    sensor = MyHOMEMotionSensor(
        hass=hass, name="Device", entity_name="Sensor", device_id="device_1",
        who="1", where="12", inverted=False, device_class=BinarySensorDeviceClass.MOTION,
        manufacturer="M", model="M", gateway=gateway,
    )
    sensor.async_write_ha_state = MagicMock()
    
    # Init tests calls to gateway
    sensor.async_get_last_state = AsyncMock(return_value=None)
    await sensor.async_added_to_hass()
    assert gateway.send_status_request.call_count == 2
    
    # Test motion event
    event = MagicMock(spec=OWNLightingEvent)
    event.message_type = MESSAGE_TYPE_MOTION
    event.motion = True
    sensor.handle_event(event)
    assert sensor.is_on
    
    # Test timeout event
    event.message_type = MESSAGE_TYPE_MOTION_TIMEOUT
    event.motion_timeout = timedelta(seconds=60)
    sensor.handle_event(event)
    assert sensor._timeout == timedelta(seconds=75)
    
    # Test PIR sensitivity event
    event.message_type = MESSAGE_TYPE_PIR_SENSITIVITY
    event.pir_sensitivity = 2 # 0: low, 1: medium, 2: high
    sensor.handle_event(event)
    assert sensor.extra_state_attributes["Sensitivity"] == "high"
    
    # Test unrelated event
    event.message_type = "unrelated"
    assert sensor.handle_event(event) is True
    
    # Test async_will_remove_from_hass
    await sensor.async_will_remove_from_hass()
