#!/usr/bin/env python3
"""Automated Documentation Synchronization & Anti-Drift Sentinel.

Validates and synchronizes documentation (README.md and the docs/ MkDocs github.io site)
against the codebase:
1. Gateway Profiles table (README.md, docs/getting-started/hardware-compatibility.md,
   docs/configuration/gateways.md, docs/index.md) cross-referenced with const.py.
2. Supported Entity Domains & Automations table (README.md, docs/configuration/supported_functions.md)
   cross-referenced with const.py (PLATFORMS) and device_trigger.py.
3. Hardware Trace Availability Matrix (README.md, docs/trace-availability.md)
   cross-referenced with actual test fixtures.
4. Services & Actions Reference (docs/configuration/services.md)
   cross-referenced with custom_components/myhome/services.yaml.
5. Home Assistant Repairs Issues (docs/diagnostics/repair-issues.md)
   cross-referenced with custom_components/myhome/repairs.py and strings.json.
6. MkDocs navigation & link integrity.

CLI Modes:
- python scripts/sync_documentation.py --check: Verifies docs are in sync, exits 1 on drift.
- python scripts/sync_documentation.py --update: Rewrites out-of-sync doc blocks in place.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CUSTOM_COMPONENTS_DIR = REPO_ROOT / "custom_components" / "myhome"
CONST_PY = CUSTOM_COMPONENTS_DIR / "const.py"
SERVICES_YAML = CUSTOM_COMPONENTS_DIR / "services.yaml"
STRINGS_JSON = CUSTOM_COMPONENTS_DIR / "strings.json"
REPAIRS_PY = CUSTOM_COMPONENTS_DIR / "repairs.py"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"
README_MD = REPO_ROOT / "README.md"
DOCS_DIR = REPO_ROOT / "docs"

# Documentation target files for Gateway Profiles table
GATEWAY_DOC_TARGETS = [
    README_MD,
    DOCS_DIR / "getting-started" / "hardware-compatibility.md",
    DOCS_DIR / "configuration" / "gateways.md",
    DOCS_DIR / "index.md",
]

# Markers
GATEWAY_START_MARKER = "<!-- GATEWAY_PROFILES_START -->"
GATEWAY_END_MARKER = "<!-- GATEWAY_PROFILES_END -->"

DOMAINS_START_MARKER = "<!-- SUPPORTED_DOMAINS_START -->"
DOMAINS_END_MARKER = "<!-- SUPPORTED_DOMAINS_END -->"

TRACE_START_MARKER = "<!-- TRACE_MATRIX_START -->"
TRACE_END_MARKER = "<!-- TRACE_MATRIX_END -->"

SERVICES_START_MARKER = "<!-- SERVICES_TABLE_START -->"
SERVICES_END_MARKER = "<!-- SERVICES_TABLE_END -->"


def rel_path(p: Path) -> str:
    """Safely return path relative to REPO_ROOT, or path string if outside."""
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Gateway Profiles Synchronization
# ─────────────────────────────────────────────────────────────────────────────

def get_gateway_block() -> str:
    """Build the canonical Gateway Profiles table block."""
    try:
        from scripts.update_gateway_profiles import build_block
    except ImportError:
        from update_gateway_profiles import build_block
    return build_block(CONST_PY)


def sync_gateway_profiles(update: bool = False) -> tuple[bool, list[str]]:
    """Check or update the Gateway Profiles table across all target files."""
    messages: list[str] = []
    all_ok = True
    expected_block = get_gateway_block().strip()
    pattern = re.compile(
        rf"{re.escape(GATEWAY_START_MARKER)}.*?{re.escape(GATEWAY_END_MARKER)}",
        re.DOTALL,
    )

    for target in GATEWAY_DOC_TARGETS:
        if not target.exists():
            messages.append(f"Gateway target not found: {rel_path(target)}")
            all_ok = False
            continue

        content = target.read_text(encoding="utf-8")
        if GATEWAY_START_MARKER not in content or GATEWAY_END_MARKER not in content:
            messages.append(
                f"Missing markers {GATEWAY_START_MARKER} and/or {GATEWAY_END_MARKER} "
                f"in {rel_path(target)}"
            )
            all_ok = False
            continue

        match = pattern.search(content)
        if not match:
            messages.append(f"Could not parse marker block in {rel_path(target)}")
            all_ok = False
            continue

        actual_block = match.group(0).strip()
        if actual_block != expected_block:
            if update:
                new_content = pattern.sub(expected_block, content)
                target.write_text(new_content, encoding="utf-8")
                messages.append(f"Updated Gateway Profiles table in {rel_path(target)}")
            else:
                messages.append(
                    f"Gateway Profiles table out of sync in {rel_path(target)}"
                )
                all_ok = False
        else:
            messages.append(f"Gateway Profiles table in sync: {rel_path(target)}")

    return all_ok, messages


# ─────────────────────────────────────────────────────────────────────────────
# 2. Supported Entity Domains & Automations Synchronization
# ─────────────────────────────────────────────────────────────────────────────

def sync_supported_domains(update: bool = False) -> tuple[bool, list[str]]:
    """Check or update the Supported Entity Domains table in README.md."""
    try:
        from scripts.update_supported_domains import (
            check_readme_in_sync,
            update_readme,
        )
    except ImportError:
        from update_supported_domains import (
            check_readme_in_sync,
            update_readme,
        )

    messages: list[str] = []
    if update:
        changed = update_readme(README_MD)
        if changed:
            messages.append("Updated Supported Entity Domains table in README.md")
        else:
            messages.append("Supported Entity Domains table in README.md is already up to date")
        return True, messages

    in_sync, msg = check_readme_in_sync(README_MD)
    if not in_sync:
        messages.append(f"Supported Entity Domains table out of sync: {msg}")
        return False, messages

    messages.append("Supported Entity Domains table in sync: README.md")
    return True, messages


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hardware Trace Availability Matrix Synchronization
# ─────────────────────────────────────────────────────────────────────────────

def sync_trace_matrix(update: bool = False) -> tuple[bool, list[str]]:
    """Check or update the Hardware Trace Matrix across README.md and docs/trace-availability.md."""
    try:
        from scripts.update_trace_matrix import build_matrix, update_file
    except ImportError:
        from update_trace_matrix import build_matrix, update_file

    matrix_md = build_matrix()
    expected_block = f"{TRACE_START_MARKER}\n{matrix_md}\n{TRACE_END_MARKER}".strip()
    pattern = re.compile(
        rf"{re.escape(TRACE_START_MARKER)}.*?{re.escape(TRACE_END_MARKER)}",
        re.DOTALL,
    )

    targets = [README_MD, DOCS_DIR / "trace-availability.md"]
    messages: list[str] = []
    all_ok = True

    for target in targets:
        if not target.exists():
            messages.append(f"Trace matrix target not found: {rel_path(target)}")
            all_ok = False
            continue

        content = target.read_text(encoding="utf-8")
        if TRACE_START_MARKER not in content or TRACE_END_MARKER not in content:
            messages.append(
                f"Missing markers {TRACE_START_MARKER} / {TRACE_END_MARKER} in {rel_path(target)}"
            )
            all_ok = False
            continue

        match = pattern.search(content)
        if not match:
            messages.append(f"Could not parse trace matrix block in {rel_path(target)}")
            all_ok = False
            continue

        if match.group(0).strip() != expected_block:
            if update:
                update_file(target, matrix_md)
                messages.append(f"Updated Trace Matrix in {rel_path(target)}")
            else:
                messages.append(f"Trace Matrix out of sync in {rel_path(target)}")
                all_ok = False
        else:
            messages.append(f"Trace Matrix in sync: {rel_path(target)}")

    return all_ok, messages


# ─────────────────────────────────────────────────────────────────────────────
# 4. Services Reference Synchronization
# ─────────────────────────────────────────────────────────────────────────────

def parse_services_yaml() -> dict[str, Any]:
    """Parse custom_components/myhome/services.yaml."""
    if not SERVICES_YAML.exists():
        raise FileNotFoundError(f"{SERVICES_YAML} not found")

    content = SERVICES_YAML.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(content) or {}
    except ImportError:
        # Simple fallback parser if PyYAML is not installed
        services: dict[str, Any] = {}
        current_service = None
        for line in content.splitlines():
            if line and not line.startswith(" ") and line.endswith(":"):
                current_service = line.rstrip(":")
                services[current_service] = {}
        return services


def generate_services_summary_table(services_data: dict[str, Any]) -> str:
    """Generate the markdown table for services summary."""
    lines = [
        "| Service | Target | Description |",
        "| :--- | :--- | :--- |",
    ]

    for service_name, s_data in sorted(services_data.items()):
        # Determine target
        target = "Gateway"
        if isinstance(s_data, dict):
            target_dict = s_data.get("target", {})
            if isinstance(target_dict, dict) and "entity" in target_dict:
                ent = target_dict["entity"]
                if isinstance(ent, dict) and "domain" in ent:
                    dom = ent["domain"]
                    if isinstance(dom, list):
                        target = ", ".join(f"`{d}`" for d in dom)
                    elif isinstance(dom, str):
                        target = f"`{dom}`"
            elif service_name in ("start_sending_instant_power",):
                target = "`sensor`"

            description = s_data.get("description", "").strip().split("\n")[0]
            # Strip trailing markdown if any
            if not description.endswith("."):
                description = f"{description}."
        else:
            description = ""

        anchor = f"#myhome{service_name}"
        lines.append(f"| [`myhome.{service_name}`]({anchor}) | {target} | {description} |")

    return "\n".join(lines)


def build_services_table_block() -> str:
    """Return the marker-wrapped services summary table block."""
    services_data = parse_services_yaml()
    table = generate_services_summary_table(services_data)
    return f"{SERVICES_START_MARKER}\n{table}\n{SERVICES_END_MARKER}"


def sync_services(update: bool = False) -> tuple[bool, list[str]]:
    """Check or update services documentation against services.yaml."""
    services_doc = DOCS_DIR / "configuration" / "services.md"
    if not services_doc.exists():
        return False, [f"{services_doc} does not exist"]

    messages: list[str] = []
    all_ok = True
    services_data = parse_services_yaml()
    doc_content = services_doc.read_text(encoding="utf-8")

    # 1. Check all services are documented with a heading
    missing_sections = []
    for service_name in services_data:
        # Expect heading like '## myhome.service_name' or '## 1. `myhome.service_name`'
        pattern = re.compile(rf"##\s+(?:\d+\.\s+)?`?myhome\.{re.escape(service_name)}`?", re.IGNORECASE)
        if not pattern.search(doc_content):
            missing_sections.append(f"myhome.{service_name}")

    if missing_sections:
        messages.append(f"Services missing documentation sections in services.md: {missing_sections}")
        all_ok = False
    else:
        messages.append(f"All {len(services_data)} services have documented sections in services.md")

    # 2. Check all parameter fields are documented
    missing_fields: list[str] = []
    for service_name, s_data in services_data.items():
        if isinstance(s_data, dict) and "fields" in s_data:
            fields = s_data["fields"]
            if isinstance(fields, dict):
                for field_name in fields:
                    if f"`{field_name}`" not in doc_content and f"| {field_name} |" not in doc_content:
                        missing_fields.append(f"myhome.{service_name} field '{field_name}'")

    if missing_fields:
        messages.append(f"Service fields missing in services.md: {missing_fields}")
        all_ok = False
    else:
        messages.append("All service parameter fields are documented in services.md")

    # 3. Synchronize Summary Table if markers exist
    if SERVICES_START_MARKER in doc_content and SERVICES_END_MARKER in doc_content:
        pattern = re.compile(
            rf"{re.escape(SERVICES_START_MARKER)}.*?{re.escape(SERVICES_END_MARKER)}",
            re.DOTALL,
        )
        expected_block = build_services_table_block().strip()
        match = pattern.search(doc_content)
        if match and match.group(0).strip() != expected_block:
            if update:
                new_content = pattern.sub(expected_block, doc_content)
                services_doc.write_text(new_content, encoding="utf-8")
                messages.append("Updated Services Summary table in docs/configuration/services.md")
            else:
                messages.append("Services Summary table out of sync in docs/configuration/services.md")
                all_ok = False
        else:
            messages.append("Services Summary table in sync: docs/configuration/services.md")

    return all_ok, messages


# ─────────────────────────────────────────────────────────────────────────────
# 5. Repair Issues Synchronization
# ─────────────────────────────────────────────────────────────────────────────

def extract_repair_issues_from_code() -> set[str]:
    """Extract all ISSUE_* constants from custom_components/myhome/repairs.py."""
    if not REPAIRS_PY.exists():
        return set()

    issues: set[str] = set()
    tree = ast.parse(REPAIRS_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("ISSUE_"):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        issues.add(node.value.value)
    return issues


def extract_repair_issues_from_strings() -> set[str]:
    """Extract issues keys from custom_components/myhome/strings.json."""
    if not STRINGS_JSON.exists():
        return set()
    try:
        data = json.loads(STRINGS_JSON.read_text(encoding="utf-8"))
        return set(data.get("issues", {}).keys())
    except Exception:
        return set()


def sync_repair_issues(update: bool = False) -> tuple[bool, list[str]]:
    """Verify docs/diagnostics/repair-issues.md documents all registered repair issues."""
    repair_doc = DOCS_DIR / "diagnostics" / "repair-issues.md"
    if not repair_doc.exists():
        return False, [f"{repair_doc} does not exist"]

    messages: list[str] = []
    all_ok = True

    code_issues = extract_repair_issues_from_code()
    strings_issues = extract_repair_issues_from_strings()
    all_known_issues = code_issues | strings_issues

    doc_content = repair_doc.read_text(encoding="utf-8")
    missing_in_docs: list[str] = []

    for issue_key in sorted(all_known_issues):
        # Look for **Repair Key**: `issue_key` or `Repair Key: `issue_key``
        pattern = re.compile(rf"Repair Key[:\*`\s]+`?{re.escape(issue_key)}`?", re.IGNORECASE)
        if not pattern.search(doc_content):
            missing_in_docs.append(issue_key)

    if missing_in_docs:
        messages.append(
            f"Repair issues defined in code/strings but missing from repair-issues.md: {missing_in_docs}"
        )
        all_ok = False
    else:
        messages.append(
            f"All {len(all_known_issues)} repair issues are documented in docs/diagnostics/repair-issues.md"
        )

    return all_ok, messages


# ─────────────────────────────────────────────────────────────────────────────
# 6. MkDocs Navigation & Markdown Link Health
# ─────────────────────────────────────────────────────────────────────────────

def sync_mkdocs_nav(update: bool = False) -> tuple[bool, list[str]]:
    """Verify mkdocs.yml navigation includes all markdown documentation pages."""
    if not MKDOCS_YML.exists():
        return False, [f"{MKDOCS_YML} not found"]

    messages: list[str] = []
    all_ok = True
    mkdocs_text = MKDOCS_YML.read_text(encoding="utf-8")

    # Excluded files not meant for top-level navigation
    EXCLUDED_DOCS = {
        "index.md",
    }

    unlisted_pages: list[str] = []
    for md_file in DOCS_DIR.rglob("*.md"):
        rel_path = md_file.relative_to(DOCS_DIR).as_posix()
        if rel_path in EXCLUDED_DOCS:
            continue
        if rel_path not in mkdocs_text:
            unlisted_pages.append(rel_path)

    if unlisted_pages:
        messages.append(f"Markdown pages missing from mkdocs.yml navigation: {unlisted_pages}")
        all_ok = False
    else:
        messages.append("All documentation pages are referenced in mkdocs.yml navigation")

    return all_ok, messages


def check_markdown_link_health() -> tuple[bool, list[str]]:
    """Check for malformed anchor links (e.g. emoji prefixes '#-') across docs/."""
    messages: list[str] = []
    all_ok = True

    # Pattern for anchor links with emoji-stripped leading hyphen like '#-'
    bad_anchor_pattern = re.compile(r"\[([^\]]+)\]\((\S*?#-[\w-]+)\)")

    for md_file in DOCS_DIR.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        matches = bad_anchor_pattern.findall(content)
        if matches:
            for text, link in matches:
                messages.append(
                    f"Malformed anchor '{link}' (stripped emoji leading hyphen) in {rel_path(md_file)}"
                )
                all_ok = False

    if all_ok:
        messages.append("All markdown anchor links validated cleanly (0 malformed emoji anchors).")

    return all_ok, messages


# ─────────────────────────────────────────────────────────────────────────────
# Master Routine & CLI Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def check_all_documentation(update: bool = False) -> tuple[bool, list[str]]:
    """Run all documentation synchronization checks or updates.

    Returns (is_all_in_sync, list_of_report_messages).
    """
    overall_ok = True
    all_messages: list[str] = []

    # 1. Gateway profiles
    ok_gw, msgs_gw = sync_gateway_profiles(update=update)
    overall_ok = overall_ok and ok_gw
    all_messages.extend(msgs_gw)

    # 2. Supported domains
    ok_dom, msgs_dom = sync_supported_domains(update=update)
    overall_ok = overall_ok and ok_dom
    all_messages.extend(msgs_dom)

    # 3. Trace matrix
    ok_trace, msgs_trace = sync_trace_matrix(update=update)
    overall_ok = overall_ok and ok_trace
    all_messages.extend(msgs_trace)

    # 4. Services
    ok_srv, msgs_srv = sync_services(update=update)
    overall_ok = overall_ok and ok_srv
    all_messages.extend(msgs_srv)

    # 5. Repairs
    ok_rep, msgs_rep = sync_repair_issues(update=update)
    overall_ok = overall_ok and ok_rep
    all_messages.extend(msgs_rep)

    # 6. MkDocs nav
    ok_nav, msgs_nav = sync_mkdocs_nav(update=update)
    overall_ok = overall_ok and ok_nav
    all_messages.extend(msgs_nav)

    # 7. Anchor links
    ok_anchors, msgs_anchors = check_markdown_link_health()
    overall_ok = overall_ok and ok_anchors
    all_messages.extend(msgs_anchors)

    return overall_ok, all_messages


def main(argv: list[str] | None = None) -> int:
    """CLI interface for documentation synchronization and anti-drift validation."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Validate or synchronize documentation against the MyHOME codebase."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether documentation is in sync without modifying files (exit 1 on drift)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update all out-of-sync documentation tables and marker blocks in place",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict zero-warning validation",
    )

    args = parser.parse_args(argv)

    # Default mode is --check if neither --check nor --update is given
    do_update = args.update and not args.check

    print("=" * 70)
    print("Running Documentation Anti-Drift Sentinel & Synchronizer")
    print("Mode:", "UPDATE" if do_update else "CHECK")
    print("=" * 70)

    in_sync, messages = check_all_documentation(update=do_update)

    for msg in messages:
        print(f"  • {msg}")

    print("=" * 70)
    if in_sync:
        print("SUCCESS: All documentation is calibrated and in sync with the codebase!\n")
        return 0
    else:
        if do_update:
            print("WARNING: Some documentation files required manual review or were updated.\n")
            return 0 if not args.strict else 1
        else:
            print("FAILED: Documentation drift detected! Run 'python scripts/sync_documentation.py --update' to sync.\n")
            return 1


if __name__ == "__main__":
    sys.exit(main())
