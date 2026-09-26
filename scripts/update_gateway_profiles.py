#!/usr/bin/env python3
"""Update and calibrate the Gateway Profiles table in README.md.

Maintains live, automated documentation of supported gateway profiles and hardware
specifications by cross-referencing custom_components/myhome/const.py (SUPPORTED_GATEWAY_MODELS),
custom_components/myhome/manifest.json (ssdp), and hardware specifications.
Called locally, by scripts/verify_ha_standards.py, and by GitHub Actions CI workflows.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README_MD = REPO_ROOT / "README.md"
CONST_PY = REPO_ROOT / "custom_components" / "myhome" / "const.py"
MANIFEST_JSON = REPO_ROOT / "custom_components" / "myhome" / "manifest.json"

START_MARKER = "<!-- GATEWAY_PROFILES_START -->"
END_MARKER = "<!-- GATEWAY_PROFILES_END -->"

FOOTER_NOTE = (
    "*This table is automatically updated from gateway profile definitions "
    "and hardware specifications.*"
)

# Authoritative gateway metadata ordered by category and generation
GATEWAY_METADATA: list[dict[str, object]] = [
    {
        "model": "**F454**",
        "const_models": ["F454"],
        "protocol": "OpenWebNet / HMAC",
        "max_workers": "4 workers",
        "delay": "20 ms",
        "upnp": "✅ Port 49153",
        "notes": "Full high-speed multi-session support",
    },
    {
        "model": "**F455**",
        "const_models": ["F455"],
        "protocol": "OpenWebNet / HMAC",
        "max_workers": "4 workers",
        "delay": "20 ms",
        "upnp": "✅ Port 49153",
        "notes": "Basic gateway (single SCS bus)",
    },
    {
        "model": "**F461**",
        "const_models": ["F461"],
        "protocol": "OpenWebNet / HMAC",
        "max_workers": "4 workers",
        "delay": "20 ms",
        "upnp": "❌ Manual",
        "notes": "Compact DIN Ethernet Web Server",
    },
    {
        "model": "**MH202**",
        "const_models": ["MH202"],
        "protocol": "OpenWebNet / HMAC",
        "max_workers": "3 workers",
        "delay": "30 ms",
        "upnp": "✅ Port 49153",
        "notes": "Modern scenario programmer gateway",
    },
    {
        "model": "**MH201**",
        "const_models": ["MH201"],
        "protocol": "OpenWebNet",
        "max_workers": "2 workers",
        "delay": "60 ms",
        "upnp": "✅ Port 49153",
        "notes": "Second-generation scenario programmer",
    },
    {
        "model": "**MyHomeServer1**",
        "const_models": ["MyHomeServer1"],
        "protocol": "OpenWebNet / HMAC",
        "max_workers": "4 workers",
        "delay": "20 ms",
        "upnp": "✅ SSDP",
        "notes": "Cloud/local hybrid gateway",
    },
    {
        "model": "**MH200N**",
        "const_models": ["MH200N"],
        "protocol": "OpenWebNet",
        "max_workers": "2 workers",
        "delay": "80 ms",
        "upnp": "❌ Manual",
        "notes": "Second-generation scenario programmer",
    },
    {
        "model": "**MH200** *(Legacy)*",
        "const_models": ["MH200"],
        "protocol": "OpenWebNet",
        "max_workers": "1 worker",
        "delay": "150 ms",
        "upnp": "❌ Manual",
        "notes": "Strict single-session pacing; watchdog hardened",
    },
    {
        "model": "**H4890 / AM4890**",
        "const_models": ["AM4890", "H4890", "LN4890"],
        "protocol": "OpenWebNet",
        "max_workers": "2 workers",
        "delay": "100 ms",
        "upnp": "❌ Manual",
        "notes": '3.5" Touch screen display IP gateway (Axolute / Livinglight)',
    },
    {
        "model": "**F452 / F453AV**",
        "const_models": ["F453AV", "F452"],
        "protocol": "OpenWebNet",
        "max_workers": "2 workers",
        "delay": "50 ms",
        "upnp": "✅ Port 49153",
        "notes": "Audio/video & web server gateway",
    },
    {
        "model": "**HL4684**",
        "const_models": [],
        "protocol": "OpenWebNet",
        "max_workers": "2 workers",
        "delay": "80 ms",
        "upnp": "✅ SSDP",
        "notes": '10" Touch screen display IP gateway',
    },
    {
        "model": "**Legrand 3578**",
        "const_models": [],
        "protocol": "OpenWebNet (Serial)",
        "max_workers": "2 workers",
        "delay": "50 ms",
        "upnp": "❌ Manual (Serial)",
        "notes": "USB / Serial gateway & OpenZigBee interface",
    },
]


def extract_gateway_models_from_const(const_path: Path = CONST_PY) -> list[str]:
    """Parse SUPPORTED_GATEWAY_MODELS from custom_components/myhome/const.py using AST."""
    if not const_path.exists():
        raise FileNotFoundError(f"{const_path} not found")

    tree = ast.parse(const_path.read_text(encoding="utf-8"))
    models: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "SUPPORTED_GATEWAY_MODELS" for t in node.targets)
        ) or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "SUPPORTED_GATEWAY_MODELS"
        ):
            val_node = node.value
            if isinstance(val_node, (ast.Tuple, ast.List)):
                for elt in val_node.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        models.append(elt.value)
    return models


def extract_ssdp_models_from_manifest(manifest_path: Path = MANIFEST_JSON) -> set[str]:
    """Extract model names configured for SSDP discovery from manifest.json."""
    if not manifest_path.exists():
        return set()

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        ssdp_entries = manifest_data.get("ssdp", [])
        return {
            entry["modelName"]
            for entry in ssdp_entries
            if isinstance(entry, dict) and "modelName" in entry
        }
    except Exception:
        return set()


def generate_gateway_profiles_table(const_path: Path = CONST_PY) -> str:
    """Generate the markdown table for supported gateway profiles."""
    if const_path.exists():
        supported_models = extract_gateway_models_from_const(const_path)
        # Exclude generic fallback placeholder
        concrete_models = [m for m in supported_models if m.lower() != "generic"]

        # Verify all concrete models in const.py are mapped to a gateway row
        mapped_const_models: set[str] = set()
        for gw in GATEWAY_METADATA:
            const_list = gw.get("const_models", [])
            if isinstance(const_list, list):
                mapped_const_models.update(const_list)

        unmapped = [m for m in concrete_models if m not in mapped_const_models]
        if unmapped:
            raise ValueError(f"Gateway models defined in const.py missing from GATEWAY_METADATA: {unmapped}")

    lines = [
        "| Gateway Model | Protocol Support | Max Command Workers | Inter-Frame Delay | UPnP Discovery | Notes |",
        "|---|---|---|---|---|---|",
    ]

    for gw in GATEWAY_METADATA:
        model = gw["model"]
        protocol = gw["protocol"]
        max_workers = gw["max_workers"]
        delay = gw["delay"]
        upnp = gw["upnp"]
        notes = gw["notes"]
        lines.append(f"| {model} | {protocol} | {max_workers} | {delay} | {upnp} | {notes} |")

    return "\n".join(lines)


def build_block(const_path: Path = CONST_PY) -> str:
    """Return the complete marker-wrapped table block."""
    table = generate_gateway_profiles_table(const_path)
    return f"{START_MARKER}\n{table}\n{END_MARKER}"


def check_readme_in_sync(
    readme_path: Path = README_MD,
    const_path: Path = CONST_PY,
) -> tuple[bool, str]:
    """Check if the README.md table is in sync with the generated table."""
    if not readme_path.exists():
        return False, f"{readme_path} does not exist"

    content = readme_path.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        return False, f"Missing markers {START_MARKER} and/or {END_MARKER} in {readme_path.name}"

    pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)
    match = pattern.search(content)
    if not match:
        return False, f"Could not find marker block in {readme_path.name}"

    expected_block = build_block(const_path)
    actual_block = match.group(0)
    if actual_block.strip() != expected_block.strip():
        return False, f"Table content in {readme_path.name} differs from generated table"

    return True, "Table is in sync"


def update_readme(
    readme_path: Path = README_MD,
    const_path: Path = CONST_PY,
) -> bool:
    """Update README.md with the generated gateway profiles table.

    Returns True if file was changed, False if unchanged.
    """
    if not readme_path.exists():
        raise FileNotFoundError(f"{readme_path} not found")

    content = readme_path.read_text(encoding="utf-8")
    expected_block = build_block(const_path)

    if START_MARKER in content and END_MARKER in content:
        pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)
        updated = pattern.sub(expected_block, content)
        # Ensure footer note is present after END_MARKER
        if FOOTER_NOTE not in updated:
            updated = updated.replace(END_MARKER, f"{END_MARKER}\n\n{FOOTER_NOTE}")
    else:
        # Replace existing static table under ### Gateway Profiles
        static_pattern = re.compile(
            r"(### Gateway Profiles\s*\n\s*)"
            r"(\| Gateway Model \| Protocol Support \|.*?\n)(?=\s*\n### |\s*\n---|\s*\n## )",
            re.DOTALL,
        )
        if not static_pattern.search(content):
            raise ValueError(f"Could not find markers or static Gateway Profiles table in {readme_path.name}")
        replacement = f"\\1{expected_block}\n\n{FOOTER_NOTE}\n"
        updated = static_pattern.sub(replacement, content)

    if updated == content:
        return False

    readme_path.write_text(updated, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI interface for updating or checking the Gateway Profiles table."""
    parser = argparse.ArgumentParser(
        description="Update or check the Gateway Profiles table in README.md"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated table block to stdout without modifying README.md",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether README.md is in sync without modifying it",
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=README_MD,
        help="Path to README.md (default: repo root README.md)",
    )
    parser.add_argument(
        "--const",
        type=Path,
        default=CONST_PY,
        help="Path to const.py (default: custom_components/myhome/const.py)",
    )

    args = parser.parse_args(argv)

    if args.dry_run:
        print(build_block(args.const))
        return 0

    if args.check:
        in_sync, msg = check_readme_in_sync(args.readme, args.const)
        if in_sync:
            print(f"OK: {msg}")
            return 0
        print(f"ERROR: {msg}")
        return 1

    changed = update_readme(args.readme, args.const)
    if changed:
        print(f"Updated Gateway Profiles table in {args.readme.name}")
    else:
        print(f"Gateway Profiles table in {args.readme.name} is already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
