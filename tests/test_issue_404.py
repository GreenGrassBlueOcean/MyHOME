"""Regression tests for Issue #404 and Issue #303.

Verifies:
1. Standalone climate zones with fancoil fan actuators update hvac_action to COOLING
   or HEATING when the fan runs (Dimension 20), resolving Issue #404.
2. When the fan stops (Dimension 20 value 5) and all actuators are off, hvac_action
   correctly transitions back to IDLE (or OFF).
3. The configured fan_mode='auto' is preserved and NOT overwritten by Dimension 20
   instantaneous running speed telemetry, resolving Issue #303 comment 5728387183.
4. Full 42-frame bus trace from Issue #404 replays cleanly through Home Assistant.
"""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.climate.const import (
    HVACAction,
    HVACMode,
)
from homeassistant.const import CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from OWNd.message import OWNEvent

from custom_components.myhome.climate import MyHOMEClimate, async_setup_entry
from custom_components.myhome.const import (
    CONF_ENTITY,
    CONF_PLATFORMS,
    DOMAIN,
)
from tests.conftest import attach_runtime

MAC = "00:03:50:40:04:04"


@pytest.fixture
def mock_gateway():
    gw = MagicMock()
    gw.log_id = "[issue 404]"
    gw.mac = MAC
    return gw

ISSUE_404_BUS_TRACE = [
    "*#4*2*60*46##",
    "*4*303*1##",
    "*4*303*1##",
    "*#4*1*12*0280*3##",
    "*#4*1*0*0259##",
    "*#4*1*#14*0230*2##",
    "*4*0*1##",
    "*#4*1*12*0230*3##",
    "*#4*1*0*0259##",
    "*#4*1#2*#20*8##",
    "*#4*1#2*20*8##",
    "*4*4001#1*0#3##",
    "*#4*0#3*20*1##",
    "*#4*1*#14*0295*2##",
    "*#4*1*0*0259##",
    "*#4*4*60*46##",
    "*#4*1*#14*0270*2##",
    "*#4*1*12*0270*3##",
    "*4*0*1##",
    "*#4*1*0*0259##",
    "*4*4002#1*0#3##",
    "*#4*0#3*20*0##",
    "*4*4002*1##",
    "*#4*1#2*#20*5##",
    "*#4*1#2*20*5##",
    "*#4*1*#14*0200*2##",
    "*#4*1*12*0200*3##",
    "*4*0*1##",
    "*#4*1*0*0259##",
    "*#4*1#2*#20*8##",
    "*#4*1#2*20*8##",
    "*4*4001#1*0#3##",
    "*#4*0#3*20*1##",
    "*4*303*1##",
    "*4*303*1##",
    "*#4*1*12*0200*3##",
    "*#4*1*0*0259##",
    "*4*4002#1*0#3##",
    "*#4*0#3*20*0##",
    "*4*4002*1##",
    "*#4*1#2*#20*5##",
    "*#4*1#2*20*5##",
]


async def test_fancoil_fan_sets_hvac_action_cooling_and_idle(hass: HomeAssistant, mock_gateway):
    """Test that fan activation updates hvac_action to COOLING, and fan off updates to IDLE (#404)."""
    climate = MyHOMEClimate(
        hass=hass,
        name="Zone 1",
        device_id="4-1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=True,
        standalone=True,
        central=False,
        manufacturer="BTicino",
        model="Fancoil Zone",
        gateway=mock_gateway,
    )
    climate.entity_id = "climate.zone_1"
    climate.async_schedule_update_ha_state = MagicMock()

    # 1. Zone mode set to COOL via *4*0*1##
    climate.handle_event(OWNEvent.parse("*4*0*1##"))
    assert climate.hvac_mode == HVACMode.COOL
    assert climate.hvac_action == HVACAction.IDLE

    # 2. Fan actuator starts at high speed (*20*8, speed 3)
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*8##"))
    assert climate.hvac_action == HVACAction.COOLING
    assert climate.fan_mode == "auto"
    assert climate.extra_state_attributes["running_fan_speed"] == "high"

    # 3. Fan actuator stops (*20*5, fan off)
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*5##"))
    assert climate.hvac_action == HVACAction.IDLE
    assert climate.fan_mode == "auto"
    assert climate.extra_state_attributes["running_fan_speed"] == "off"


async def test_fancoil_fan_sets_hvac_action_heating_and_idle(hass: HomeAssistant, mock_gateway):
    """Test that fan activation updates hvac_action to HEATING in heat mode (#404)."""
    climate = MyHOMEClimate(
        hass=hass,
        name="Zone 1",
        device_id="4-1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=True,
        standalone=True,
        central=False,
        manufacturer="BTicino",
        model="Fancoil Zone",
        gateway=mock_gateway,
    )
    climate.entity_id = "climate.zone_1"
    climate.async_schedule_update_ha_state = MagicMock()

    # 1. Zone mode set to HEAT
    climate._attr_hvac_mode = HVACMode.HEAT
    climate._attr_hvac_action = HVACAction.IDLE

    # 2. Fan actuator starts at speed 2 (*20*7, medium)
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*7##"))
    assert climate.hvac_action == HVACAction.HEATING
    assert climate.extra_state_attributes["running_fan_speed"] == "medium"

    # 3. Fan actuator stops (*20*5)
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*5##"))
    assert climate.hvac_action == HVACAction.IDLE
    assert climate.extra_state_attributes["running_fan_speed"] == "off"


async def test_fancoil_fan_auto_mode_preservation_under_dimension_20(hass: HomeAssistant, mock_gateway):
    """Test that setting fan_mode='auto' is not corrupted by actuator Dimension 20 running telemetry (#303)."""
    climate = MyHOMEClimate(
        hass=hass,
        name="Zone 1",
        device_id="4-1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=True,
        standalone=True,
        central=False,
        manufacturer="BTicino",
        model="Fancoil Zone",
        gateway=mock_gateway,
    )
    climate.entity_id = "climate.zone_1"
    climate.async_schedule_update_ha_state = MagicMock()

    # Explicitly set fan mode to auto via Dimension 11 (or async_set_fan_mode)
    climate.handle_event(OWNEvent.parse("*#4*1*11*0##"))
    assert climate.fan_mode == "auto"

    # Actuator runs at high speed (*20*8)
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*8##"))
    assert climate.fan_mode == "auto"
    assert climate.extra_state_attributes["running_fan_speed"] == "high"

    # Actuator drops to low speed (*20*6)
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*6##"))
    assert climate.fan_mode == "auto"
    assert climate.extra_state_attributes["running_fan_speed"] == "low"

    # Actuator stops (*20*5)
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*5##"))
    assert climate.fan_mode == "auto"
    assert climate.extra_state_attributes["running_fan_speed"] == "off"


async def test_fancoil_fan_in_auto_hvac_mode_determines_action_from_temperature(hass: HomeAssistant, mock_gateway):
    """Test that when hvac_mode is AUTO, active fan derives action from temperature delta."""
    climate = MyHOMEClimate(
        hass=hass,
        name="Zone 1",
        device_id="4-1",
        who="4",
        where="1",
        heating=True,
        cooling=True,
        fan=True,
        standalone=True,
        central=False,
        manufacturer="BTicino",
        model="Fancoil Zone",
        gateway=mock_gateway,
    )
    climate.entity_id = "climate.zone_1"
    climate.async_schedule_update_ha_state = MagicMock()

    climate._attr_hvac_mode = HVACMode.AUTO
    climate._target_temperature = 22.0

    # 1. Current temp 25.0°C > target 22.0°C -> Cooling
    climate._attr_current_temperature = 25.0
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*8##"))
    assert climate.hvac_action == HVACAction.COOLING

    # 2. Current temp 19.0°C < target 22.0°C -> Heating
    climate._attr_current_temperature = 19.0
    climate.handle_event(OWNEvent.parse("*#4*1#2*20*8##"))
    assert climate.hvac_action == HVACAction.HEATING


async def test_issue_404_trace_replay(hass: HomeAssistant, mock_gateway):
    """Replay the full 42-frame bus trace from Issue #404 and verify exact state transitions."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry_404"
    config_entry.data = {CONF_MAC: MAC}

    hass.data = {
        DOMAIN: {
            MAC: {
                CONF_PLATFORMS: {"climate": {}},
                CONF_ENTITY: mock_gateway,
            }
        }
    }

    added_entities: list[MyHOMEClimate] = []
    attach_runtime(hass, config_entry)
    await async_setup_entry(hass, config_entry, added_entities.extend)

    # Deliver all frames from the Issue #404 diagnostic bundle
    for raw in ISSUE_404_BUS_TRACE:
        event = OWNEvent.parse(raw)
        if event is not None:
            async_dispatcher_send(hass, f"myhome_message_{MAC}", event)

    await hass.async_block_till_done()

    by_where = {e._where: e for e in added_entities}
    assert "1" in by_where, f"Zone 1 was not discovered; discovered: {list(by_where.keys())}"
    z1 = by_where["1"]

    # Final state after trace:
    # Zone 1 received *4*303*1## (off) and ended with *#4*1#2*20*5## (fan off)
    assert z1.hvac_mode == HVACMode.OFF
    assert z1.hvac_action == HVACAction.OFF
    assert z1.fan_mode == "auto"
    assert z1.extra_state_attributes["running_fan_speed"] == "off"
    assert z1.current_temperature == 25.9
    assert z1.target_temperature == 20.0
