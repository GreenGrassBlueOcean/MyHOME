
from unittest.mock import MagicMock

import pytest
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import CONF_NAME, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from OWNd.message import OWNLightingEvent
from voluptuous.error import Invalid

from custom_components.myhome.const import CONF_WHERE, DOMAIN
from custom_components.myhome.light_group import MyHOMELightGroup
from custom_components.myhome.validate import light_schema


def test_schema_validates_group():
    """Test that schema validates groups with members."""
    data = {
        "light_1": {
            CONF_WHERE: "#6",
            CONF_NAME: "Group 6",
            "members": ["11", "12"]
        }
    }
    validated = light_schema(data)
    # The key will be rewritten to 1-#6 by the MyHomeDeviceSchema
    assert "1-#6" in validated
    assert validated["1-#6"]["members"] == ["11", "12"]

def test_schema_rejects_members_on_point_to_point():
    """Test that members are rejected on point-to-point."""
    data = {
        "light_1": {
            CONF_WHERE: "11",
            CONF_NAME: "Light 11",
            "members": ["12"]
        }
    }
    with pytest.raises(Invalid):
        light_schema(data)

def test_schema_rejects_invalid_members():
    """Test that members must be point to point."""
    data = {
        "light_1": {
            CONF_WHERE: "#6",
            CONF_NAME: "Group 6",
            "members": ["#7"]
        }
    }
    with pytest.raises(Invalid):
        light_schema(data)

async def test_light_group_assumed_state(hass: HomeAssistant):
    """Test light group assumed state without members."""
    gateway = MagicMock()
    from unittest.mock import AsyncMock
    gateway.send_status_request = AsyncMock()
    gateway.send_command = AsyncMock()
    gateway.mac = "00:00:00"
    gateway.available = True

    entity = MyHOMELightGroup(
        hass, "Group 6", "dev1", 6, gateway, [], True, True, True, True
    )

    entity.hass = hass
    entity.entity_id = "light.group_6"
    await entity.async_added_to_hass()

    assert entity.assumed_state is True

    # Turn on
    await entity.async_turn_on()

    assert entity.is_on is True
    arg = entity._gateway_handler.send_command.call_args[0][0]
    # assert arg.dimension is None
    assert str(arg) == "*1*1*#6##"
    assert arg.where == "#6"

    # Turn on dimming
    await entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
    arg = entity._gateway_handler.send_command.call_args[0][0]
    assert arg.dimension == 1
    assert arg.where == "#6"

    # Receive group frame
    msg = MagicMock(spec=OWNLightingEvent)
    msg.who = 1
    msg.is_translation = False
    msg.is_group = True
    msg.group = "6"
    msg.dimension = None
    msg.is_off = True
    msg.is_on = False

    entity._handle_bus_message(msg)
    assert entity.is_on is False

@pytest.mark.asyncio
async def test_light_group_with_members(hass: HomeAssistant):
    """Test light group derives state from members."""
    gateway = MagicMock()
    from unittest.mock import AsyncMock
    gateway.send_status_request = AsyncMock()
    gateway.send_command = AsyncMock()
    gateway.mac = "00:00:00"
    gateway.available = True

    registry = er.async_get(hass)
    entry1 = registry.async_get_or_create("light", DOMAIN, "00:00:00-1-11", suggested_object_id="member_1")
    entry2 = registry.async_get_or_create("light", DOMAIN, "00:00:00-1-12", suggested_object_id="member_2")

    entity = MyHOMELightGroup(
        hass, "Group 6", "dev1", 6, gateway, ["11", "12"], True, False, False, False
    )

    entity.hass = hass
    entity.entity_id = "light.group_6"

    await entity.async_added_to_hass()
    assert entity.assumed_state is False

    # Initially member states do not exist -> off
    assert entity.is_on is False

    # Update member 1 to ON
    hass.states.async_set(entry1.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255})
    await hass.async_block_till_done()

    assert entity.is_on is True
    assert entity.brightness == 255

    # Update member 2 to ON but lower brightness
    hass.states.async_set(entry2.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 127})
    await hass.async_block_till_done()

    assert entity.is_on is True
    assert entity.brightness == 191 # (255+127)/2

    # Both members unavailable
    hass.states.async_set(entry1.entity_id, STATE_UNAVAILABLE)
    hass.states.async_set(entry2.entity_id, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    assert entity.available is False
