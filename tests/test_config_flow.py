"""Test the MyHOME config flow."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.myhome.const import DOMAIN


async def test_form(hass: HomeAssistant) -> None:
    """Test we get the form and create an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] is None

    with patch(
        "custom_components.myhome.ownd.connection.OWNSession.test_gateway",
        return_value={"Success": True},
    ), patch(
        "custom_components.myhome.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry, patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[]
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["step_id"],
            {
                "host": "1.1.1.1",
                "port": 20000,
                "password": "test",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "MyHome Gateway - 1.1.1.1" # Fallback if no serial
    assert result2["data"] == {
        "host": "1.1.1.1",
        "port": 20000,
        "password": "test",
        "mac": "1.1.1.1",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.myhome.ownd.connection.OWNSession.test_gateway",
        return_value={"Success": False, "Message": "connection_refused"},
    ), patch(
        "custom_components.myhome.config_flow.find_gateways",
        return_value=[]
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["step_id"],
            {
                "host": "1.1.1.1",
                "port": 20000,
                "password": "test",
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}
