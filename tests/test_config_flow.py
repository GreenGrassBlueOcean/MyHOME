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
