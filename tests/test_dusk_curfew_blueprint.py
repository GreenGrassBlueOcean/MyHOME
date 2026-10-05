"""Tests for the MyHOME dusk curfew & hardware-coupled sensor automation blueprint."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from homeassistant.components.automation.config import (
    _MINIMAL_PLATFORM_SCHEMA,
    AUTOMATION_BLUEPRINT_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.helpers import template
from homeassistant.setup import async_setup_component
from homeassistant.util import yaml as yaml_util


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
        "max_duration",
        "sync_lights",
        "presence_entity",
        "away_timeout",
        "after_sunset_only",
    }
    assert set(bp.inputs.keys()) == expected_inputs

    # Validate target_light entity selector (HA normalizes domain to list)
    target_selector = bp.inputs["target_light"]["selector"]
    assert target_selector["entity"]["domain"] == ["light"]

    # Validate curfew_time time selector and default
    assert "time" in bp.inputs["curfew_time"]["selector"]
    assert bp.inputs["curfew_time"]["default"] == "23:00:00"

    # Validate default values
    assert bp.inputs["sync_lights"]["default"] == {}
    assert bp.inputs["presence_entity"]["default"] == ""
    assert bp.inputs["away_timeout"]["default"] == 0
    assert bp.inputs["max_duration"]["default"] == 0
    assert bp.inputs["after_sunset_only"]["default"] is True


def test_dusk_curfew_blueprint_substitution() -> None:
    """Verify substituting inputs produces valid automation configuration with expected triggers."""
    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "max_duration": 180,
        "sync_lights": {"entity_id": ["light.garden_pathway", "light.driveway_spots"]},
        "presence_entity": "zone.home",
        "away_timeout": 15,
        "after_sunset_only": True,
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    bp_inputs.validate()
    substituted = bp_inputs.async_substitute()

    # Pass minimal automation platform validation
    validated = _MINIMAL_PLATFORM_SCHEMA(substituted)
    assert validated.get("mode") == "restart"

    triggers = validated["triggers"]
    trigger_ids = {t.get("id") for t in triggers}
    assert trigger_ids == {
        "light_turned_on",
        "light_turned_off",
        "curfew_reached",
        "ha_started",
        "presence_away",
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


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_dusk_curfew_automation_setup_in_hass(hass: HomeAssistant) -> None:
    """Verify instantiated automation successfully loads and attaches in a live Home Assistant instance."""
    blueprint_path = _get_blueprint_path()
    raw_data: dict[str, Any] = yaml_util.load_yaml(str(blueprint_path))
    bp = Blueprint(raw_data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    user_inputs = {
        "target_light": "light.light_98",
        "curfew_time": "23:00:00",
        "max_duration": 60,
        "sync_lights": {"entity_id": ["light.garden_pathway"]},
        "presence_entity": "zone.home",
        "away_timeout": 10,
    }

    bp_inputs = BlueprintInputs(bp, {"use_blueprint": {"path": "test", "input": user_inputs}})
    substituted = bp_inputs.async_substitute()
    substituted["alias"] = "Dusk Curfew Test Automation"

    config = {"automation": [substituted]}
    assert await async_setup_component(hass, "automation", config)
