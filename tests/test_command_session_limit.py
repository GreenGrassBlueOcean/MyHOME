"""The configured command-session count is capped by the gateway profile (issue #425)."""
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import DOMAIN
from custom_components.myhome.gateway import command_session_limit

MAC = "00:03:50:02:1b:35"


@pytest.mark.parametrize(
    ("model", "limit"),
    [
        ("MH200N", 1),
        ("MH200", 1),  # aliased to the MH200N profile
        ("MH202", 2),
        ("F454", 4),
        ("MyHomeServer1", 4),
        ("Unknown Gateway", None),  # generic profile: its limit is a guess
        (None, None),
    ],
)
def test_command_session_limit(model, limit) -> None:
    assert command_session_limit(model) == limit


def _entry(model: str, workers: int) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.0.2.40", "port": 20000, "password": "12345", "mac": MAC, "name": model},
        options={"command_worker_count": workers, "generate_events": False},
        unique_id=MAC,
    )


def _gateway_patches():
    return [
        patch("custom_components.myhome.gateway.OWNSession.test_connection", return_value={"Success": True, "Message": None}),
        patch("custom_components.myhome.gateway.MyHOMEGatewayHandler.listening_loop"),
        patch("custom_components.myhome.gateway.MyHOMEGatewayHandler.send"),
        patch("custom_components.myhome.gateway.MyHOMEGatewayHandler.send_status_request"),
    ]


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> list[int]:
    entry.add_to_hass(hass)
    started: list[int] = []

    async def fake_sending_loop(self, worker_id: int) -> None:
        started.append(worker_id)

    patches = _gateway_patches()
    patches.append(patch("custom_components.myhome.gateway.MyHOMEGatewayHandler.sending_loop", fake_sending_loop))
    for p in patches:
        p.start()
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    finally:
        for p in patches:
            p.stop()
    return started


async def test_setup_caps_workers_to_gateway_limit(hass: HomeAssistant, caplog) -> None:
    started = await _setup(hass, _entry("MH200N", 3))

    assert started == [0]
    assert "accepts at most 1 command session(s) but 3 are configured; using 1" in caplog.text


async def test_setup_keeps_workers_within_limit(hass: HomeAssistant, caplog) -> None:
    started = await _setup(hass, _entry("F454", 3))

    assert sorted(started) == [0, 1, 2]
    assert "command session(s) but" not in caplog.text


async def test_setup_keeps_workers_for_unknown_model(hass: HomeAssistant, caplog) -> None:
    started = await _setup(hass, _entry("Unknown Gateway", 2))

    assert sorted(started) == [0, 1]
    assert "command session(s) but" not in caplog.text


async def test_options_flow_rejects_workers_above_gateway_limit(hass: HomeAssistant) -> None:
    entry = _entry("MH200N", 1)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["description_placeholders"]["session_limit"] == "1"

    rejected = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"command_worker_count": 3, "generate_events": False, "address": "192.0.2.40", "password": "12345"},
    )
    assert rejected["type"] == FlowResultType.FORM
    assert rejected["errors"] == {"command_worker_count": "worker_count_above_gateway_limit"}
    assert rejected["description_placeholders"] == {"session_limit": "1", "model": "MH200N"}

    accepted = await hass.config_entries.options.async_configure(
        rejected["flow_id"],
        user_input={"command_worker_count": 1, "generate_events": False, "address": "192.0.2.40", "password": "12345"},
    )
    assert accepted["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["command_worker_count"] == 1


async def test_options_flow_checks_the_newly_chosen_model(hass: HomeAssistant) -> None:
    """Switching an MH200N entry to an F454 in the same submit allows 3 sessions."""
    entry = _entry("MH200N", 1)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", return_value=True):
        accepted = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "command_worker_count": 3,
                "generate_events": False,
                "address": "192.0.2.40",
                "password": "12345",
                "name": "F454",
            },
        )
    assert accepted["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["command_worker_count"] == 3
