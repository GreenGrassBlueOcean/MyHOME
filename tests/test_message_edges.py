"""Tests targeting remaining uncovered branches in message.py to maximize coverage."""
import pytest
import datetime
from custom_components.myhome.ownd.message import (
    OWNMessage,
    OWNEvent,
    OWNCommand,
    OWNSignaling,
    OWNLightingEvent,
    OWNAutomationEvent,
    OWNHeatingEvent,
    OWNAlarmEvent,
    OWNAuxEvent,
    OWNCENEvent,
    OWNCENPlusEvent,
    OWNScenarioEvent,
    OWNSceneEvent,
    OWNEnergyEvent,
    OWNGatewayEvent,
    OWNGatewayCommand,
    OWNDryContactEvent,
    OWNSoundEvent,
    OWNSoundCommand,
    OWNLightingCommand,
    OWNAutomationCommand,
    OWNHeatingCommand,
    OWNEnergyCommand,
    OWNDryContactCommand,
    OWNAVCommand,
    MESSAGE_TYPE_ACTIVE_POWER,
    MESSAGE_TYPE_ENERGY_TOTALIZER,
    MESSAGE_TYPE_HOURLY_CONSUMPTION,
    MESSAGE_TYPE_DAILY_CONSUMPTION,
    MESSAGE_TYPE_MONTHLY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION,
    MESSAGE_TYPE_MODE,
    MESSAGE_TYPE_ACTION,
    CLIMATE_MODE_OFF,
    CLIMATE_MODE_HEAT,
    CLIMATE_MODE_COOL,
    CLIMATE_MODE_AUTO,
)


# ── OWNMessage Base Class Parsing ──────────────────────────────────────────

class TestOWNMessageBase:
    """Cover all regex paths in OWNMessage.__init__."""

    def test_dimension_request_reply(self):
        """*#WHO*WHERE*DIMENSION*VAL1*VALn## pattern."""
        msg = OWNMessage("*#4*1*0*0225##")
        assert msg.is_valid is True
        assert msg.who == 4

    def test_dimension_writing(self):
        """*#WHO*WHERE*#DIMENSION*VAL1*VALn## pattern."""
        msg = OWNMessage("*#1*21*#1*150*0##")
        assert msg.is_valid is True

    def test_dimension_request(self):
        """*#WHO*WHERE*DIMENSION## pattern."""
        msg = OWNMessage("*#4*1*0##")
        assert msg.is_valid is True

    def test_command_translation(self):
        """WHAT=1000 should set family to COMMAND_TRANSLATION."""
        msg = OWNMessage("*1*1000*21##")
        assert msg.is_valid is True

    def test_invalid_message(self):
        msg = OWNMessage("not_a_valid_message")
        assert msg.is_valid is False

    def test_message_parse_status(self):
        result = OWNMessage.parse("*1*1*21##")
        assert isinstance(result, OWNLightingEvent)

    def test_message_parse_signaling_ack(self):
        result = OWNMessage.parse("*#*1##")
        assert isinstance(result, OWNSignaling)

    def test_message_parse_signaling_nack(self):
        result = OWNMessage.parse("*#*0##")
        assert isinstance(result, OWNSignaling)

    def test_message_parse_unknown(self):
        result = OWNMessage.parse("garbage")
        assert result is None

    def test_message_parse_command_session(self):
        result = OWNMessage.parse("*99*0##")
        assert isinstance(result, OWNSignaling)

    def test_message_parse_event_session(self):
        result = OWNMessage.parse("*99*1##")
        assert isinstance(result, OWNSignaling)

    def test_where_param_parsing(self):
        """Messages with WHERE parameters (e.g. #zone#param)."""
        msg = OWNMessage("*#4*0#1*0*0225##")
        assert msg.is_valid is True


# ── Heating Event Edge Cases ──────────────────────────────────────────────

class TestHeatingEdgeCases:
    """Cover remaining branches in OWNHeatingEvent."""

    def test_mode_off_variant_103(self):
        msg = OWNEvent.parse("*4*103*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_OFF

    def test_mode_off_variant_203(self):
        msg = OWNEvent.parse("*4*203*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_OFF

    def test_mode_off_variant_102(self):
        msg = OWNEvent.parse("*4*102*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_OFF

    def test_mode_off_variant_202(self):
        msg = OWNEvent.parse("*4*202*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_OFF

    def test_mode_off_variant_302(self):
        msg = OWNEvent.parse("*4*302*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_OFF

    def test_mode_cool_variant_210(self):
        msg = OWNEvent.parse("*4*210*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_COOL

    def test_mode_cool_variant_211(self):
        msg = OWNEvent.parse("*4*211*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_COOL

    def test_mode_cool_variant_215(self):
        msg = OWNEvent.parse("*4*215*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_COOL

    def test_mode_cool_weekly_2101(self):
        msg = OWNEvent.parse("*4*2101*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_COOL

    def test_mode_cool_scenario_2201(self):
        msg = OWNEvent.parse("*4*2201*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_COOL

    def test_mode_heat_variant_110(self):
        msg = OWNEvent.parse("*4*110*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_HEAT

    def test_mode_heat_variant_111(self):
        msg = OWNEvent.parse("*4*111*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_HEAT

    def test_mode_heat_variant_115(self):
        msg = OWNEvent.parse("*4*115*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_HEAT

    def test_mode_heat_weekly_1101(self):
        msg = OWNEvent.parse("*4*1101*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_HEAT

    def test_mode_heat_scenario_1201(self):
        msg = OWNEvent.parse("*4*1201*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_HEAT

    def test_mode_auto_variant_310(self):
        msg = OWNEvent.parse("*4*310*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_AUTO

    def test_mode_auto_variant_315(self):
        msg = OWNEvent.parse("*4*315*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_AUTO

    def test_mode_auto_weekly_23001(self):
        msg = OWNEvent.parse("*4*23001*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_AUTO

    def test_mode_auto_weekly_13001(self):
        msg = OWNEvent.parse("*4*13001*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode == CLIMATE_MODE_AUTO

    def test_unknown_mode(self):
        msg = OWNEvent.parse("*4*999*1##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.mode is None

    def test_valve_cooling_on(self):
        msg = OWNEvent.parse("*#4*1*19*1*0##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.message_type == MESSAGE_TYPE_ACTION

    def test_valve_cooling_opened(self):
        msg = OWNEvent.parse("*#4*1*19*2*0##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_cooling_closed(self):
        msg = OWNEvent.parse("*#4*1*19*3*0##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_cooling_stopped(self):
        msg = OWNEvent.parse("*#4*1*19*4*0##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_cooling_fan_on(self):
        msg = OWNEvent.parse("*#4*1*19*6*0##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_cooling_fan_off(self):
        msg = OWNEvent.parse("*#4*1*19*5*0##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_heating_on(self):
        msg = OWNEvent.parse("*#4*1*19*0*1##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_heating_opened(self):
        msg = OWNEvent.parse("*#4*1*19*0*2##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_heating_closed(self):
        msg = OWNEvent.parse("*#4*1*19*0*3##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_heating_stopped(self):
        msg = OWNEvent.parse("*#4*1*19*0*4##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_heating_fan_on(self):
        msg = OWNEvent.parse("*#4*1*19*0*6##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_valve_heating_fan_off(self):
        msg = OWNEvent.parse("*#4*1*19*0*5##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_off(self):
        msg = OWNEvent.parse("*#4*1#1*20*0##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.message_type == MESSAGE_TYPE_ACTION

    def test_actuator_on(self):
        msg = OWNEvent.parse("*#4*1#1*20*1##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_opened(self):
        msg = OWNEvent.parse("*#4*1#1*20*2##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_closed(self):
        msg = OWNEvent.parse("*#4*1#1*20*3##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_stopped(self):
        msg = OWNEvent.parse("*#4*1#1*20*4##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_fan_on_speed(self):
        msg = OWNEvent.parse("*#4*1#1*20*6##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_fan_on_speed_high(self):
        msg = OWNEvent.parse("*#4*1#1*20*8##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_fan_on_auto(self):
        """Fan mode >= 4 is auto speed."""
        msg = OWNEvent.parse("*#4*1#1*20*9##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_actuator_fan_off(self):
        msg = OWNEvent.parse("*#4*1#1*20*5##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_fan_speed_auto(self):
        """Fan speed 0 = auto."""
        msg = OWNEvent.parse("*#4*1*11*0##")
        assert isinstance(msg, OWNHeatingEvent)

    def test_local_offset_knob_off(self):
        """Value 4 or 5 means offset knob is off."""
        msg = OWNEvent.parse("*#4*1*13*4##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.local_offset == 0

    def test_local_offset_knob_5(self):
        msg = OWNEvent.parse("*#4*1*13*5##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.local_offset == 0

    def test_local_offset_zero_single_digit(self):
        msg = OWNEvent.parse("*#4*1*13*0##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.local_offset == 0

    def test_heating_central_local_command(self):
        """Commands with #0#zone format."""
        cmd = OWNHeatingCommand.set_mode("#0#1", CLIMATE_MODE_OFF)
        assert cmd is not None

    def test_heating_temp_standalone(self):
        cmd = OWNHeatingCommand.set_temperature("1", 21.0, CLIMATE_MODE_HEAT, standalone=True)
        assert cmd is not None

    def test_heating_temp_zone_zero_standalone(self):
        cmd = OWNHeatingCommand.set_temperature("#0", 21.0, CLIMATE_MODE_AUTO, standalone=True)
        assert cmd is not None

    def test_heating_set_mode_standalone(self):
        cmd = OWNHeatingCommand.set_mode("1", CLIMATE_MODE_OFF, standalone=True)
        assert cmd is not None

    def test_heating_set_mode_zone_zero(self):
        cmd = OWNHeatingCommand.set_mode("#0", CLIMATE_MODE_OFF, standalone=False)
        assert cmd is not None

    def test_heating_zone_from_param(self):
        """Zone 0 with where_param should use the param as zone."""
        msg = OWNEvent.parse("*#4*0#5*0*0225##")
        assert isinstance(msg, OWNHeatingEvent)
        assert msg.zone == 5


# ── Alarm Event Edge Cases ────────────────────────────────────────────────

class TestAlarmEdgeCases:
    def test_alarm_deactivation(self):
        msg = OWNEvent.parse("*5*2**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_delay_end(self):
        msg = OWNEvent.parse("*5*3**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_battery_fault(self):
        msg = OWNEvent.parse("*5*4**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_battery_ok(self):
        msg = OWNEvent.parse("*5*5**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_no_network(self):
        msg = OWNEvent.parse("*5*6**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_network_present(self):
        msg = OWNEvent.parse("*5*7**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_disengage(self):
        msg = OWNEvent.parse("*5*9**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_battery_unloads(self):
        msg = OWNEvent.parse("*5*10**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_active_zone(self):
        msg = OWNEvent.parse("*5*11*#1##")
        assert isinstance(msg, OWNAlarmEvent)
        assert msg.is_active is True

    def test_alarm_reset_technical(self):
        msg = OWNEvent.parse("*5*13**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_no_reception(self):
        msg = OWNEvent.parse("*5*14**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_tampering(self):
        msg = OWNEvent.parse("*5*16**##")
        assert isinstance(msg, OWNAlarmEvent)
        assert msg.is_alarm is True

    def test_alarm_anti_panic(self):
        msg = OWNEvent.parse("*5*17**##")
        assert isinstance(msg, OWNAlarmEvent)
        assert msg.is_alarm is True

    def test_alarm_non_active_zone(self):
        msg = OWNEvent.parse("*5*18*#1##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_start_programming(self):
        msg = OWNEvent.parse("*5*26**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_stop_programming(self):
        msg = OWNEvent.parse("*5*27**##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_silent(self):
        msg = OWNEvent.parse("*5*31**##")
        assert isinstance(msg, OWNAlarmEvent)
        assert msg.is_alarm is True

    def test_alarm_zone_c(self):
        """Zone #12 maps to 'c'."""
        msg = OWNEvent.parse("*5*1*#12##")
        assert isinstance(msg, OWNAlarmEvent)
        assert msg.zone == "c"

    def test_alarm_zone_f(self):
        """Zone #15 maps to 'f'."""
        msg = OWNEvent.parse("*5*1*#15##")
        assert isinstance(msg, OWNAlarmEvent)
        assert msg.zone == "f"

    def test_alarm_sensor_in_input_zone(self):
        """Zone 0 + sensor ID."""
        msg = OWNEvent.parse("*5*1*01##")
        assert isinstance(msg, OWNAlarmEvent)

    def test_alarm_control_panel(self):
        """Single digit where = control panel."""
        msg = OWNEvent.parse("*5*1*1##")
        assert isinstance(msg, OWNAlarmEvent)


# ── Aux Event Edge Cases ──────────────────────────────────────────────────

class TestAuxEdgeCases:
    def test_aux_stop(self):
        msg = OWNEvent.parse("*9*3*1##")
        assert isinstance(msg, OWNAuxEvent)
        assert msg.state_code == 3

    def test_aux_up(self):
        msg = OWNEvent.parse("*9*4*1##")
        assert isinstance(msg, OWNAuxEvent)

    def test_aux_down(self):
        msg = OWNEvent.parse("*9*5*1##")
        assert isinstance(msg, OWNAuxEvent)

    def test_aux_enabled(self):
        msg = OWNEvent.parse("*9*6*1##")
        assert isinstance(msg, OWNAuxEvent)

    def test_aux_disabled(self):
        msg = OWNEvent.parse("*9*7*1##")
        assert isinstance(msg, OWNAuxEvent)

    def test_aux_reset_gen(self):
        msg = OWNEvent.parse("*9*8*1##")
        assert isinstance(msg, OWNAuxEvent)

    def test_aux_reset_bi(self):
        msg = OWNEvent.parse("*9*9*1##")
        assert isinstance(msg, OWNAuxEvent)

    def test_aux_reset_tri(self):
        msg = OWNEvent.parse("*9*10*1##")
        assert isinstance(msg, OWNAuxEvent)


# ── CEN+ Event Edge Cases ────────────────────────────────────────────────

class TestCENPlusEdgeCases:
    def test_slow_rotated_cw(self):
        msg = OWNEvent.parse("*25*25#1*21##")
        assert isinstance(msg, OWNCENPlusEvent)
        assert msg.is_slowly_turned_cw is True

    def test_quickly_rotated_cw(self):
        msg = OWNEvent.parse("*25*26#1*21##")
        assert isinstance(msg, OWNCENPlusEvent)
        assert msg.is_quickly_turned_cw is True

    def test_slowly_rotated_ccw(self):
        msg = OWNEvent.parse("*25*27#1*21##")
        assert isinstance(msg, OWNCENPlusEvent)
        assert msg.is_slowly_turned_ccw is True

    def test_quickly_rotated_ccw(self):
        msg = OWNEvent.parse("*25*28#1*21##")
        assert isinstance(msg, OWNCENPlusEvent)
        assert msg.is_quickly_turned_ccw is True


# ── Scene Event Edge Cases ────────────────────────────────────────────────

class TestSceneEdgeCases:
    def test_unknown_state(self):
        msg = OWNEvent.parse("*17*99*1##")
        assert isinstance(msg, OWNSceneEvent)
        assert msg.is_on is None
        assert msg.is_enabled is None


# ── Gateway Device Types ──────────────────────────────────────────────────

class TestGatewayDeviceTypes:
    def test_mhserver(self):
        msg = OWNEvent.parse("*#13**15*2##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_f452(self):
        msg = OWNEvent.parse("*#13**15*6##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_f452v(self):
        msg = OWNEvent.parse("*#13**15*7##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_mhserver2(self):
        msg = OWNEvent.parse("*#13**15*11##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_h4684(self):
        msg = OWNEvent.parse("*#13**15*13##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_f454(self):
        msg = OWNEvent.parse("*#13**15*200##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_unknown_device(self):
        msg = OWNEvent.parse("*#13**15*99##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_gateway_time_no_timezone(self):
        """Timezone field empty."""
        msg = OWNEvent.parse("*#13**0*12*30*45*##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_gateway_time_negative_tz(self):
        """Timezone with leading 1 = negative."""
        msg = OWNEvent.parse("*#13**0*12*30*45*105##")
        assert isinstance(msg, OWNGatewayEvent)

    def test_gateway_datetime_no_tz(self):
        msg = OWNEvent.parse("*#13**22*12*14*58**03*15*04*2026##")
        assert isinstance(msg, OWNGatewayEvent)


# ── Energy Event Edge Cases ───────────────────────────────────────────────

class TestEnergyEdgeCases:
    def test_energy_sensor_7x(self):
        """Sensors starting with 7 are also valid."""
        msg = OWNEvent.parse("*#18*71*113*500##")
        assert isinstance(msg, OWNEnergyEvent)
        assert msg.active_power == 500

    def test_energy_invalid_sensor(self):
        """Sensors not starting with 5 or 7 trigger early return in __init__.
        This is an upstream quirk: __init__ returns None which is silently ignored."""
        msg = OWNEvent.parse("*#18*31*113*500##")
        assert isinstance(msg, OWNEnergyEvent)
        # _type attribute is never set due to early return - upstream bug
        assert not hasattr(msg, '_type') or msg._type is None

    def test_energy_command_duration_clamp(self):
        """Duration > 255 should be clamped."""
        cmd = OWNEnergyCommand.start_sending_instant_power("51", 999)
        assert "255" in str(cmd)


# ── Lighting Edge Cases ──────────────────────────────────────────────────

class TestLightingEdgeCases:
    def test_brightness_dim4(self):
        """Dimension 4 is also brightness."""
        msg = OWNEvent.parse("*#1*21*4*150*5##")
        assert isinstance(msg, OWNLightingEvent)
        assert msg.brightness == 50

    def test_timer_dimension(self):
        """Dimension 2 = time value."""
        msg = OWNEvent.parse("*#1*21*2*1*30*0##")
        assert isinstance(msg, OWNLightingEvent)
        assert msg.timer == 5400  # 1*3600 + 30*60

    def test_flash_invalid_frequency(self):
        """Invalid frequency should default to 0.5."""
        cmd = OWNLightingCommand.flash("21", _freqency=-1)
        assert str(cmd) == "*1*20*21##"

    def test_switch_on_invalid_transition(self):
        """Transition out of range should use simple command."""
        cmd = OWNLightingCommand.switch_on("21", _transition=300)
        assert str(cmd) == "*1*1*21##"

    def test_switch_off_invalid_transition(self):
        cmd = OWNLightingCommand.switch_off("21", _transition=-1)
        assert str(cmd) == "*1*0*21##"

    def test_set_brightness_negative_transition(self):
        """Negative transition should default to 0."""
        cmd = OWNLightingCommand.set_brightness("21", _level=50, _transition=-5)
        assert "*0##" in str(cmd)


# ── Automation Edge Cases ─────────────────────────────────────────────────

class TestAutomationEdgeCases:
    def test_cover_opening_state13(self):
        """State 13 is also opening from position."""
        msg = OWNEvent.parse("*#2*21*10*13*50*0*0##")
        assert isinstance(msg, OWNAutomationEvent)
        assert msg.is_opening is True

    def test_cover_closing_state14(self):
        """State 14 is also closing from position."""
        msg = OWNEvent.parse("*#2*21*10*14*50*0*0##")
        assert isinstance(msg, OWNAutomationEvent)
        assert msg.is_closing is True


# ── AV Command Edge Cases ─────────────────────────────────────────────────

class TestAVEdgeCases:
    def test_receive_video_4xxx(self):
        """Camera ID >= 4000 extracts from where."""
        cmd = OWNAVCommand.receive_video("4005")
        assert cmd is not None

    def test_receive_video_invalid(self):
        """Camera ID in invalid range returns None."""
        cmd = OWNAVCommand.receive_video("5000")
        assert cmd is None


# ── Command Parse Additional WHO Coverage ─────────────────────────────────

class TestCommandParseWHOCoverage:
    """Cover the remaining WHO dispatch branches in OWNCommand.parse."""

    def test_who3_charges(self):
        cmd = OWNCommand.parse("*3*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who5_alarm(self):
        cmd = OWNCommand.parse("*5*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who6_vdes(self):
        cmd = OWNCommand.parse("*6*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who7_av(self):
        cmd = OWNCommand.parse("*7*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who9_aux(self):
        cmd = OWNCommand.parse("*9*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who14(self):
        cmd = OWNCommand.parse("*14*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who15_cen(self):
        cmd = OWNCommand.parse("*15*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who17_scene(self):
        cmd = OWNCommand.parse("*17*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who22(self):
        cmd = OWNCommand.parse("*22*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who24(self):
        cmd = OWNCommand.parse("*24*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who25_cenplus(self):
        cmd = OWNCommand.parse("*25*1*21##")
        assert isinstance(cmd, OWNCommand)

    def test_who_over_1000(self):
        cmd = OWNCommand.parse("*1001*1*21##")
        assert isinstance(cmd, OWNCommand)


# ── Gateway Command Edge Cases ────────────────────────────────────────────

class TestGatewayCommandEdgeCases:
    def test_set_date_to_today(self):
        cmd = OWNGatewayCommand.set_date_to_today("Europe/Brussels")
        assert cmd is not None
        assert "*#13**#1*" in str(cmd)

    def test_set_time_to_now(self):
        cmd = OWNGatewayCommand.set_time_to_now("Europe/Brussels")
        assert cmd is not None
        assert "*#13**#0*" in str(cmd)

    def test_gateway_command_date(self):
        cmd = OWNCommand.parse("*#13**#1*03*15*04*2026##")
        assert isinstance(cmd, OWNGatewayCommand)

    def test_gateway_command_datetime(self):
        cmd = OWNCommand.parse("*#13**#22*12*14*58*000*03*15*04*2026##")
        assert isinstance(cmd, OWNGatewayCommand)

    def test_gateway_command_time_negative_tz(self):
        """Timezone starting with 1 = negative offset."""
        cmd = OWNCommand.parse("*#13**#0*12*30*45*105*##")
        assert isinstance(cmd, OWNGatewayCommand)

    def test_gateway_command_time_no_tz(self):
        cmd = OWNCommand.parse("*#13**#0*12*30*45**##")
        assert isinstance(cmd, OWNGatewayCommand)
