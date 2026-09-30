"""Regression tests for the runtime defects collected in #566."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from OWNd.message import OWNMessage

from custom_components.myhome.alarm_control_panel import MyHOMEAlarmControlPanel
from custom_components.myhome.sensor import MyHOMETemperatureSensor
from homeassistant.components.sensor import SensorDeviceClass


@pytest.fixture
def gateway():
    gw = MagicMock()
    gw.mac = "00:03:50:00:55:55"
    gw.unique_id = gw.mac
    gw.log_id = "[Test]"
    gw.send = AsyncMock()
    gw.send_status_request = AsyncMock()
    return gw


# --- alarm: the central unit takes no code over the bus --------------------


def test_alarm_arm_needs_no_code(hass: HomeAssistant, gateway) -> None:
    alarm = MyHOMEAlarmControlPanel(
        hass=hass, name="Alarm", entity_name="Alarm", device_id="0", who="5", where="0",
        manufacturer="BTicino", model="3486", gateway=gateway,
    )
    alarm.entity_id = "alarm_control_panel.alarm"
    assert alarm.code_arm_required is False
    assert alarm.check_code_arm_required(None) is None


# --- WHO 4: temperatures below zero ----------------------------------------


@pytest.mark.parametrize(
    ("frame", "expected"),
    [("*#4*1*0*0055##", 5.5), ("*#4*1*0*1055##", -5.5), ("*#4*1*0*1005##", -0.5)],
)
def test_temperature_sensor_reads_the_sign(hass: HomeAssistant, gateway, frame, expected) -> None:
    sensor = MyHOMETemperatureSensor(
        hass=hass, name="Zone 1", device_id="4-1", who="4", where="1",
        device_class=SensorDeviceClass.TEMPERATURE, manufacturer="BTicino", model="Probe", gateway=gateway,
    )
    sensor.async_schedule_update_ha_state = MagicMock()
    sensor.handle_event(OWNMessage.parse(frame))
    assert sensor._attr_native_value == expected


def test_climate_reads_the_sign_of_the_zone_temperature(hass: HomeAssistant, gateway) -> None:
    from custom_components.myhome.climate import MyHOMEClimate

    climate = MyHOMEClimate(
        hass=hass, name="Zone", device_id="1", who="4", where="1", heating=True, cooling=False,
        fan=False, standalone=True, central=False, manufacturer="B", model="M", gateway=gateway,
    )
    climate.entity_id = "climate.zone"
    climate.async_schedule_update_ha_state = MagicMock()
    climate.handle_event(OWNMessage.parse("*#4*1*0*1055##"))
    assert climate.current_temperature == -5.5
    climate.handle_event(OWNMessage.parse("*#4*1*0*0215##"))
    assert climate.current_temperature == 21.5


def test_signed_temperature_ignores_mocks_and_unknown_values() -> None:
    from custom_components.myhome.const import signed_who4_temperature

    assert signed_who4_temperature(MagicMock(), 3.0) == 3.0
    assert signed_who4_temperature(MagicMock(_dimension_value=["1055"]), None) is None
    assert signed_who4_temperature(MagicMock(_dimension_value=[]), 3.0) == 3.0


# --- lights ----------------------------------------------------------------


def _light(hass: HomeAssistant, gateway):
    from custom_components.myhome.light import MyHOMELight

    gateway.config_entry = MagicMock(options={"transition_mode": "native"})
    light = MyHOMELight(
        hass=hass, name="L", entity_name="L", icon=None, icon_on=None, device_id="12", who="1",
        where="12", interface=None, dimmable=True, manufacturer="B", model="M", gateway=gateway,
    )
    light.async_schedule_update_ha_state = MagicMock()
    return light


async def test_brightness_one_of_255_is_on_at_minimum_not_off(hass: HomeAssistant, gateway) -> None:
    light = _light(hass, gateway)
    await light.async_turn_on(brightness=1)
    frames = [str(call.args[0]) for call in gateway.send.await_args_list]
    assert frames, "nothing was sent"
    assert "*1*0*12##" not in frames
    assert light._attr_is_on is not False


@pytest.mark.parametrize(("what", "percent"), [(2, 20), (5, 50), (10, 100)])
def test_wall_dimmer_preset_is_the_level(hass: HomeAssistant, gateway, what, percent) -> None:
    light = _light(hass, gateway)
    light.handle_event(OWNMessage.parse(f"*1*{what}*12##"))
    assert light._attr_is_on is True
    assert light._attr_brightness_pct == percent
    assert light._attr_brightness == round(percent * 255 / 100)


# --- light group -----------------------------------------------------------


def _group(hass: HomeAssistant, gateway):
    from custom_components.myhome.light_group import MyHOMELightGroup

    group = MyHOMELightGroup(
        hass, "Group 6", "dev1", 6, gateway, [], dimmable=True, color_temp=True, rgb=True, hs=False,
    )
    group.hass = hass
    group.entity_id = "light.group_6"
    group.async_schedule_update_ha_state = MagicMock()
    return group


@pytest.mark.parametrize(("value", "brightness"), [(150, 128), (200, 255), (101, 3)])
def test_group_dimension_1_carries_level_plus_100(hass: HomeAssistant, gateway, value, brightness) -> None:
    group = _group(hass, gateway)
    group.handle_event(OWNMessage.parse(f"*#1*#6*1*{value}*0##"))
    assert group.brightness == brightness


def test_group_ignores_out_of_range_dimension_1(hass: HomeAssistant, gateway) -> None:
    group = _group(hass, gateway)
    group.handle_event(OWNMessage.parse("*#1*#6*1*150*0##"))
    group.handle_event(OWNMessage.parse("*#1*#6*1*50*0##"))
    assert group.brightness == 128


def test_group_ignores_the_unsupported_colour_sentinels(hass: HomeAssistant, gateway) -> None:
    group = _group(hass, gateway)
    group.handle_event(OWNMessage.parse("*#1*#6*14*1##"))
    assert group.color_temp_kelvin is None
    group.handle_event(OWNMessage.parse("*#1*#6*12*511*127*255##"))
    assert group.hs_color is None
