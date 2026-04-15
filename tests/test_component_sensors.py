import pytest
from unittest.mock import MagicMock
from homeassistant.const import UnitOfPower, UnitOfEnergy, UnitOfTemperature

from custom_components.myhome.sensor import (
    MyHOMEPowerSensor,
    MyHOMEEnergySensor,
    MyHOMETemperatureSensor,
    MyHOMEIlluminanceSensor,
)
from custom_components.myhome.binary_sensor import (
    MyHOMEDryContact,
    MyHOMEAuxiliary,
    MyHOMEMotionSensor,
)

@pytest.fixture
def mock_gateway():
    gateway = MagicMock()
    gateway.mac = "01:02:03:04:05:06"
    gateway.log_id = "[Test Gateway]"
    return gateway

@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {"myhome": {"01:02:03:04:05:06": {"platforms": {"sensor": {}, "binary_sensor": {}}}}}
    return hass


class TestSensorsCoverage:

    def test_energy_sensor(self, mock_hass, mock_gateway):
        sensor = MyHOMEEnergySensor(
            hass=mock_hass,
            name="Test En",
            device_id="sensor_energy",
            who="18",
            where="51",
            entity_specific_id="total-energy",
            device_class="energy",
            manufacturer="Bticino",
            model="Meter",
            gateway=mock_gateway
        )
        sensor.async_schedule_update_ha_state = MagicMock()
        msg = MagicMock()
        msg.message_type = "energy_totalizer"
        msg.total_consumption = 1500.0
        msg.human_readable_log = "mock energy"
        sensor.handle_event(msg)
        assert sensor._attr_native_value == 1500.0

    def test_temperature_sensor(self, mock_hass, mock_gateway):
        sensor = MyHOMETemperatureSensor(
            hass=mock_hass,
            name="Test Temp",
            device_id="sensor_temp",
            who="4",
            where="51",
            device_class="temperature",
            manufacturer="Bticino",
            model="Meter",
            gateway=mock_gateway
        )
        sensor.async_schedule_update_ha_state = MagicMock()
        msg = MagicMock()
        msg.message_type = "main_temperature"
        msg.local_offset = 0
        msg.temperature = 22.5
        msg.human_readable_log = "mock temp"
        sensor.handle_event(msg)
        assert sensor._attr_native_value == 22.5

    def test_illuminance_sensor(self, mock_hass, mock_gateway):
        sensor = MyHOMEIlluminanceSensor(
            hass=mock_hass,
            name="Test Illum",
            device_id="sensor_lux",
            who="4",
            where="51",
            device_class="illuminance",
            manufacturer="Bticino",
            model="Meter",
            gateway=mock_gateway
        )
        sensor.async_schedule_update_ha_state = MagicMock()
        msg = MagicMock()
        msg.message_type = "illuminance_value"
        msg.illuminance = 450
        msg.human_readable_log = "mock lux"
        sensor.handle_event(msg)
        assert sensor._attr_native_value == 450


class TestBinarySensorsCoverage:

    def test_auxiliary(self, mock_hass, mock_gateway):
        sensor = MyHOMEAuxiliary(
            hass=mock_hass,
            name="Test Aux",
            entity_name="test_aux",
            device_id="aux_1",
            who="25",
            where="51",
            inverted=False,
            device_class="window",
            manufacturer="Bticino",
            model="Sensor",
            gateway=mock_gateway
        )
        sensor.async_schedule_update_ha_state = MagicMock()
        msg = MagicMock(is_on=True, human_readable_log="o")
        sensor.handle_event(msg)
        assert sensor._attr_is_on is True

    def test_motion(self, mock_hass, mock_gateway):
        sensor = MyHOMEMotionSensor(
            hass=mock_hass,
            name="Test Motion",
            entity_name="test_mot",
            device_id="mot_1",
            who="25",
            where="51",
            inverted=False,
            device_class="motion",
            manufacturer="Bticino",
            model="Sensor",
            gateway=mock_gateway
        )
        sensor.async_schedule_update_ha_state = MagicMock()
        msg = MagicMock(is_on=True, human_readable_log="m")
        sensor.handle_event(msg)
        assert sensor._attr_is_on is True
