"""Tests for scripts/sync_documentation.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync_documentation.py"

spec = importlib.util.spec_from_file_location("sync_documentation", SCRIPT)
syncdoc = importlib.util.module_from_spec(spec)
sys.modules["sync_documentation"] = syncdoc
spec.loader.exec_module(syncdoc)

GATEWAY_START_MARKER = syncdoc.GATEWAY_START_MARKER
GATEWAY_END_MARKER = syncdoc.GATEWAY_END_MARKER
SERVICES_START_MARKER = syncdoc.SERVICES_START_MARKER
SERVICES_END_MARKER = syncdoc.SERVICES_END_MARKER


def test_sync_gateway_profiles_all_in_sync():
    """Verify sync_gateway_profiles returns all_ok=True on clean repository."""
    ok, messages = syncdoc.sync_gateway_profiles(update=False)
    assert ok is True
    assert len(messages) >= len(syncdoc.GATEWAY_DOC_TARGETS)
    for target in syncdoc.GATEWAY_DOC_TARGETS:
        assert any(str(target.name) in m for m in messages)


def test_sync_gateway_profiles_detects_drift(tmp_path, monkeypatch):
    """Verify sync_gateway_profiles detects out of sync content and updates it."""
    dummy_file = tmp_path / "dummy_gateways.md"
    dummy_file.write_text(
        f"{GATEWAY_START_MARKER}\nOld Outdated Table\n{GATEWAY_END_MARKER}",
        encoding="utf-8",
    )

    monkeypatch.setattr(syncdoc, "GATEWAY_DOC_TARGETS", [dummy_file])

    # Check mode should fail
    ok, messages = syncdoc.sync_gateway_profiles(update=False)
    assert ok is False
    assert any("out of sync" in m for m in messages)

    # Update mode should succeed
    ok, messages = syncdoc.sync_gateway_profiles(update=True)
    assert ok is True
    assert any("Updated Gateway Profiles table" in m for m in messages)

    # Subsequent check mode should now pass
    ok, messages = syncdoc.sync_gateway_profiles(update=False)
    assert ok is True


def test_sync_gateway_profiles_missing_target(tmp_path, monkeypatch):
    """Verify sync_gateway_profiles handles missing files and missing markers."""
    missing_file = tmp_path / "nonexistent.md"
    no_marker_file = tmp_path / "no_markers.md"
    no_marker_file.write_text("Hello world", encoding="utf-8")

    monkeypatch.setattr(syncdoc, "GATEWAY_DOC_TARGETS", [missing_file, no_marker_file])

    ok, messages = syncdoc.sync_gateway_profiles(update=False)
    assert ok is False
    assert any("not found" in m for m in messages)
    assert any("Missing markers" in m for m in messages)


def test_sync_supported_domains():
    """Verify sync_supported_domains checks README.md domains table."""
    ok, messages = syncdoc.sync_supported_domains(update=False)
    assert ok is True
    assert any("in sync" in m for m in messages)

    ok_up, messages_up = syncdoc.sync_supported_domains(update=True)
    assert ok_up is True


def test_sync_trace_matrix():
    """Verify sync_trace_matrix checks README.md and docs/trace-availability.md."""
    ok, messages = syncdoc.sync_trace_matrix(update=False)
    assert ok is True
    assert len(messages) >= 2


def test_sync_trace_matrix_missing_target(tmp_path, monkeypatch):
    """Verify sync_trace_matrix handles missing file and missing markers."""
    dummy_missing = tmp_path / "missing.md"
    dummy_nomarkers = tmp_path / "nomarkers.md"
    dummy_nomarkers.write_text("text without markers", encoding="utf-8")

    # Call with fake targets
    orig_dir = syncdoc.DOCS_DIR
    try:
        monkeypatch.setattr(syncdoc, "README_MD", dummy_missing)
        monkeypatch.setattr(syncdoc, "DOCS_DIR", tmp_path)
        ok, msgs = syncdoc.sync_trace_matrix(update=False)
        assert ok is False
        assert any("not found" in m for m in msgs)
    finally:
        monkeypatch.setattr(syncdoc, "DOCS_DIR", orig_dir)


def test_parse_services_yaml():
    """Verify parse_services_yaml extracts services correctly."""
    services = syncdoc.parse_services_yaml()
    assert "send_message" in services
    assert "turn_on_timed" in services
    assert "sync_time" in services
    assert "sweep_bus" in services
    assert "calibrate_cover" in services
    assert "stop_cover_calibration" in services
    assert "set_cover_travel_time" in services
    assert "reset_cover_travel_time" in services
    assert "start_sending_instant_power" in services
    assert len(services) == 9


def test_sync_services_all_in_sync():
    """Verify sync_services passes on current docs/configuration/services.md."""
    ok, messages = syncdoc.sync_services(update=False)
    assert ok is True
    assert any("All 9 services have documented sections" in m for m in messages)
    assert any("All service parameter fields are documented" in m for m in messages)


def test_sync_services_detects_missing_section(tmp_path, monkeypatch):
    """Verify sync_services flags when a service section is absent in doc."""
    dummy_services_doc = tmp_path / "services.md"
    dummy_services_doc.write_text("## Only one service\n", encoding="utf-8")

    monkeypatch.setattr(syncdoc, "DOCS_DIR", tmp_path)
    (tmp_path / "configuration").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "configuration" / "services.md"
    target.write_text("## Only partial doc\n", encoding="utf-8")

    ok, messages = syncdoc.sync_services(update=False)
    assert ok is False
    assert any("Services missing documentation sections" in m for m in messages)


def test_sync_services_missing_file(tmp_path, monkeypatch):
    """Verify sync_services handles missing services.md file."""
    monkeypatch.setattr(syncdoc, "DOCS_DIR", tmp_path)
    ok, messages = syncdoc.sync_services(update=False)
    assert ok is False
    assert any("does not exist" in m for m in messages)


def test_extract_repair_issues_from_code_and_strings():
    """Verify repair issues are extracted from repairs.py and strings.json."""
    code_issues = syncdoc.extract_repair_issues_from_code()
    strings_issues = syncdoc.extract_repair_issues_from_strings()

    assert "gateway_authentication_failed" in code_issues
    assert "bus_collision_storm" in code_issues
    assert "gateway_identity_mismatch" in code_issues
    assert "unknown_gateway_model" in code_issues
    assert "unconfigured_timezone" in code_issues
    assert "gateway_identity_corrected" in code_issues
    assert "incompatible_decoder_platform" in code_issues

    assert code_issues.issubset(strings_issues) or strings_issues.issubset(code_issues)


def test_sync_repair_issues_all_in_sync():
    """Verify sync_repair_issues confirms all repair issues are documented."""
    ok, messages = syncdoc.sync_repair_issues(update=False)
    assert ok is True
    assert any("repair issues are documented" in m for m in messages)


def test_sync_repair_issues_missing_issue(tmp_path, monkeypatch):
    """Verify sync_repair_issues detects an undocumented repair issue."""
    (tmp_path / "diagnostics").mkdir(parents=True, exist_ok=True)
    dummy_repairs_doc = tmp_path / "diagnostics" / "repair-issues.md"
    dummy_repairs_doc.write_text("## No keys here\n", encoding="utf-8")

    monkeypatch.setattr(syncdoc, "DOCS_DIR", tmp_path)
    ok, messages = syncdoc.sync_repair_issues(update=False)
    assert ok is False
    assert any("missing from repair-issues.md" in m for m in messages)


def test_sync_mkdocs_nav():
    """Verify mkdocs.yml navigation contains all doc files."""
    ok, messages = syncdoc.sync_mkdocs_nav(update=False)
    assert ok is True
    assert any("All documentation pages are referenced" in m for m in messages)


def test_check_markdown_link_health():
    """Verify all markdown links have clean anchors without malformed emoji prefixes."""
    ok, messages = syncdoc.check_markdown_link_health()
    assert ok is True
    assert any("0 malformed emoji anchors" in m for m in messages)


def test_check_markdown_link_health_detects_malformed(tmp_path, monkeypatch):
    """Verify check_markdown_link_health flags links like [test](#-bad-anchor)."""
    bad_doc = tmp_path / "bad.md"
    bad_doc.write_text("Here is a [bad link](#-bad-anchor)", encoding="utf-8")

    monkeypatch.setattr(syncdoc, "DOCS_DIR", tmp_path)
    ok, messages = syncdoc.check_markdown_link_health()
    assert ok is False
    assert any("Malformed anchor" in m for m in messages)


def test_check_all_documentation():
    """Verify check_all_documentation master orchestrator passes cleanly."""
    overall_ok, all_messages = syncdoc.check_all_documentation(update=False)
    assert overall_ok is True
    assert len(all_messages) > 10


def test_main_cli_check(capsys):
    """Verify CLI main entrypoint in --check mode exits 0."""
    code = syncdoc.main(["--check"])
    assert code == 0
    captured = capsys.readouterr()
    assert "SUCCESS: All documentation is calibrated and in sync" in captured.out


def test_main_cli_update(capsys):
    """Verify CLI main entrypoint in --update mode exits 0."""
    code = syncdoc.main(["--update"])
    assert code == 0
    captured = capsys.readouterr()
    assert "SUCCESS: All documentation is calibrated and in sync" in captured.out


def test_verify_ha_standards_documentation_rule():
    """Verify verify_ha_standards.py documentation anti-drift rule passes."""
    import scripts.verify_ha_standards as vha

    checker = vha.StandardsChecker()
    vha.check_documentation_anti_drift_rule(checker)
    assert len(checker.errors) == 0
