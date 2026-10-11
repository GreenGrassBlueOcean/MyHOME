"""WHO=22 reports reaching a WHO=16 tuner entity.

The F500 mirrors its WHO=16 reports onto WHO=22 (source address ``5#2#S``). The
frames are the ones recorded from a live F500N on an MH200N, in
``tests/fixtures/traces/f500_tuner``.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_MAC
from OWNd.message import OWNMessage, OWNSoundEvent

from custom_components.myhome.data import MyHOMERuntimeData
from custom_components.myhome.sound_source import (
    MyHOMESoundSource,
    who22_source_id,
    who22_tuner_listener,
)
from tests.conftest import attach_platform


def _frame(where, where_param, dimension, *values, who="22"):
    """A WHO=22 frame as the gateway handler hands it on."""
    return SimpleNamespace(
        who=who,
        where=where,
        where_param=list(where_param),
        dimension=dimension,
        dimension_value=list(values),
    )


def _tuner(hass, gateway, source=1):
    entity = MyHOMESoundSource(
        hass=hass,
        name=f"Radio {source}",
        device_id=f"10{source}#16",
        who="16",
        where=f"10{source}",
        manufacturer="BTicino",
        model="Audio Source",
        gateway=gateway,
    )
    entity.hass = hass
    entity.entity_id = f"media_player.radio_{source}"
    entity.async_schedule_update_ha_state = MagicMock()
    entry = MagicMock()
    entry.data = {CONF_MAC: gateway.mac}
    entry.runtime_data = MyHOMERuntimeData(gateway=gateway)
    attach_platform(entity, entry)
    return entity


@pytest.fixture
def gateway():
    gw = MagicMock()
    gw.mac = "00:11:22:33:44:55"
    gw.log_id = "[MYHOME gateway - 192.168.1.5]"
    gw.send = AsyncMock()
    gw.send_status_request = AsyncMock()
    return gw


@pytest.fixture
def tuner(hass, gateway):
    return _tuner(hass, gateway)


def test_frequency_and_preset_report(tuner):
    tuner.handle_who22_event(_frame("5", ["2", "1"], 11, "1", "9620", "2"))
    assert tuner.extra_state_attributes == {"frequency": 96.2, "station": 2}
    assert tuner.source == "Station 2"


def test_frequency_without_a_preset_clears_the_previous_station(tuner):
    tuner.handle_who22_event(_frame("5", ["2", "1"], 11, "1", "9620", "2"))
    tuner.handle_who22_event(_frame("5", ["2", "1"], 5, "1", "8950"))
    assert tuner.extra_state_attributes == {"frequency": 89.5}
    assert tuner.source is None


def test_a_new_frequency_drops_the_old_stations_text(tuner):
    tuner.handle_who22_event(_frame("5", ["2", "1"], 10, *"75*82*79*78*69*72*73*84".split("*")))
    assert tuner.media_title == "KRONEHIT"
    tuner.handle_who22_event(_frame("5", ["2", "1"], 5, "1", "9030"))
    assert tuner.media_title is None


def test_rds_text_and_its_blanking_while_retuning(tuner):
    tuner.handle_who22_event(_frame("5", ["2", "1"], 10, *"75*82*79*78*69*72*73*84".split("*")))
    assert tuner.media_title == "KRONEHIT"
    tuner.handle_who22_event(_frame("5", ["2", "1"], 10, *["32"] * 8))
    assert tuner.media_title is None


def test_a_twelve_code_rds_glitch_leaves_the_title_alone(tuner):
    tuner.handle_who22_event(_frame("5", ["2", "1"], 10, *"75*82*79*78*69*72*73*84".split("*")))
    tuner.handle_who22_event(
        _frame("5", ["2", "1"], 10, *"42*42*79*79*69*42*79*79*69*42*42*32".split("*"))
    )
    assert tuner.media_title == "KRONEHIT"


def test_station_report_from_a_query_reply(tuner):
    tuner.handle_who22_event(_frame("2", ["1"], 6, "3"))
    assert tuner.extra_state_attributes == {"station": 3}


def test_mirrored_who16_and_who22_reports_agree(tuner):
    """The same fact on both families lands on one state, whichever arrives first."""
    tuner.handle_event(OWNMessage.parse("*#16*101*6*0*96200##"))
    tuner.handle_who22_event(_frame("5", ["2", "1"], 5, "1", "9620"))
    tuner.handle_event(OWNMessage.parse("*#16*101*7*0*2##"))
    tuner.handle_who22_event(_frame("5", ["2", "1"], 11, "1", "9620", "2"))
    assert isinstance(OWNMessage.parse("*#16*101*6*0*96200##"), OWNSoundEvent)
    assert tuner.extra_state_attributes == {"frequency": 96.2, "station": 2}


@pytest.mark.parametrize(
    ("where", "param", "expected"),
    [
        ("5", ["2", "1"], 1),
        ("5", ["2", "4"], 4),
        ("2", ["3"], 3),
        ("3", ["4", "1"], None),  # an amplifier, not a source
        ("6", [], None),
        ("5", ["3", "1"], None),
    ],
)
def test_who22_source_id_reads_the_address(where, param, expected):
    assert who22_source_id(_frame(where, param, 5, "1", "9620")) == expected


def test_only_who22_frames_are_placed():
    assert who22_source_id(_frame("5", ["2", "1"], 5, "1", "9620", who="16")) is None


def test_the_listener_feeds_the_declared_tuner_and_nothing_else(hass, gateway):
    first, second = _tuner(hass, gateway, 1), _tuner(hass, gateway, 2)
    listener = who22_tuner_listener([first, second])
    listener(_frame("5", ["2", "2"], 5, "1", "10350"))
    listener(_frame("5", ["2", "9"], 5, "1", "8880"))  # no such tuner declared
    assert first.extra_state_attributes == {}
    assert second.extra_state_attributes == {"frequency": 103.5}


def test_a_who22_frame_of_unknown_meaning_changes_nothing(tuner):
    tuner.handle_who22_event(_frame("5", ["2", "1"], 99, "1"))
    tuner.handle_who22_event(_frame("5", ["2", "1"], None))
    assert tuner.extra_state_attributes == {}


def test_real_owndiffusion_event_is_placed_when_owNd_parses_who22():
    """With an OWNd that parses WHO=22, its own reading of the address agrees."""
    event = OWNMessage.parse("*#22*5#2#1*11*1*9620*2##")
    if str(getattr(event, "who", "")) != "22" or not hasattr(event, "source_id"):
        pytest.skip("this OWNd does not parse WHO=22")
    assert who22_source_id(event) == 1

def test_entity_picture_follows_the_live_frequency(hass, gateway):
    tuner = _tuner(hass, gateway)
    tuner._pictures = {96200: "/local/radio/one.png"}
    assert tuner.entity_picture is None  # nothing heard yet
    tuner.handle_who22_event(_frame("5", ["2", "1"], 5, "1", "9620"))
    assert tuner.entity_picture == "/local/radio/one.png"
    tuner.handle_who22_event(_frame("5", ["2", "1"], 5, "1", "8950"))
    assert tuner.entity_picture is None  # an unlisted station shows no picture
