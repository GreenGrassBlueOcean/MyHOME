"""Tests for H4684 and LGRH4684 Gateway Identification Synthetic Trace Replay.

Verifies deterministic replay of gateway model identification frames synthesized
from static disassembly of Legrand / BTicino bt_device daemon (firmware 2.0.54,
TiDisplayColorIP build 0x02003194, catalogued in own-firmware-oracle PR #26 and OWNd PR #96):
1. WHO 13 Dimension 15 resolution:
   - Code 13 (BTicino 2006 table & bt_device) -> H4684
   - Code 20 (bt_device Legrand brand) -> WHO 13 unmapped, settled by WHO 1013
2. WHO 1013 Dimension 1 diagnostic object model resolution:
   - Code 19 (bt_device primary dispatch) -> H4684
   - Code 26 (bt_device Legrand primary dispatch) -> LGRH4684
3. Profile binding:
   - Both H4684 and LGRH4684 bind to H4684Profile.
4. Zero identity conflicts and zero device health faults across replay cycles.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from OWNd.message import OWNEvent
from OWNd.profiles import H4684Profile, get_gateway_profile

from custom_components.myhome.gateway import MyHOMEGatewayHandler

TRACES_DIR = Path(__file__).resolve().parent / "fixtures" / "traces" / "oracle_h4684_gateway"
TRACE_FILE = TRACES_DIR / "myhome_trace_oracle_h4684_gateway_identification.json"


def _create_mock_handler(data_overrides: dict | None = None) -> MyHOMEGatewayHandler:
    """Create a mock MyHOMEGatewayHandler for identification trace replay."""
    entry = MagicMock()
    entry.entry_id = "test_h4684_entry"
    entry.title = "H4684 Gateway"
    entry.data = {
        "host": "192.168.1.50",
        "port": 20000,
        "name": "H4684",
        "model_source": "auto",
        "ssdp_location": None,
        "UDN": None,
    }
    entry.data.update(data_overrides or {})
    hass = MagicMock()
    hass.data = {}
    h = MyHOMEGatewayHandler(hass, entry)
    h.device_registry_id = "dev_h4684"
    return h


def test_h4684_trace_fixture_integrity():
    """Verify schema integrity of the synthetic H4684 trace fixture."""
    assert TRACE_FILE.is_file(), f"Trace fixture missing: {TRACE_FILE}"
    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    assert trace_data["gateway"]["model"] == "H4684"
    assert trace_data["gateway"]["firmware"] == "2.0.54"
    frames = trace_data["frames"]
    assert len(frames) == 8

    raw_frames = [f["raw"] for f in frames]
    assert "*#13**15*13##" in raw_frames
    assert "*#13**16*2*0*54##" in raw_frames
    assert "*#1013**1*19*15*5*0##" in raw_frames
    assert "*#13**15*20##" in raw_frames
    assert "*#1013**1*26*15*5*0##" in raw_frames


def test_h4684_synthetic_identification_trace_replay():
    """Replay complete gateway identification sequence for BTicino H4684."""
    dev_reg = MagicMock()
    dev_reg.async_get.return_value = MagicMock(model="H4684")

    with patch("homeassistant.helpers.device_registry.async_get", return_value=dev_reg), \
         patch("custom_components.myhome.gateway.async_create_identity_issue") as create_issue, \
         patch("custom_components.myhome.gateway.async_create_identity_corrected_issue") as corrected_issue:
        h = _create_mock_handler({"name": "H4684"})

        # Step 1: Gateway reports device type code 13 on WHO 13
        h._handle_gateway_diagnostics(OWNEvent.parse("*#13**15*13##"))
        assert h._who13["code"] == "13"
        assert h._who13["model"] == "H4684"

        # Step 2: Gateway reports firmware version 2.0.54
        h._handle_gateway_diagnostics(OWNEvent.parse("*#13**16*2*0*54##"))
        assert h._who13["firmware"] == "2.0.54"

        # Step 3: Gateway reports WHO 1013 diagnostic object model 19
        h._handle_gateway_identity_diagnostics(OWNEvent.parse("*#1013**1*19*15*5*0##"))
        assert h._who1013["code"] == "19"
        assert h._who1013["model"] == "H4684"
        assert h._who1013["n_conf"] == "15"
        assert h._who1013["brand"] == "5"
        assert h._who1013["line"] == "0"

        # Step 4: Verify identification dictionary
        ident = h.identification()
        assert ident["model"] == "H4684"
        assert ident["who13_code"] == "13"
        assert ident["who13_firmware"] == "2.0.54"
        assert ident["who1013_code"] == "19"
        assert ident["who1013_n_conf"] == "15"
        assert ident["who1013_brand"] == "5 (Legrand BTicino)"
        assert ident["who1013_line"] == "0 (Undefined)"
        assert ident["profile"] == "H4684Profile"
        assert ident["conflict"] is None

        # Verify device profile instantiation
        profile = get_gateway_profile(ident["model"])
        assert isinstance(profile, H4684Profile)
        assert profile.model_name == "H4684"

        # Step 5: Zero faults and zero repair issues
        assert h.device_health.faults == []
        create_issue.assert_not_called()
        corrected_issue.assert_not_called()


def test_lgrh4684_synthetic_identification_trace_replay():
    """Replay complete gateway identification sequence for Legrand LGRH4684."""
    dev_reg = MagicMock()
    dev_reg.async_get.return_value = MagicMock(model="LGRH4684")

    with patch("homeassistant.helpers.device_registry.async_get", return_value=dev_reg), \
         patch("custom_components.myhome.gateway.async_create_identity_issue") as create_issue, \
         patch("custom_components.myhome.gateway.async_create_identity_corrected_issue") as corrected_issue:
        h = _create_mock_handler({"name": "LGRH4684"})

        # Step 1: Gateway reports device type code 20 on WHO 13 (unmapped in WHO 13 tables)
        h._handle_gateway_diagnostics(OWNEvent.parse("*#13**15*20##"))
        assert h._who13["code"] == "20"
        assert h._who13["model"] is None

        # Step 2: Gateway reports WHO 1013 diagnostic object model 26 (settles model)
        h._handle_gateway_identity_diagnostics(OWNEvent.parse("*#1013**1*26*15*5*0##"))
        assert h._who1013["code"] == "26"
        assert h._who1013["model"] == "LGRH4684"

        # Step 3: Verify identification dictionary
        ident = h.identification()
        assert ident["model"] == "LGRH4684"
        assert ident["who13_code"] == "20"
        assert ident["who1013_code"] == "26"
        assert ident["who1013_brand"] == "5 (Legrand BTicino)"
        assert ident["who1013_line"] == "0 (Undefined)"
        assert ident["profile"] == "H4684Profile"
        assert ident["conflict"] is None

        # Verify profile alias resolves to H4684Profile
        profile = get_gateway_profile(ident["model"])
        assert isinstance(profile, H4684Profile)
        assert profile.model_name == "H4684"

        # Step 4: Zero faults and zero repair issues
        assert h.device_health.faults == []
        create_issue.assert_not_called()
        corrected_issue.assert_not_called()


def test_shared_code_200_resolved_to_h4684_by_who1013():
    """Verify shared code 200 is settled cleanly by WHO 1013 object model 19."""
    dev_reg = MagicMock()
    dev_reg.async_get.return_value = MagicMock(model="F454")

    with patch("homeassistant.helpers.device_registry.async_get", return_value=dev_reg):
        h = _create_mock_handler({"name": "MyHome Gateway"})

        # Gateway reports shared code 200
        h._handle_gateway_diagnostics(OWNEvent.parse("*#13**15*200##"))
        assert h._who13["code"] == "200"

        # Diagnostic response arrives settling model to H4684
        h._handle_gateway_identity_diagnostics(OWNEvent.parse("*#1013**1*19*15*5*0##"))
        ident = h.identification()
        assert ident["model"] == "H4684"
        assert ident["who13_code"] == "200"
        assert ident["who1013_code"] == "19"
        assert ident["conflict"] is None
        assert ident["profile"] == "H4684Profile"


def test_shared_code_200_resolved_to_lgrh4684_by_who1013():
    """Verify shared code 200 is settled cleanly by WHO 1013 object model 26."""
    dev_reg = MagicMock()
    dev_reg.async_get.return_value = MagicMock(model="F454")

    with patch("homeassistant.helpers.device_registry.async_get", return_value=dev_reg):
        h = _create_mock_handler({"name": "MyHome Gateway"})

        # Gateway reports shared code 200
        h._handle_gateway_diagnostics(OWNEvent.parse("*#13**15*200##"))
        assert h._who13["code"] == "200"

        # Diagnostic response arrives settling model to LGRH4684
        h._handle_gateway_identity_diagnostics(OWNEvent.parse("*#1013**1*26*15*5*0##"))
        ident = h.identification()
        assert ident["model"] == "LGRH4684"
        assert ident["who13_code"] == "200"
        assert ident["who1013_code"] == "26"
        assert ident["conflict"] is None
        assert ident["profile"] == "H4684Profile"
