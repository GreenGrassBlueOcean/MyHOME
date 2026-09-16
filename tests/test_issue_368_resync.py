"""Test issue #368 PR A: debounced re-sync for group / area / general frames."""

from unittest.mock import AsyncMock, MagicMock, patch

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from OWNd.message import OWNMessage
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.myhome.const import (
    CONF_BROADCAST_RESYNC,
    DOMAIN,
    area_of_where,
)
from custom_components.myhome.gateway import MyHOMEGatewayHandler

MAC = "00:03:50:00:00:01"


def test_area_of_where():
    """Test area_of_where logic."""
    assert area_of_where("12") == "1"
    assert area_of_where("0115") == "1"
    assert area_of_where("0015") == "00"
    assert area_of_where("1003") == "100"
    assert area_of_where("invalid") is None
    assert area_of_where(None) is None


def _entry(hass: HomeAssistant, *, broadcast_resync: bool = True) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.5",
            CONF_PORT: 20000,
            CONF_PASSWORD: "open",
            CONF_MAC: MAC,
        },
        options={CONF_BROADCAST_RESYNC: broadcast_resync},
    )
    entry.add_to_hass(hass)
    return entry


def _handler(hass: HomeAssistant, entry: MockConfigEntry, *, broadcast_resync: bool = True) -> MyHOMEGatewayHandler:
    with patch("custom_components.myhome.gateway.OWNGateway"):
        handler = MyHOMEGatewayHandler(hass, entry, generate_events=False, broadcast_resync=broadcast_resync)
        handler.gateway.mac = MAC
        handler.send_status_request = AsyncMock()
        return handler


async def _advance(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + dt_util.dt.timedelta(seconds=1))
    await hass.async_block_till_done()


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    return _entry(hass)


@pytest.fixture
def handler(hass: HomeAssistant, entry: MockConfigEntry) -> MyHOMEGatewayHandler:
    return _handler(hass, entry)


@pytest.mark.asyncio
async def test_resync_group(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """A group frame, followed by silence, sweeps the group's own status."""
    msg = OWNMessage.parse("*1*1*#6##")

    await handler._process_message(msg)
    await _advance(hass)

    handler.send_status_request.assert_called_once()
    arg = handler.send_status_request.call_args[0][0]
    assert str(arg) == "*#1*#6##"


@pytest.mark.asyncio
async def test_resync_group_with_echo(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """A point-to-point frame inside the debounce window cancels the sweep."""
    msg_grp = OWNMessage.parse("*1*1*#6##")
    await handler._process_message(msg_grp)

    msg_pt = OWNMessage.parse("*1*1*11##")
    await handler._process_message(msg_pt)

    await _advance(hass)

    handler.send_status_request.assert_not_called()


@pytest.mark.asyncio
async def test_resync_area(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """A plain area frame ('3') sweeps its own raw WHERE."""
    msg = OWNMessage.parse("*1*0*3##")

    await handler._process_message(msg)
    await _advance(hass)

    handler.send_status_request.assert_called_once()
    arg = handler.send_status_request.call_args[0][0]
    assert str(arg) == "*#1*3##"


@pytest.mark.asyncio
async def test_resync_area_00_never_sends_banned_general_request(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """Area '00' must sweep '*#1*00##', never the banned '*#1*0##'."""
    msg = OWNMessage.parse("*1*1*00##")

    await handler._process_message(msg)
    await _advance(hass)

    handler.send_status_request.assert_called_once()
    arg = handler.send_status_request.call_args[0][0]
    assert str(arg) == "*#1*00##"
    assert str(arg) != "*#1*0##"


@pytest.mark.asyncio
async def test_resync_area_100_targets_area_ten(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """Area '100' (area 10) must sweep '*#1*100##', not the point address '*#1*10##'."""
    msg = OWNMessage.parse("*1*1*100##")

    await handler._process_message(msg)
    await _advance(hass)

    handler.send_status_request.assert_called_once()
    arg = handler.send_status_request.call_args[0][0]
    assert str(arg) == "*#1*100##"
    assert str(arg) != "*#1*10##"


@pytest.mark.asyncio
async def test_resync_general(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """A general frame sweeps every known light area, never the general itself."""
    msg = OWNMessage.parse("*1*1*0##")

    with patch.object(handler, "_known_light_areas", return_value=["1", "00", "100"]):
        await handler._process_message(msg)
        await _advance(hass)

    assert handler.send_status_request.call_count == 3
    frames = {str(call[0][0]) for call in handler.send_status_request.call_args_list}
    assert frames == {"*#1*1##", "*#1*00##", "*#1*100##"}
    assert "*#1*0##" not in frames


@pytest.mark.asyncio
async def test_known_light_areas_from_registry(hass: HomeAssistant, entry: MockConfigEntry):
    """_known_light_areas reads real light registry entries for this config entry."""
    handler = _handler(hass, entry)
    registry = er.async_get(hass)
    for where in ("12", "0015", "1003", "#6"):
        registry.async_get_or_create(
            "light", DOMAIN, f"{MAC}-1-{where}", config_entry=entry,
        )
    # A sensor sharing WHO=1 addressing must not be treated as a light area.
    registry.async_get_or_create(
        "binary_sensor", DOMAIN, f"{MAC}-1-14", config_entry=entry,
    )
    # A unique id with no device-id part (parse_unique_id -> empty key) is skipped.
    registry.async_get_or_create(
        "light", DOMAIN, f"{MAC}-", config_entry=entry,
    )

    assert handler._known_light_areas() == ["00", "1", "100"]


@pytest.mark.asyncio
async def test_resync_debounces_repeated_group_frames(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """Two group frames for the same group inside the window produce one sweep."""
    await handler._process_message(OWNMessage.parse("*1*1*#6##"))
    await handler._process_message(OWNMessage.parse("*1*0*#6##"))

    await _advance(hass)

    handler.send_status_request.assert_called_once()


@pytest.mark.asyncio
async def test_resync_off(hass: HomeAssistant):
    """The option disables scheduling entirely."""
    entry = _entry(hass, broadcast_resync=False)
    handler = _handler(hass, entry, broadcast_resync=False)

    await handler._process_message(OWNMessage.parse("*1*1*#6##"))
    await _advance(hass)

    handler.send_status_request.assert_not_called()


@pytest.mark.asyncio
async def test_close_listener_cancels_pending_resync(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """Closing the listener cancels a pending sweep so it never fires."""
    await handler._process_message(OWNMessage.parse("*1*1*#6##"))
    assert handler._resync_timers

    await handler.close_listener()
    await _advance(hass)

    handler.send_status_request.assert_not_called()
    assert not handler._resync_timers


def test_known_light_areas_without_valid_entry_id(hass: HomeAssistant):
    """A config entry without a usable entry_id yields no areas."""
    entry = MagicMock()
    entry.entry_id = None
    with patch("custom_components.myhome.gateway.OWNGateway"):
        handler = MyHOMEGatewayHandler(hass, entry, generate_events=False)
        handler.gateway.mac = MAC

    assert handler._known_light_areas() == []


@pytest.mark.asyncio
async def test_resync_golden_mh200_sweep_burst(hass: HomeAssistant, handler: MyHOMEGatewayHandler):
    """
    Test that a real-world burst of responses from an MH200 during an area status sweep
    (which can include interleaved WHO=2 automation events, WHO=13 gateway events,
    and WHO=1001 diagnostic events) is processed safely without triggering further resync loops.
    """
    golden_frames = [
        "*1*0*11##",
        "*2*0*11#4#02##",
        "*1*0*12##",
        "*1*0*21##",
        "*1*0*31##",
        "*1*0*29##",
        "*1*0*32##",
        "*1*0*41##",
        "*1*0*51##",
        "*1*0*42##",
        "*1*0*52##",
        "*1*0*61##",
        "*1*0*71##",
        "*1*1*81##",
        "*1*0*82##",
        "*1*0*83##",
        "*1*10*62##",
        "*#1001*74*11*111110111111111111110111##",
        "*#13**15*4##",
        "*2*0*15#4#02##"
    ]

    for frame in golden_frames:
        msg = OWNMessage.parse(frame)
        if msg is not None:
            await handler._process_message(msg)

    await _advance(hass)

    # Point-to-point status reports and interleaved events must NOT spawn broad sweeps.
    handler.send_status_request.assert_not_called()
