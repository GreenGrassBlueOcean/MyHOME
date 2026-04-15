import pytest
from message_target import OWNEvent, OWNSoundEvent, OWNSoundCommand

def test_own_sound_event_parsing():
    """Test parsing of WHO=16 Audio Events."""
    
    # Test Sound ON (General)
    message = OWNEvent.parse("*16*0*0##")
    assert isinstance(message, OWNSoundEvent)
    assert message.who == 16
    assert message.is_on is True
    assert message.zone == "0"
    assert message.is_source_event is False
    
    # Test Sound OFF (Zone 21)
    message = OWNEvent.parse("*16*10*21##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is False
    assert message.is_off is True
    assert message.zone == "21"
    assert message.is_source_event is False

    # Test Source ON (It is a source broadcast)
    message = OWNEvent.parse("*16*0*102##")
    assert isinstance(message, OWNSoundEvent)
    assert message.is_on is True
    assert message.is_source_event is True
    assert message.source_id == "2"

def test_own_sound_command_generation():
    """Test generating WHO=16 Audio Commands."""
    
    # Status Request
    status_msg = OWNSoundCommand.status("22")
    assert str(status_msg) == "*#16*22##"
    
    # Turn On
    on_msg = OWNSoundCommand.turn_on("11")
    assert str(on_msg) == "*16*0*11##"
    
    # Turn Off
    off_msg = OWNSoundCommand.turn_off("11")
    assert str(off_msg) == "*16*10*11##"

    # Select Source
    source_msg = OWNSoundCommand.select_source("3")
    assert str(source_msg) == "*16*0*103##"  # 100 + 3
    
    # Volume Up
    vol_up_msg = OWNSoundCommand.volume_up("0") # All zones
    assert str(vol_up_msg) == "*16*1001*0##"
    
    # Volume Down
    vol_down_msg = OWNSoundCommand.volume_down("21")
    assert str(vol_down_msg) == "*16*1000*21##"
