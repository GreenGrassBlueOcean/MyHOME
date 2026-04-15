"""Test the MyHOME config flow."""
from unittest.mock import patch, MagicMock

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.myhome.const import DOMAIN


async def test_form(hass: HomeAssistant) -> None:
    """Test the full config flow: user -> custom -> test_connection creates an entry."""
    with patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[]
    ), patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        return_value={"Success": True},
    ), patch(
        "custom_components.myhome.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        # Step 1: user step – returns a form with a "serial" dropdown
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        # Step 2: select "Custom" (serial = 00:00:00:00:00:00)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"serial": "00:00:00:00:00:00"},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "custom"

        # Step 3: fill custom form with address/port/serialNumber/modelName
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                "address": "192.168.1.135",
                "port": 20000,
                "serialNumber": "00:03:50:00:12:34",
                "modelName": "F454",
            },
        )
        await hass.async_block_till_done()

    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert "Gateway" in result3["title"]
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect via abort."""
    with patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[]
    ), patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        return_value={"Success": False, "Message": "connection_refused"},
    ):
        # Step 1: user step
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Step 2: select Custom
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"serial": "00:00:00:00:00:00"},
        )

        # Step 3: fill custom form
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                "address": "192.168.1.135",
                "port": 20000,
                "serialNumber": "00:03:50:00:12:34",
                "modelName": "F454",
            },
        )

    # connection_refused should cause an abort
    assert result3["type"] == FlowResultType.ABORT
    assert result3["reason"] == "connection_refused"


async def test_form_already_configured(hass: HomeAssistant) -> None:
    """Test aborting when the gateway is already configured."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.135",
            "port": 20000,
            "mac": "00:03:50:00:12:34",
        },
        unique_id="00:03:50:00:12:34",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[]
    ), patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        return_value={"Success": True},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"serial": "00:00:00:00:00:00"},
        )

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                "address": "192.168.1.135",
                "port": 20000,
                "serialNumber": "00:03:50:00:12:34",
                "modelName": "F454",
            },
        )

    assert result3["type"] == FlowResultType.ABORT
    assert result3["reason"] == "already_configured"


async def test_form_discovery(hass: HomeAssistant) -> None:
    """Test user selecting a discovered gateway."""
    mock_discovery = {
        "00:03:50:00:12:34": {
            "address": "192.168.1.135",
            "port": 20000,
            "serialNumber": "00:03:50:00:12:34",
            "modelName": "F454"
        }
    }
    with patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[mock_discovery["00:03:50:00:12:34"]]
    ), patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        return_value={"Success": True},
    ), patch(
        "custom_components.myhome.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"serial": "00:03:50:00:12:34"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert "F454" in result2["title"]
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_discovery_already_configured(hass: HomeAssistant) -> None:
    """Test aborting when a discovered gateway is already selected."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.135",
            "port": 20000,
            "mac": "00:03:50:00:12:34",
        },
        unique_id="00:03:50:00:12:34",
    )
    entry.add_to_hass(hass)

    mock_discovery = {
        "00:03:50:00:12:34": {
            "address": "192.168.1.135",
            "port": 20000,
            "serialNumber": "00:03:50:00:12:34",
            "modelName": "F454"
        }
    }
    with patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[mock_discovery["00:03:50:00:12:34"]]
    ), patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        return_value={"Success": True},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        # Note: if it's already configured, the flow filters it from dropdown, but if manually passed:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"serial": "00:03:50:00:12:34"},
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test options config flow."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.135",
            "password": "pass",
            "mac": "00:03:50:00:12:34",
        },
        options={
            "command_worker_count": 1,
            "generate_events": False,
        },
        unique_id="00:03:50:00:12:34",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.myhome.config_flow.find_gateways"):
        # Initialize option flow
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Submit updated options
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "command_worker_count": 3,
            "generate_events": True,
            "address": "192.168.1.136",
            "password": "new_password"
        },
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["command_worker_count"] == 3
    assert entry.options["generate_events"] is True
    assert entry.data["host"] == "192.168.1.136"
    assert entry.data["password"] == "new_password"

    # Test invalid ip address config error
    result_invalid = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "command_worker_count": 3,
            "generate_events": True,
            "address": "invalid_ip",
            "password": "new_password"
        },
    )
    assert result_invalid["type"] == FlowResultType.FORM
    assert result_invalid["errors"]["address"] == "invalid_ip"


async def test_ssdp_discovery(hass: HomeAssistant) -> None:
    """Test SSDP discovery flow."""
    class SsdpServiceInfo:
        def __init__(self, ssdp_usn, ssdp_st, ssdp_location, upnp, ssdp_headers):
            self.ssdp_usn = ssdp_usn
            self.ssdp_st = ssdp_st
            self.ssdp_location = ssdp_location
            self.upnp = upnp
            self.ssdp_headers = ssdp_headers

    ssdp_info = SsdpServiceInfo(
        ssdp_usn="mock_usn",
        ssdp_st="mock_st",
        ssdp_location="http://192.168.1.135:49153/description.xml",
        upnp={
            "modelName": "F454",
            "serialNumber": "00:03:50:00:12:34",
            "friendlyName": "Gateway",
            "UDN": "uuid",
            "modelNumber": "2.0"
        },
        ssdp_headers={"_host": "192.168.1.135"}
    )

    with patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        return_value={"Success": True},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=ssdp_info
        )

    # Note: the gateway discovery dict doesn't specify port, so it gets set to 20000 in async_step_ssdp
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "192.168.1.135"


async def test_reauth_flow(hass: HomeAssistant) -> None:
    """Test reauth flow triggered by a password error."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.135",
            "mac": "00:03:50:00:12:34",
            "password": "wrong"
        },
        unique_id="00:03:50:00:12:34",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.myhome.config_flow.MyHOMEGatewayHandler"
    ) as mock_gateway_handler:
        # Provide the mock gateway host/serial properties 
        mock_gateway_handler.return_value.gateway.host = "192.168.1.135"
        mock_gateway_handler.return_value.gateway.model = "F454"
        mock_gateway_handler.return_value.gateway.serial = "00:03:50:00:12:34"
        mock_gateway_handler.return_value.gateway.password = "wrong"

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "password"

    with patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        return_value={"Success": True},
    ), patch(
        "custom_components.myhome.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "correct_password"},
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.data["password"] == "correct_password"

async def test_password_required_and_error(hass: HomeAssistant) -> None:
    """Test manual connection with password error states."""
    with patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[]
    ), patch(
        "custom_components.myhome.config_flow.OWNSession.test_connection",
        side_effect=[
            {"Success": False, "Message": "password_required"},
            {"Success": False, "Message": "password_error"},
            {"Success": True}
        ]
    ), patch(
        "custom_components.myhome.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"serial": "00:00:00:00:00:00"},
        )
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                "address": "192.168.1.135",
                "port": 20000,
                "serialNumber": "00:03:50:00:12:34",
                "modelName": "F454",
            },
        )
        # 1st attempt: password required
        assert result3["type"] == FlowResultType.FORM
        assert result3["step_id"] == "password"

        # 2nd attempt: password error
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {"password": "wrong_password"}
        )
        assert result4["type"] == FlowResultType.FORM
        assert result4["step_id"] == "password"
        assert result4["errors"]["password"] == "password_error"

        # 3rd attempt: successful setup
        result5 = await hass.config_entries.flow.async_configure(
            result4["flow_id"],
            {"password": "correct_password"}
        )
        assert result5["type"] == FlowResultType.CREATE_ENTRY
