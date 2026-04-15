"""Tests for the MyHOME custom component initialization."""
import pytest
from unittest.mock import patch, AsyncMock
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import DOMAIN
from custom_components.myhome.ownd.connection import OWNGateway


async def test_setup_entry_success(hass: HomeAssistant):
    """Test successful setup of the integration via MockConfigEntry."""
    # 1. Provide a realistic connection mock that succeeds
    with patch(
        "custom_components.myhome.gateway.OWNSession.test_connection",
        return_value={"Success": True, "Message": None}
    ), patch(
        "custom_components.myhome.gateway.MyHOMEGatewayHandler.listening_loop"
    ), patch(
        "custom_components.myhome.gateway.MyHOMEGatewayHandler.sending_loop"
    ):
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "host": "192.168.0.35",
                "port": 20000,
                "password": "pass",
                "mac": "00:03:50:00:12:34",
                "ssdp_location": "http://192.168.0.35:49153/description.xml",
                "ssdp_st": "urn:schemas-upnp-org:device:Basic:1",
                "deviceType": "urn:schemas-upnp-org:device:Basic:1",
                "friendly_name": "MyHOME Gateway",
                "manufacturer": "BTicino",
                "manufacturerURL": "http://www.bticino.com",
                "name": "F454",
                "firmware": "2.0.0",
                "UDN": "uuid:12345678-1234-1234-1234-123456789012"
            },
            unique_id="00:03:50:00:12:34",
        )
        config_entry.add_to_hass(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Check entry loaded
        assert config_entry.state is ConfigEntryState.LOADED

        # Cleanup
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
        assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_connection_failed(hass: HomeAssistant):
    """Test failing setup due to bad password or timeout."""
    with patch(
        "custom_components.myhome.gateway.OWNSession.test_connection",
        return_value={"Success": False, "Message": "password_error"}
    ):
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "host": "192.168.0.35",
                "port": 20000,
                "password": "wrong",
                "mac": "00:03:50:00:12:34",
                "ssdp_location": "http://192.168.0.35:49153/description.xml",
                "ssdp_st": "urn:schemas-upnp-org:device:Basic:1",
                "deviceType": "urn:schemas-upnp-org:device:Basic:1",
                "friendly_name": "MyHOME Gateway",
                "manufacturer": "BTicino",
                "manufacturerURL": "http://www.bticino.com",
                "name": "F454",
                "firmware": "2.0.0",
                "UDN": "uuid:12345678-1234-1234-1234-123456789012"
            },
            unique_id="00:03:50:00:12:35",
        )
        config_entry.add_to_hass(hass)

        result = await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Should return False
        assert not result
        assert config_entry.state is ConfigEntryState.SETUP_ERROR
