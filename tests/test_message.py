import pytest
from custom_components.myhome.ownd.message import OWNEvent, OWNSoundEvent, OWNSoundCommand

def test_own_sound_event_parsing_baseband():
    """Test parsing of WHO=16 Audio Events with baseband WHAT values (0/10)."""

    # Test Sound ON baseband (WHAT=0, General)
    message = OWNEvent.parse("*16*0*0##")
    assert isinstance(message, OWNSoundEvent)
    assert message.who == 16
    assert message.is_on is True
    assert message.is_off is False
    assert message.zone == "0"
    assert message.is_source_event is False

    # Test Sound OFF baseband (WHAT=10, Zone 21)
    message = OWNEvent.parse("*16*10*21##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is False
    assert message.is_off is True
    assert message.zone == "21"
    assert message.is_source_event is False

    # Test Source ON baseband (WHAT=0, WHERE=102 → Source 2)
    message = OWNEvent.parse("*16*0*102##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is True
    assert message.is_source_event is True
    assert message.source_id == "2"


def test_own_sound_event_parsing_stereo():
    """Test parsing of WHO=16 Audio Events with stereo WHAT values (3/13).

    BTicino Sound System 2.0 uses WHAT=3 for stereo ON and WHAT=13 for
    stereo OFF.  These must be recognised as on/off state changes alongside
    the legacy baseband values (0/10).
    """

    # Stereo ON zone (WHAT=3, WHERE=22 — kitchen zone from live capture)
    message = OWNEvent.parse("*16*3*22##")
    assert isinstance(message, OWNSoundEvent)
    assert message.who == 16
    assert message.is_on is True
    assert message.is_off is False
    assert message.zone == "22"
    assert message.is_source_event is False
    assert "switched ON" in message.human_readable_log

    # Stereo OFF zone (WHAT=13, WHERE=22)
    message = OWNEvent.parse("*16*13*22##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is False
    assert message.is_off is True
    assert message.zone == "22"
    assert "switched OFF" in message.human_readable_log

    # Stereo ON source (WHAT=3, WHERE=101 — source 1 from live capture)
    message = OWNEvent.parse("*16*3*101##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is True
    assert message.is_source_event is True
    assert message.source_id == "1"
    assert "Source 1" in message.human_readable_log

    # Stereo OFF source (WHAT=13, WHERE=103)
    message = OWNEvent.parse("*16*13*103##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_off is True
    assert message.is_source_event is True
    assert message.source_id == "3"


def test_own_sound_event_volume():
    """Test volume dimension messages."""

    # Volume Level Dimension (Volume 19 on zone 22 — from live capture)
    message = OWNEvent.parse("*#16*22*1*19##")
    assert isinstance(message, OWNSoundEvent)
    assert message.who == 16
    assert message.zone == "22"
    assert message.volume == 19
    assert message.is_on is False   # volume events don't set state
    assert message.is_off is False

    # Volume Level Dimension (Volume 15 on zone 1)
    message = OWNEvent.parse("*#16*1*1*15##")
    assert isinstance(message, OWNSoundEvent)
    assert message.zone == "1"
    assert message.volume == 15


def test_own_sound_event_amplifier_zones():
    """Test that amplifier/zone addresses (121, 122, 132) are parsed as zone events.

    These addresses appear on BTicino multi-amplifier systems.  They are NOT
    sources (101-109) and should be treated as regular zone events.
    """

    # *16*3*121## from live capture — amplifier zone, not a source
    message = OWNEvent.parse("*16*3*121##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is True
    assert message.is_source_event is False  # 121 does NOT start with "10"
    assert message.source_id is None
    assert message.zone == "121"

    # *16*3*122## from live capture
    message = OWNEvent.parse("*16*3*122##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is True
    assert message.is_source_event is False
    assert message.zone == "122"

    # *16*3*132## from live capture
    message = OWNEvent.parse("*16*3*132##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is True
    assert message.is_source_event is False
    assert message.zone == "132"


def test_own_sound_event_unknown_command():
    """Test that unrecognised WHAT values fall through to generic log."""

    message = OWNEvent.parse("*16*30*22##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is False
    assert message.is_off is False
    assert "received command: 30" in message.human_readable_log


def test_own_sound_command_generation():
    """Test generating WHO=16 Audio Commands.

    Commands must use WHAT=3 (stereo ON) and WHAT=13 (stereo OFF)
    to match BTicino Sound System 2.0 protocol.
    """

    # Status Request
    status_msg = OWNSoundCommand.status("22")
    assert str(status_msg) == "*#16*22##"

    # Turn On — must send WHAT=3 (stereo)
    on_msg = OWNSoundCommand.turn_on("11")
    assert str(on_msg) == "*16*3*11##"

    # Turn Off — must send WHAT=13 (stereo)
    off_msg = OWNSoundCommand.turn_off("11")
    assert str(off_msg) == "*16*13*11##"

    # Select Source — must send WHAT=3 (stereo)
    source_msg = OWNSoundCommand.select_source("3")
    assert str(source_msg) == "*16*3*103##"  # 100 + 3

    # Volume Up
    vol_up_msg = OWNSoundCommand.volume_up("0") # All zones
    assert str(vol_up_msg) == "*16*1001*0##"

    # Volume Down
    vol_down_msg = OWNSoundCommand.volume_down("21")
    assert str(vol_down_msg) == "*16*1000*21##"

    # Set Volume
    set_vol_msg = OWNSoundCommand.set_volume("1", 15)
    assert str(set_vol_msg) == "*#16*1*#1*15##"


def test_own_sound_live_capture_full_sequence():
    """End-to-end replay of a real SDomotica capture.

    Sequence: turn on kitchen → change volume → switch source → turn off.
    Verifies every message from the live capture is parsed correctly.
    """
    capture = [
        ("*16*13*22##",     {"is_on": False, "is_off": True,  "zone": "22"}),
        ("*#16*22*1*19##",  {"volume": 19, "zone": "22"}),
        ("*16*3*101##",     {"is_on": True,  "is_source_event": True, "source_id": "1"}),
        ("*16*3*121##",     {"is_on": True,  "is_source_event": False, "zone": "121"}),
        ("*16*3*122##",     {"is_on": True,  "is_source_event": False, "zone": "122"}),
        ("*#16*22*1*20##",  {"volume": 20, "zone": "22"}),
        ("*#16*22*1*21##",  {"volume": 21, "zone": "22"}),
        ("*#16*22*1*20##",  {"volume": 20, "zone": "22"}),
        ("*#16*22*1*19##",  {"volume": 19, "zone": "22"}),
        ("*16*3*22##",      {"is_on": True,  "is_off": False, "zone": "22"}),
        ("*16*3*132##",     {"is_on": True,  "is_source_event": False, "zone": "132"}),
    ]

    for raw, expected in capture:
        msg = OWNEvent.parse(raw)
        assert isinstance(msg, OWNSoundEvent), f"Failed to parse {raw} as OWNSoundEvent"
        for attr, value in expected.items():
            actual = getattr(msg, attr)
            assert actual == value, (
                f"{raw}: expected {attr}={value!r}, got {actual!r}"
            )
