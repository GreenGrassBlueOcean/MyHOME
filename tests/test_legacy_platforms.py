"""Coverage tests for legacy MyHOME platforms relying on static CONF_PLATFORMS."""
import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.const import (CONF_MAC, CONF_NAME, CONF_DEVICE_CLASS, CONF_HOST, CONF_PORT, CONF_PASSWORD, CONF_FRIENDLY_NAME)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import (
    DOMAIN, CONF_PLATFORMS, CONF_ENTITIES, CONF_WHO, CONF_WHERE, 
    CONF_ZONE, CONF_ENTITY_NAME, CONF_INVERTED,
    CONF_MANUFACTURER, CONF_DEVICE_MODEL, CONF_HEATING_SUPPORT, CONF_COOLING_SUPPORT,
    CONF_FAN_SUPPORT, CONF_STANDALONE, CONF_CENTRAL, CONF_ICON, CONF_ICON_ON,
    CONF_SSDP_LOCATION, CONF_SSDP_ST, CONF_DEVICE_TYPE,
    CONF_MANUFACTURER_URL, CONF_FIRMWARE, CONF_UDN
)
from custom_components.myhome.ownd.message import OWNEvent
from homeassistant.helpers.dispatcher import async_dispatcher_send

@pytest.fixture
def mock_gateway_connection():
    with patch(
        "custom_components.myhome.gateway.OWNSession.test_connection",
        return_value={"Success": True, "Message": None}
    ), patch(
        "custom_components.myhome.gateway.MyHOMEGatewayHandler.listening_loop"
    ), patch(
        "custom_components.myhome.gateway.MyHOMEGatewayHandler.sending_loop"
    ), patch(
        "custom_components.myhome.gateway.MyHOMEGatewayHandler.send"
    ) as mock_send, patch(
        "custom_components.myhome.gateway.MyHOMEGatewayHandler.send_status_request"
    ) as mock_req:
        yield mock_send, mock_req


async def test_legacy_platforms_setup_and_execution(hass: HomeAssistant, mock_gateway_connection, caplog):
    """Test legacy platforms logic instantiated via fallback CONF_PLATFORMS."""
    import logging
    caplog.set_level(logging.DEBUG)
    mac_addr = "00:03:50:00:12:35"
    mock_send, mock_req = mock_gateway_connection
    
    hass.data.setdefault(DOMAIN, {})
    
    # Pre-populate hass.data completely bypassing __init__ fallback with static entities
    hass.data[DOMAIN][mac_addr] = {
        CONF_ENTITIES: {"switch": {}, "binary_sensor": {}, "climate": {}, "sensor": {}, "button": {}, "light": {}, "cover": {}, "media_player": {}},
        CONF_PLATFORMS: {
            "switch": {
                "switch_12": {
                    CONF_WHO: "1", CONF_WHERE: "12", CONF_NAME: "Switch 12",
                    CONF_ENTITY_NAME: "Switch 12", CONF_DEVICE_CLASS: "switch",
                    CONF_ICON: "mdi:flash", CONF_ICON_ON: "mdi:flash",
                    CONF_MANUFACTURER: "BTicino", CONF_DEVICE_MODEL: "Model"
                }
            },
            "binary_sensor": {
                "bs_35": {
                    CONF_WHO: "25", CONF_WHERE: "35", CONF_NAME: "BS 35",
                    CONF_ENTITY_NAME: "BS 35", CONF_DEVICE_CLASS: "door",
                    CONF_INVERTED: False, CONF_MANUFACTURER: "B", CONF_DEVICE_MODEL: "M"
                }
            },
            "climate": {
                "clim_01": {
                    CONF_WHO: "4", CONF_ZONE: "01", CONF_NAME: "Climate 1",
                    CONF_HEATING_SUPPORT: True, CONF_COOLING_SUPPORT: True,
                    CONF_FAN_SUPPORT: False, CONF_STANDALONE: False, CONF_CENTRAL: False,
                    CONF_MANUFACTURER: "B", CONF_DEVICE_MODEL: "M"
                }
            },
            "sensor": {
                "sens_1": {
                    CONF_WHO: "18", CONF_WHERE: "51", CONF_NAME: "Sensor 1",
                    CONF_ENTITY_NAME: "Sensor 1", CONF_DEVICE_CLASS: "power",
                    CONF_MANUFACTURER: "B", CONF_DEVICE_MODEL: "M",
                    CONF_ENTITIES: {"daily_energy": "daily"}
                }
            },
            "button": {
                "button_1": {
                    CONF_WHO: "1", CONF_WHERE: "1", CONF_NAME: "Button 1",
                    CONF_ENTITY_NAME: "Button 1", CONF_MANUFACTURER: "B", CONF_DEVICE_MODEL: "M",
                    CONF_ICON: "mdi:button"
                }
            },
            "light": {}, "cover": {}, "media_player": {}
        }
    }
    
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.0.35",
            CONF_PORT: 20000,
            CONF_PASSWORD: "pass",
            CONF_MAC: mac_addr,
            CONF_SSDP_LOCATION: "http://192.168.0.35:49153/description.xml",
            CONF_SSDP_ST: "ssdp:all",
            CONF_DEVICE_TYPE: "urn:schemas-upnp-org:device:Basic:1",
            CONF_FRIENDLY_NAME: "MyHOME Gateway",
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_MANUFACTURER_URL: "http://www.bticino.it",
            CONF_NAME: "MyHOME Gateway",
            CONF_FIRMWARE: "1.0",
            CONF_UDN: "uuid:1234",
        },
        unique_id=mac_addr,
    )
    config_entry.add_to_hass(hass)

    success = await hass.config_entries.async_setup(config_entry.entry_id)
    assert success
    await hass.async_block_till_done()

    # Hit Switch turn_on and turn_off coverage
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.switch_12"}, blocking=True)
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.switch_12"}, blocking=True)
    # Switch Event
    sw_event = OWNEvent.parse("*1*1*12##")
    async_dispatcher_send(hass, f"myhome_update_{mac_addr}_1", sw_event)
    await hass.async_block_till_done()

    # Hit Climate set_temperature and hvac coverage
    await hass.services.async_call("climate", "set_temperature", {"entity_id": "climate.climate_1", "temperature": 22.0}, blocking=True)
    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": "climate.climate_1", "hvac_mode": "heat"}, blocking=True)
    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": "climate.climate_1", "hvac_mode": "cool"}, blocking=True)
    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": "climate.climate_1", "hvac_mode": "off"}, blocking=True)
    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": "climate.climate_1", "hvac_mode": "auto"}, blocking=True)
    # Climate Event
    clim_event = OWNEvent.parse("*#4*01*#14*0220*1##")
    async_dispatcher_send(hass, f"myhome_update_{mac_addr}_4", clim_event)
    await hass.async_block_till_done()

    # Hit Binary Sensor
    bs_event = OWNEvent.parse("*25*31#1*35##")
    async_dispatcher_send(hass, f"myhome_update_{mac_addr}_25", bs_event)
    await hass.async_block_till_done()

    # Hit Sensor Event
    sens_event = OWNEvent.parse("*18*51*113*114*115##")
    async_dispatcher_send(hass, f"myhome_update_{mac_addr}_18", sens_event)
    await hass.async_block_till_done()

    # Hit Button Press
    await hass.services.async_call("button", "press", {"entity_id": "button.button_1"}, blocking=True)
    await hass.async_block_till_done()
    
    # Send Dummy Dispatch update to climate 
    clim_event = OWNEvent.parse("*#4*01*0*0225##")
    async_dispatcher_send(hass, f"myhome_update_{mac_addr}_4", clim_event)
    await hass.async_block_till_done()


async def test_button_direct_coverage(hass: HomeAssistant, mock_gateway_connection):
    from custom_components.myhome.button import DisableCommandButtonEntity
    from custom_components.myhome.gateway import MyHOMEGatewayHandler
    from unittest.mock import AsyncMock

    gw = AsyncMock(spec=MyHOMEGatewayHandler)
    gw.mac = "00:11:22:33:44:55"
    
    b = DisableCommandButtonEntity(hass, "button", "Test", "id1", "1", "1", None, "B", "M", gw)
    b.hass = hass
    assert b.name == "Lock"
    await b.async_press()

async def test_climate_direct_coverage(hass: HomeAssistant, mock_gateway_connection):
    from custom_components.myhome.climate import MyHOMEClimate, HVACMode
    from custom_components.myhome.ownd.message import OWNEvent
    from unittest.mock import AsyncMock

    gw = AsyncMock()
    gw.mac = "00:11:22:33:44:55"

    c = MyHOMEClimate(hass=hass, name="name", device_id="id1", who="4", where="01", heating=True, cooling=True, fan=False, standalone=False, central=False, manufacturer="B", model="M", gateway=gw)
    c.hass = hass
    
    # Hit properties
    _ = c.target_temperature
    _ = c.current_temperature
    _ = c.current_humidity
    _ = c.hvac_action
    
    # Hit updates
    await c.async_update()
    await c.async_set_hvac_mode(HVACMode.HEAT)
    await c.async_set_hvac_mode(HVACMode.COOL)
    await c.async_set_hvac_mode(HVACMode.OFF)
    await c.async_set_hvac_mode(HVACMode.AUTO)
    await c.async_set_temperature(temperature=21.0)
    
    # Hit Events
    evt1 = OWNEvent.parse("*#4*01*#14*0220*1##")
    c.handle_event(evt1)
    evt2 = OWNEvent.parse("*#4*01*0*0225##")
    c.handle_event(evt2)

async def test_binary_sensor_direct_coverage(hass: HomeAssistant, mock_gateway_connection):
    from custom_components.myhome.binary_sensor import MyHOMEAuxiliary, MyHOMEMotionSensor
    from custom_components.myhome.ownd.message import OWNEvent
    from unittest.mock import AsyncMock

    gw = AsyncMock()
    gw.mac = "00:11:22:33:44:55"

    b1 = MyHOMEAuxiliary(hass, "au1", "aname", "aid", "25", "35", False, "door", "B", "M", gw)
    b1.hass = hass
    await b1.async_update()
    evt = OWNEvent.parse("*25*31#1*35##")
    b1.handle_event(evt)
    
    b2 = MyHOMEMotionSensor(hass, "mo1", "mname", "mid", "1", "12", False, "motion", "B", "M", gw)
    b2.hass = hass
    await b2.async_update()
    evt2 = OWNEvent.parse("*1*1*12##")
    b2.handle_event(evt2)

async def test_sensor_direct_coverage(hass: HomeAssistant, mock_gateway_connection):
    from custom_components.myhome.sensor import MyHOMEPowerSensor, MyHOMEEnergySensor
    from custom_components.myhome.ownd.message import OWNEvent
    from unittest.mock import AsyncMock

    gw = AsyncMock()
    gw.mac = "00:11:22:33:44:55"

    pw = MyHOMEPowerSensor(hass, "Power", "p1", "18", "51", "power", "B", "M", gw)
    pw.hass = hass
    en = MyHOMEEnergySensor(hass, "Energy", "e1", "18", "51", "daily-energy", "energy", "B", "M", gw)
    en.hass = hass

    evt = OWNEvent.parse("*18*51*113*114*115##")
    pw.handle_event(evt)
    en.handle_event(evt)


    # Cleanup teardown
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
