"""Tests for the MyHOME dusk curfew & hardware-coupled sensor automation blueprint."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.components.automation.config import (
    _MINIMAL_PLATFORM_SCHEMA,
    AUTOMATION_BLUEPRINT_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.helpers import template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util import yaml as yaml_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed


def _get_blueprint_path() -> Path:
    """Return the absolute path to the dusk curfew blueprint."""
    return Path(__file__).parent.parent / "blueprints" / "automation" / "myhome" / "dusk_curfew.yaml"


def test_dusk_curfew_blueprint_schema_and_inputs() -> None:
    """Verify dusk_curfew.yaml complies with HA's native AUTOMATION_BLUEPRINT_SCHEMA."""
    blueprint_path = _get_blueprint_path()
    assert blueprint_path.is_file(), f"Blueprint file not found at {blueprint_path}"

    # Verify no dead bundled copy remains in custom_components
    bundled_dir = Path(__file__).parent.parent / "custom_components" / "myhome" / "blueprints"
    assert not bundled_dir.exists(), "custom_components/myhome/blueprints must not exist"

    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    assert isinstance(raw_data, dict), "Blueprint YAML root must be a mapping"
    assert "blueprint" in raw_data, "Missing top-level 'blueprint' key"

    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)
    assert bp.domain == "automation"
    assert bp.name == "MyHOME - Dusk Curfew & Hardware-Coupled Sensor Control"

    expected_inputs = {
        "target_light",
        "curfew_time",
        "curfew_end_time",
        "max_duration",
        "sync_lights",
        "presence_entity",
        "away_timeout",
        "after_sunset_only",
        "override_entity",
        "override_mode",
        "service_timeout_hours",
    }
    assert set(bp.inputs.keys()) == expected_inputs

    # Validate target_light entity selector (HA normalizes domain to list)
    target_selector = bp.inputs["target_light"]["selector"]
    assert target_selector["entity"]["domain"] == ["light"]

    # Validate curfew_time & curfew_end_time selectors and defaults
    assert "time" in bp.inputs["curfew_time"]["selector"]
    assert bp.inputs["curfew_time"]["default"] == "23:00:00"
    assert "time" in bp.inputs["curfew_end_time"]["selector"]
    assert bp.inputs["curfew_end_time"]["default"] == "06:00:00"

    # Validate default values
    assert bp.inputs["sync_lights"]["default"] == {}
    assert bp.inputs["presence_entity"]["default"] == ""
    assert bp.inputs["away_timeout"]["default"] == 0
    assert bp.inputs["max_duration"]["default"] == 0
    assert bp.inputs["after_sunset_only"]["default"] is False
    assert bp.inputs["override_entity"]["default"] == ""
    assert bp.inputs["override_mode"]["default"] == "service_power"
    assert bp.inputs["service_timeout_hours"]["default"] == 4


def test_dusk_curfew_blueprint_substitution() -> None:
    """Verify substituting inputs produces valid automation configuration with expected triggers."""
    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "curfew_end_time": "06:00:00",
        "max_duration": 180,
        "sync_lights": {"entity_id": ["light.garden_pathway", "light.driveway_spots"]},
        "presence_entity": "zone.home",
        "away_timeout": 15,
        "after_sunset_only": False,
        "override_entity": "input_boolean.gardener_power",
        "override_mode": "service_power",
        "service_timeout_hours": 3,
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    bp_inputs.validate()
    substituted = bp_inputs.async_substitute()

    # Pass minimal automation platform validation
    validated = _MINIMAL_PLATFORM_SCHEMA(substituted)
    assert validated.get("mode") == "parallel"
    assert validated.get("max") == 10

    # Verify trigger_variables scoping so template triggers can access presence_entity & override_entity
    trig_vars = validated.get("trigger_variables", {})
    assert trig_vars.get("presence_entity") == "zone.home"
    assert trig_vars.get("away_timeout") == 15
    assert trig_vars.get("override_entity") == "input_boolean.gardener_power"

    triggers = validated["triggers"]
    trigger_ids = {t.get("id") for t in triggers}
    assert trigger_ids == {
        "light_turned_on",
        "light_turned_off",
        "curfew_reached",
        "ha_started",
        "presence_away",
        "override_activated",
        "override_deactivated",
    }

    # Verify light_turned_on trigger has from: off, to: on (prevent flap on gateway reconnect)
    turn_on_trig = next(t for t in triggers if t.get("id") == "light_turned_on")
    assert turn_on_trig.get("from") == "off"
    assert turn_on_trig.get("to") == "on"
    assert turn_on_trig.get("entity_id") == "light.light_98"

    # Verify light_turned_off trigger has from: on, to: off
    turn_off_trig = next(t for t in triggers if t.get("id") == "light_turned_off")
    assert turn_off_trig.get("from") == "on"
    assert turn_off_trig.get("to") == "off"

    # Verify curfew_reached trigger
    curfew_trig = next(t for t in triggers if t.get("id") == "curfew_reached")
    assert curfew_trig.get("trigger") == "time"
    assert curfew_trig.get("at") == "23:00:00"


async def test_dusk_curfew_presence_template_rendering(hass: HomeAssistant) -> None:
    """Verify presence template handles zone counts (count 0 = away) and person/binary_sensor states."""
    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {"target_light": "light.light_98"}
    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    substituted = bp_inputs.async_substitute()

    template_str = substituted["variables"]["is_away"]

    # Case 1: Empty presence entity defaults to false (not away)
    t = template.Template(template_str, hass)
    assert t.async_render({"presence_entity": ""}, parse_result=True) is False

    # Case 2: zone.home with 0 persons is away; with 1 or 2 persons is home
    hass.states.async_set("zone.home", "0")
    assert t.async_render({"presence_entity": "zone.home"}, parse_result=True) is True

    hass.states.async_set("zone.home", "1")
    assert t.async_render({"presence_entity": "zone.home"}, parse_result=True) is False

    hass.states.async_set("zone.home", "2")
    assert t.async_render({"presence_entity": "zone.home"}, parse_result=True) is False

    # Case 3: person.* entity
    hass.states.async_set("person.john", "not_home")
    assert t.async_render({"presence_entity": "person.john"}, parse_result=True) is True

    hass.states.async_set("person.john", "away")
    assert t.async_render({"presence_entity": "person.john"}, parse_result=True) is True

    hass.states.async_set("person.john", "home")
    assert t.async_render({"presence_entity": "person.john"}, parse_result=True) is False

    # Case 4: binary_sensor.* entity
    hass.states.async_set("binary_sensor.presence", "off")
    assert t.async_render({"presence_entity": "binary_sensor.presence"}, parse_result=True) is True

    hass.states.async_set("binary_sensor.presence", "on")
    assert t.async_render({"presence_entity": "binary_sensor.presence"}, parse_result=True) is False


async def test_dusk_curfew_behavioral_turn_on_and_from_off_guard(hass: HomeAssistant) -> None:
    """Behaviorally verify from: off guard prevents unavailable->on flap and off->on syncs companion lights."""
    calls: list[tuple[str, dict[str, Any]]] = []
    hass.services.async_register("light", "turn_on", lambda c: calls.append(("on", c.data)))
    hass.services.async_register("light", "turn_off", lambda c: calls.append(("off", c.data)))

    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "curfew_end_time": "06:00:00",
        "max_duration": 0,
        "sync_lights": {"entity_id": ["light.garden_pathway"]},
        "after_sunset_only": False,
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    substituted = bp_inputs.async_substitute()
    substituted["alias"] = "test_turn_on_guard"

    hass.states.async_set("light.light_98", "off")
    hass.states.async_set("light.garden_pathway", "off")

    assert await async_setup_component(hass, "automation", {"automation": [substituted]})
    await hass.async_block_till_done()

    # Flap test: unavailable -> on must NOT trigger companion turn_on
    hass.states.async_set("light.light_98", "unavailable")
    await hass.async_block_till_done()

    hass.states.async_set("light.light_98", "on")
    await hass.async_block_till_done()
    assert not any(action == "on" for action, _ in calls)

    # Valid transition test: off -> on MUST trigger companion turn_on
    hass.states.async_set("light.light_98", "off")
    await hass.async_block_till_done()
    calls.clear()

    hass.states.async_set("light.light_98", "on")
    await hass.async_block_till_done()
    assert any(action == "on" and data.get("entity_id") == ["light.garden_pathway"] for action, data in calls)

    # Clean up automation
    await hass.services.async_call("automation", "turn_off", {"entity_id": "automation.test_turn_on_guard"}, blocking=True)


async def test_dusk_curfew_behavioral_daylight_guard(hass: HomeAssistant) -> None:
    """Behaviorally verify after_sunset_only stops companion activation when sun is above horizon."""
    calls: list[tuple[str, dict[str, Any]]] = []
    hass.services.async_register("light", "turn_on", lambda c: calls.append(("on", c.data)))
    hass.services.async_register("light", "turn_off", lambda c: calls.append(("off", c.data)))

    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "curfew_end_time": "06:00:00",
        "max_duration": 0,
        "sync_lights": {"entity_id": ["light.garden_pathway"]},
        "after_sunset_only": True,
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    substituted = bp_inputs.async_substitute()
    substituted["alias"] = "test_daylight_guard"

    hass.states.async_set("light.light_98", "off")
    hass.states.async_set("light.garden_pathway", "off")
    hass.states.async_set("sun.sun", "above_horizon")

    assert await async_setup_component(hass, "automation", {"automation": [substituted]})
    await hass.async_block_till_done()

    # Daytime off -> on: companion lights must NOT turn on
    hass.states.async_set("light.light_98", "on")
    await hass.async_block_till_done()
    assert not any(action == "on" for action, _ in calls)

    # Nighttime off -> on: companion lights MUST turn on
    hass.states.async_set("light.light_98", "off")
    hass.states.async_set("sun.sun", "below_horizon")
    await hass.async_block_till_done()
    calls.clear()

    hass.states.async_set("light.light_98", "on")
    await hass.async_block_till_done()
    assert any(action == "on" and data.get("entity_id") == ["light.garden_pathway"] for action, data in calls)

    # Clean up automation
    await hass.services.async_call("automation", "turn_off", {"entity_id": "automation.test_daylight_guard"}, blocking=True)


async def test_dusk_curfew_behavioral_presence_away_trigger(hass: HomeAssistant) -> None:
    """Behaviorally verify presence_away trigger fires via trigger_variables and turns off lights."""
    calls: list[tuple[str, dict[str, Any]]] = []
    hass.services.async_register("light", "turn_on", lambda c: calls.append(("on", c.data)))
    hass.services.async_register("light", "turn_off", lambda c: calls.append(("off", c.data)))

    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "curfew_end_time": "06:00:00",
        "max_duration": 0,
        "sync_lights": {"entity_id": ["light.garden_pathway"]},
        "presence_entity": "zone.home",
        "away_timeout": 1,
        "after_sunset_only": False,
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    substituted = bp_inputs.async_substitute()
    substituted["alias"] = "test_presence_away_guard"

    # Initialize: lights on, zone.home has 1 person
    hass.states.async_set("light.light_98", "on")
    hass.states.async_set("light.garden_pathway", "on")
    hass.states.async_set("zone.home", "1")

    assert await async_setup_component(hass, "automation", {"automation": [substituted]})
    await hass.async_block_till_done()

    # Trigger template verification: transition to 0 person
    hass.states.async_set("zone.home", "0")
    await hass.async_block_till_done()

    # Advance time by 65 seconds so the 1-minute 'for:' duration expires
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=65))
    await hass.async_block_till_done()

    try:
        # Assert that presence_away fired and commanded light.turn_off on target_light
        assert any(
            action == "off" and ("light.light_98" in data.get("entity_id", []) or data.get("entity_id") == "light.light_98")
            for action, data in calls
        )
    finally:
        # Clean up automation
        await hass.services.async_call("automation", "turn_off", {"entity_id": "automation.test_presence_away_guard"}, blocking=True)


async def test_dusk_curfew_behavioral_service_power_override(hass: HomeAssistant) -> None:
    """Behaviorally verify service_power override energizes circuit on demand and bypasses curfew."""
    calls: list[tuple[str, dict[str, Any]]] = []
    hass.services.async_register("light", "turn_on", lambda c: calls.append(("on", c.data)))
    hass.services.async_register("light", "turn_off", lambda c: calls.append(("off", c.data)))

    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "curfew_end_time": "06:00:00",
        "max_duration": 0,
        "sync_lights": {"entity_id": ["light.garden_pathway"]},
        "override_entity": "input_boolean.gardener_power",
        "override_mode": "service_power",
        "service_timeout_hours": 0,
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    substituted = bp_inputs.async_substitute()
    substituted["alias"] = "test_service_power_override"

    hass.states.async_set("light.light_98", "off")
    hass.states.async_set("input_boolean.gardener_power", "off")

    assert await async_setup_component(hass, "automation", {"automation": [substituted]})
    await hass.async_block_till_done()

    # Step 1: Turn on gardener power override -> target light turns on
    hass.states.async_set("input_boolean.gardener_power", "on")
    await hass.async_block_till_done()

    assert any(
        action == "on" and ("light.light_98" in data.get("entity_id", []) or data.get("entity_id") == "light.light_98")
        for action, data in calls
    )

    # Step 2: Trigger curfew while override is active -> light must NOT be shut off
    calls.clear()
    hass.states.async_set("light.light_98", "on")
    curfew_dt = dt_util.parse_datetime("2026-10-05T23:00:00+00:00")
    assert curfew_dt is not None
    async_fire_time_changed(hass, curfew_dt)
    await hass.async_block_till_done()
    assert not any(action == "off" for action, _ in calls)

    # Step 3: Turn off gardener power override -> target light turns off
    calls.clear()
    hass.states.async_set("input_boolean.gardener_power", "off")
    await hass.async_block_till_done()

    assert any(
        action == "off" and ("light.light_98" in data.get("entity_id", []) or data.get("entity_id") == "light.light_98")
        for action, data in calls
    )

    # Clean up automation
    await hass.services.async_call("automation", "turn_off", {"entity_id": "automation.test_service_power_override"}, blocking=True)


async def test_dusk_curfew_behavioral_safety_lockout_override(hass: HomeAssistant) -> None:
    """Behaviorally verify safety_lockout forces lights off and intercepts dusk photocell turn-ons."""
    calls: list[tuple[str, dict[str, Any]]] = []
    hass.services.async_register("light", "turn_on", lambda c: calls.append(("on", c.data)))
    hass.services.async_register("light", "turn_off", lambda c: calls.append(("off", c.data)))

    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "curfew_end_time": "06:00:00",
        "max_duration": 0,
        "sync_lights": {"entity_id": ["light.garden_pathway"]},
        "override_entity": "input_boolean.maintenance_lock",
        "override_mode": "safety_lockout",
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    substituted = bp_inputs.async_substitute()
    substituted["alias"] = "test_safety_lockout"

    hass.states.async_set("light.light_98", "on")
    hass.states.async_set("input_boolean.maintenance_lock", "off")

    assert await async_setup_component(hass, "automation", {"automation": [substituted]})
    await hass.async_block_till_done()

    # Step 1: Turn on maintenance lock -> forces target light off immediately
    hass.states.async_set("input_boolean.maintenance_lock", "on")
    await hass.async_block_till_done()

    assert any(
        action == "off" and ("light.light_98" in data.get("entity_id", []) or data.get("entity_id") == "light.light_98")
        for action, data in calls
    )

    # Step 2: Simulate physical photocell turning light on while lockout active -> intercepted and forced off
    calls.clear()
    hass.states.async_set("light.light_98", "off")
    await hass.async_block_till_done()

    hass.states.async_set("light.light_98", "on")
    await hass.async_block_till_done()

    assert any(
        action == "off" and ("light.light_98" in data.get("entity_id", []) or data.get("entity_id") == "light.light_98")
        for action, data in calls
    )

    # Clean up automation
    await hass.services.async_call("automation", "turn_off", {"entity_id": "automation.test_safety_lockout"}, blocking=True)
