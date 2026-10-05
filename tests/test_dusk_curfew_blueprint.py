"""Tests for the MyHOME dusk curfew & hardware-coupled sensor automation blueprint."""
from pathlib import Path

import yaml


def test_dusk_curfew_blueprint_syntax_and_schema() -> None:
    """Verify blueprints/automation/myhome/dusk_curfew.yaml is valid Home Assistant automation blueprint."""
    blueprint_path = Path(__file__).parent.parent / "blueprints" / "automation" / "myhome" / "dusk_curfew.yaml"
    bundled_path = Path(__file__).parent.parent / "custom_components" / "myhome" / "blueprints" / "automation" / "dusk_curfew.yaml"
    assert blueprint_path.is_file(), f"Blueprint file not found at {blueprint_path}"
    assert bundled_path.is_file(), f"Bundled blueprint not found at {bundled_path}"
    assert blueprint_path.read_text(encoding="utf-8") == bundled_path.read_text(encoding="utf-8")

    # Load raw content and ensure custom yaml tags like !input don't break parsing
    class BlueprintLoader(yaml.SafeLoader):
        pass

    def input_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> str:
        return f"!input {loader.construct_scalar(node)}"  # type: ignore[arg-type]

    BlueprintLoader.add_constructor("!input", input_constructor)

    with blueprint_path.open("r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=BlueprintLoader)

    assert isinstance(data, dict), "Blueprint YAML root must be a mapping"
    assert "blueprint" in data, "Missing top-level 'blueprint' key"

    bp = data["blueprint"]
    assert bp.get("domain") == "automation", "Blueprint domain must be 'automation'"
    assert "name" in bp and len(bp["name"]) > 0, "Blueprint must have a non-empty name"
    assert "description" in bp and len(bp["description"]) > 0, "Blueprint must have a description"
    assert "input" in bp, "Blueprint must declare inputs"

    inputs = bp["input"]
    expected_inputs = {
        "target_light",
        "curfew_time",
        "max_duration",
        "sync_lights",
        "presence_entity",
        "away_timeout",
    }
    for inp in expected_inputs:
        assert inp in inputs, f"Expected input '{inp}' missing from blueprint"

    # Verify target_light requires entity selector in light domain
    target_selector = inputs["target_light"]["selector"]
    assert "entity" in target_selector
    assert target_selector["entity"].get("domain") == "light"

    # Verify curfew_time has time selector
    assert "time" in inputs["curfew_time"]["selector"]

    # Verify execution structure
    assert data.get("mode") == "restart"
    assert "trigger" in data and isinstance(data["trigger"], list)
    assert len(data["trigger"]) >= 2
    assert "action" in data and isinstance(data["action"], list)
