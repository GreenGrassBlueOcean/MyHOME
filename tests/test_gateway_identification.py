"""Gateway identification: SSDP / manual are authoritative, WHO=13 only corroborates.

The only official device-type table (BTicino OpenWebNet_Community_2_device v1.0.0,
2006-06-13, WHO=13 section 1.2.6) is: 2 MHServer, 4 MH200, 6 F452, 7 F452V,
11 MHServer2, 13 H4684. Every gateway sold after 2006 is absent from it.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from OWNd.message import OWNEvent

from custom_components.myhome.const import (
    GATEWAY_DEVICE_TYPE_MAP,
    IDENTIFICATION_MANUAL,
    IDENTIFICATION_SERIAL,
    IDENTIFICATION_SSDP,
    IDENTIFICATION_UNKNOWN,
    IDENTIFICATION_WHO13,
    WHO13_OBSERVED_DEVICE_TYPES,
    WHO13_OFFICIAL_DEVICE_TYPES,
    WHO13_SHARED_DEVICE_TYPES,
    WHO1013_OBJECT_MODELS,
    gateway_model_family,
)
from custom_components.myhome.gateway import MyHOMEGatewayHandler
from custom_components.myhome.identity import GatewayIdentityEvidence as Evidence
from custom_components.myhome.identity import read_who13, read_who1013
from custom_components.myhome.identity import resolve_gateway_identity as resolve

OFFICIAL_2006_TABLE = {"2": "MHServer", "4": "MH200", "6": "F452", "7": "F452V", "11": "MHServer2", "13": "H4684"}


def _handler(data_overrides=None, *, title="MH200 Gateway"):
    entry = MagicMock()
    entry.entry_id = "entry_ident"
    entry.title = title
    entry.data = {
        "host": "192.0.2.40",
        "port": 20000,
        "password": "x",
        "mac": "00:03:50:00:48:71",
        "name": "MH200",
        "manufacturer": "BTicino S.p.A.",
        "firmware": None,
        "ssdp_location": None,
        "UDN": None,
    }
    entry.data.update(data_overrides or {})
    hass = MagicMock()
    hass.data = {}
    h = MyHOMEGatewayHandler(hass, entry)
    h.device_registry_id = "dev_gw"
    return h


def _who13(h, code):
    h._handle_gateway_diagnostics(OWNEvent.parse(f"*#13**15*{code}##"))


@pytest.fixture
def dev_reg():
    reg = MagicMock()
    reg.async_get.return_value = MagicMock(model="MH200")
    with patch("homeassistant.helpers.device_registry.async_get", return_value=reg):
        yield reg


@pytest.fixture
def issues():
    with patch("custom_components.myhome.gateway.async_create_identity_issue") as create, \
         patch("custom_components.myhome.gateway.async_delete_identity_issue") as delete, \
         patch("custom_components.myhome.gateway.async_create_identity_corrected_issue") as corrected:
        yield create, delete, corrected


# ── the table itself ─────────────────────────────────────────────────────


def test_official_table_is_the_2006_document_verbatim():
    assert WHO13_OFFICIAL_DEVICE_TYPES == OFFICIAL_2006_TABLE
    # observed codes never shadow official ones
    assert not set(WHO13_OBSERVED_DEVICE_TYPES) & set(WHO13_OFFICIAL_DEVICE_TYPES)
    assert GATEWAY_DEVICE_TYPE_MAP["4"] == "MH200"
    assert "MH200N" not in GATEWAY_DEVICE_TYPE_MAP.values()
    # code 200: observed on F454 (#370), MyHOMEServer1 (#292 / #297), MH202; reported for F461 (#370)
    # code 51: F454 on a 1.x firmware (reported in PR #420)
    assert WHO13_OBSERVED_DEVICE_TYPES == {"51": ("F454",), "200": ("F454", "MyHomeServer1", "MH202", "F461")}
    assert WHO13_SHARED_DEVICE_TYPES == {"200"}
    assert WHO13_SHARED_DEVICE_TYPES <= set(WHO13_OBSERVED_DEVICE_TYPES)
    # every model a shared WHO=13 code may stand for has a WHO=1013 code that settles it
    who1013_families = {gateway_model_family(m) for models in WHO1013_OBJECT_MODELS.values() for m in models}
    for code in WHO13_SHARED_DEVICE_TYPES:
        for model in WHO13_OBSERVED_DEVICE_TYPES[code]:
            assert gateway_model_family(model) in who1013_families, (code, model)
    # WHO=1013 codes are unique per model: no model appears under two codes
    seen: dict[str, str] = {}
    for code, models in WHO1013_OBJECT_MODELS.items():
        for model in models:
            assert model not in seen, (model, seen.get(model), code)
            seen[model] = code


# ── reading a code ───────────────────────────────────────────────────────


def test_read_who13():
    official = read_who13("4")
    assert (official.models, official.certain, official.shared, official.raw) == (("MH200",), True, False, "4")
    assert official.compatible_with("MH200") is True
    assert official.compatible_with("MH200N") is True  # variant suffix, same family
    assert official.compatible_with("F454") is False  # a certain contradiction
    assert official.compatible_with(None) is False and official.compatible_with("") is False

    observed = read_who13("51")
    assert (observed.models, observed.certain, observed.shared) == (("F454",), False, False)
    assert observed.compatible_with("F454") is True
    assert observed.compatible_with("MH200") is None  # field evidence cannot contradict

    shared = read_who13("200")
    assert shared.shared and shared.known and shared.canonical == "F454"
    assert shared.compatible_with("F461") is True and shared.compatible_with("MH200") is None

    unknown = read_who13("999")
    assert not unknown.known and unknown.models == ()
    assert unknown.compatible_with("F454") is None
    assert read_who13("4").describe() == "WHO=13 device type 4"


def test_read_who1013():
    r = read_who1013("51")
    assert (r.models, r.certain, r.shared, r.raw, r.canonical) == (("F454", "003598"), True, False, "1013-1-51", "F454")
    # a catalogue SKU for the same OBJECT_MODEL is corroborated, not contradicted
    assert r.compatible_with("003598") is True
    assert r.compatible_with("F454") is True
    assert r.compatible_with("MyHomeServer1") is False
    assert read_who1013("999").known is False
    assert read_who1013("67").describe() == "WHO=1013 OBJECT_MODEL 67"


# ── the resolver: evidence in, verdict out ───────────────────────────────


def test_resolver_nothing_known():
    r = resolve(Evidence())
    assert (r.model, r.source, r.conflict, r.request_who1013, r.unknown_code) == (None, IDENTIFICATION_UNKNOWN, None, False, None)
    r = resolve(Evidence(manual="MH200"))
    assert (r.model, r.source) == ("MH200", IDENTIFICATION_MANUAL)
    r = resolve(Evidence(technical="F454", technical_source=IDENTIFICATION_SSDP))
    assert (r.model, r.source) == ("F454", IDENTIFICATION_SSDP)
    r = resolve(Evidence(technical="MH200"))  # source defaults to ssdp
    assert r.source == IDENTIFICATION_SSDP
    r = resolve(Evidence(prior_label="F452"))
    assert (r.model, r.source) == ("F452", IDENTIFICATION_WHO13)


def test_resolver_shared_who13_code_is_a_question_not_an_answer():
    for ev in (
        Evidence(who13_code="200"),
        Evidence(manual="MH200", who13_code="200"),
        Evidence(technical="F454", technical_source=IDENTIFICATION_SSDP, who13_code="200"),
        Evidence(technical="MH200", technical_source=IDENTIFICATION_SERIAL, who13_code="200"),
        Evidence(prior_label="F452", who13_code="200"),
    ):
        r = resolve(ev)
        assert r.request_who1013 and r.who13_shared and r.conflict is None and r.corrected_from is None, ev
        assert r.model == (ev.manual or ev.technical or ev.prior_label), ev
    # answered: no further request, whatever the answer
    assert resolve(Evidence(who13_code="200", who1013_code="51")).request_who1013 is False
    assert resolve(Evidence(who13_code="200", who1013_code="999")).request_who1013 is False


def test_resolver_labels_an_untrusted_model_from_in_band_evidence():
    assert resolve(Evidence(who13_code="6")).model == "F452"
    assert resolve(Evidence(prior_label="F452", who13_code="4")).model == "MH200"  # our own label: relabel freely
    assert resolve(Evidence(who13_code="51")).model == "F454"  # observed-only code still labels
    r = resolve(Evidence(who13_code="200", who1013_code="67"))
    assert (r.model, r.source, r.corrected_from) == ("MyHomeServer1", IDENTIFICATION_WHO13, None)


def test_resolver_manual_choice():
    # compatible, or questioned by field evidence only: kept
    assert resolve(Evidence(manual="MH200N", who13_code="4")).model == "MH200N"
    r = resolve(Evidence(manual="MH200", who13_code="51"))
    assert (r.model, r.conflict, r.corrected_from) == ("MH200", None, None)
    # a certain contradiction corrects it and says from what
    r = resolve(Evidence(manual="F454", who13_code="6"))
    assert (r.model, r.source, r.corrected_from, r.corrected_reading.raw) == ("F452", IDENTIFICATION_WHO13, "F454", "6")
    r = resolve(Evidence(manual="F454", who13_code="200", who1013_code="67"))
    assert (r.model, r.corrected_from, r.corrected_reading.raw) == ("MyHomeServer1", "F454", "1013-1-67")
    # confirmed by WHO=1013 with no table change needed for the model itself
    r = resolve(Evidence(manual="F461", who13_code="200", who1013_code="134"))
    assert (r.model, r.conflict, r.corrected_from) == ("F461", None, None)
    # a manual catalogue SKU is corroborated
    assert resolve(Evidence(manual="003598", who13_code="200", who1013_code="51")).corrected_from is None


def test_resolver_technical_identity_is_never_overruled():
    for source in (IDENTIFICATION_SSDP, IDENTIFICATION_SERIAL):
        r = resolve(Evidence(technical="F454", technical_source=source, who13_code="4"))
        assert r.model == "F454" and r.source == source
        assert r.conflict == f"configured as F454 ({source}) but WHO=13 device type 4 identifies MH200 per the OpenWebNet specification"
        assert (r.conflict_reading.raw, r.conflict_reading.certain) == ("4", True)
        r = resolve(Evidence(technical="MH202", technical_source=source, who13_code="200", who1013_code="67"))
        assert r.model == "MH202"
        assert r.conflict == f"configured as MH202 ({source}) but WHO=1013 OBJECT_MODEL 67 identifies MyHomeServer1 per diagnostic catalogue"
        # field evidence only: unverified, no conflict
        assert resolve(Evidence(technical="MH200", technical_source=source, who13_code="51")).conflict is None
        # corroborated
        assert resolve(Evidence(technical="MH202", technical_source=source, who13_code="200", who1013_code="5")).conflict is None
        assert resolve(Evidence(technical="003598", technical_source=source, who13_code="200", who1013_code="51")).conflict is None


def test_resolver_who1013_outranks_who13():
    """The catalogue is one code per model and the two families disagree for the same SKU."""
    r = resolve(Evidence(technical="F454", technical_source=IDENTIFICATION_SSDP, who13_code="4", who1013_code="51"))
    assert r.conflict is None
    r = resolve(Evidence(manual="MH200", who13_code="4", who1013_code="51"))
    assert (r.model, r.corrected_from) == ("F454", "MH200")
    # an unknown WHO=1013 code does not outrank a known WHO=13 one
    r = resolve(Evidence(who13_code="4", who1013_code="999"))
    assert (r.model, r.unknown_code) == ("MH200", "1013-1-999")


def test_resolver_unknown_codes():
    r = resolve(Evidence(manual="MH200", who13_code="999"))
    assert (r.model, r.conflict, r.unknown_code) == ("MH200", None, "999")
    r = resolve(Evidence(who13_code="200", who1013_code="999"))
    assert (r.model, r.unknown_code, r.request_who1013) == (None, "1013-1-999", False)
    r = resolve(Evidence(who13_code="998", who1013_code="999"))
    assert [u.raw for u in r.unknown_readings] == ["998", "1013-1-999"]
    assert r.unknown_code == "1013-1-999"


def test_resolver_is_idempotent():
    ev = Evidence(technical="MH202", technical_source=IDENTIFICATION_SSDP, who13_code="200", who1013_code="67")
    assert resolve(ev) == resolve(ev)


def test_official_table_matches_ownd_decoder():
    for code, model in OFFICIAL_2006_TABLE.items():
        decoded = OWNEvent.parse(f"*#13**15*{code}##")
        assert getattr(decoded, "device_type", getattr(decoded, "_device_type", None)) == model


@pytest.mark.parametrize(
    ("model", "family"),
    [("MH200", "MH200"), ("MH200N", "MH200"), ("F452V", "F452"), ("F454", "F454"), ("MyHomeServer1", "MYHOMESERVER1"), ("", ""), (None, "")],
)
def test_model_family(model, family):
    assert gateway_model_family(model) == family


# ── identification source ────────────────────────────────────────────────


def test_identification_source_precedence():
    assert _handler({"ssdp_location": "http://192.0.2.40:49153/desc.xml"}).identification_source == IDENTIFICATION_SSDP
    assert _handler({"UDN": "uuid:1234"}).identification_source == IDENTIFICATION_SSDP
    assert _handler({"transport_type": "serial", "name": "Legrand 3578 USB Gateway"}).identification_source == IDENTIFICATION_SERIAL
    assert _handler().identification_source == IDENTIFICATION_MANUAL
    assert _handler({"name": "Generic"}).identification_source == IDENTIFICATION_UNKNOWN
    assert _handler({"name": "MH200", "model_source": "who13"}).identification_source == IDENTIFICATION_WHO13
    assert _handler({"name": "MH200N", "model_source": "manual"}).identification_source == IDENTIFICATION_MANUAL


# ── a manually configured MH200 that reports type 4 (the live case) ─────


def test_manual_mh200_reporting_type_4_is_left_alone(dev_reg, issues):
    create, delete, corrected = issues
    h = _handler()
    _who13(h, "4")
    assert h.gateway.model_name == "MH200"
    assert h._who13["code"] == "4" and h._who13["model"] == "MH200"
    assert h._identity_conflict is None
    create.assert_not_called()
    corrected.assert_not_called()
    h.hass.config_entries.async_update_entry.assert_not_called()
    dev_reg.async_update_device.assert_not_called()
    ident = h.identification()
    assert ident["model"] == "MH200" and ident["source"] == IDENTIFICATION_MANUAL and ident["who13_code"] == "4"
    assert ident["who13_model_official"] == "MH200" and ident["who13_model_observed"] is None


def test_variant_suffix_is_not_a_conflict(dev_reg, issues):
    """An MH200N owner whose unit reports the 2006 code 4 (MH200) is consistent, not mislabelled."""
    create, _, corrected = issues
    h = _handler({"name": "MH200N"})
    h.gateway.model_name = "MH200N"
    dev_reg.async_get.return_value = MagicMock(model="MH200N")
    _who13(h, "4")
    assert h.gateway.model_name == "MH200N"
    assert h._identity_conflict is None
    create.assert_not_called()
    corrected.assert_not_called()


# ── SSDP-announced model is never overruled, but a contradiction is flagged ──


def test_ssdp_model_never_relabelled_and_conflict_raises_repair(dev_reg, issues):
    create, delete, corrected = issues
    h = _handler({"name": "F454", "ssdp_location": "http://192.0.2.40:49153/desc.xml"})
    h.gateway.model_name = "F454"
    dev_reg.async_get.return_value = MagicMock(model="F454")

    _who13(h, "4")  # device says MH200 - contradiction with the announcement
    assert h.gateway.model_name == "F454"
    assert "configured as F454 (ssdp)" in h._identity_conflict
    create.assert_called_once()
    args = create.call_args.args
    assert args[1:] == ("entry_ident", "F454", "MH200", "4", "ssdp", True)
    corrected.assert_not_called()
    h.hass.config_entries.async_update_entry.assert_not_called()

    # same reply again: no duplicate issue
    _who13(h, "4")
    create.assert_called_once()

    # code 200 is compatible with F454 per field evidence (#370): conflict cleared, issue deleted
    create.reset_mock()
    _who13(h, "200")
    assert h._identity_conflict is None
    delete.assert_called_once_with(h.hass, "entry_ident")
    assert h.gateway.model_name == "F454"
    create.assert_not_called()
    ident = h.identification()
    assert ident["who13_code"] == "200"
    assert ident["who13_model_official"] is None
    assert ident["who13_model_observed"] == "F454 / MyHomeServer1 / MH202 / F461"
    assert ident["conflict"] is None
    # ...and, the code being shared, WHO=1013 is asked to cross-check the announcement
    assert str(h.send_buffer.get_nowait()["message"]) == "*#1013*0*1##"

    # a code outside both tables: conflict cleared, issue deleted, model kept
    delete.reset_mock()
    _who13(h, "999")
    assert h._identity_conflict is None
    delete.assert_called_once_with(h.hass, "entry_ident")
    assert h.gateway.model_name == "F454"


def test_f454_and_mhs1_with_code_200_have_no_conflict(dev_reg, issues):
    """Both F454 (#370) and MyHomeServer1 (#292/#297) report code 200: no conflict for either."""
    create, delete, corrected = issues
    for model in ("F454", "MyHomeServer1"):
        create.reset_mock()
        delete.reset_mock()
        h = _handler({"name": model}, title=f"{model} Gateway")
        h.gateway.model_name = model
        dev_reg.async_get.return_value = MagicMock(model=model)
        _who13(h, "200")
        assert h.gateway.model_name == model
        assert h._identity_conflict is None
        create.assert_not_called()
        corrected.assert_not_called()
        ident = h.identification()
        assert ident["who13_code"] == "200"
        assert ident["who13_model_observed"] == "F454 / MyHomeServer1 / MH202 / F461"
        assert ident["conflict"] is None


def test_manual_model_contradicted_by_official_code_is_corrected(dev_reg, issues):
    """The manual flow used to default to F454; an official code proves otherwise and is applied."""
    create, delete, corrected = issues
    h = _handler({"name": "F454"}, title="F454 Gateway")
    h.gateway.model_name = "F454"
    dev_reg.async_get.return_value = MagicMock(model="F454")

    _who13(h, "6")  # F452 per the 2006 table: certain
    assert h.gateway.model_name == "F452"
    kwargs = h.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"]["name"] == "F452" and kwargs["data"]["model_source"] == IDENTIFICATION_WHO13
    assert kwargs["title"] == "F452 Gateway"
    corrected.assert_called_once_with(h.hass, "entry_ident", "F454", "F452", "6")
    create.assert_not_called()
    dev_reg.async_update_device.assert_called_once_with("dev_gw", model="F452")


def test_manual_model_with_unverified_observed_code_keeps_model_without_conflict(dev_reg, issues):
    """An observed code whose compatibility is unverified (e.g. manual MH200, reports 200) keeps the model without conflict."""
    create, delete, corrected = issues
    h = _handler({"name": "MH200"}, title="MH200 Gateway")
    h.gateway.model_name = "MH200"
    dev_reg.async_get.return_value = MagicMock(model="MH200")

    _who13(h, "200")
    assert h.gateway.model_name == "MH200"  # not overruled by field evidence
    h.hass.config_entries.async_update_entry.assert_not_called()
    corrected.assert_not_called()
    create.assert_not_called()
    assert h._identity_conflict is None
    ident = h.identification()
    assert ident["who13_model_official"] is None and ident["who13_model_observed"] == "F454 / MyHomeServer1 / MH202 / F461"
    assert ident["conflict"] is None
    assert ident["who1013_code"] is None and ident["who1013_model"] is None
    # the shared code is the cue to ask WHO=1013, whatever the source
    queued = h.send_buffer.get_nowait()
    assert str(queued["message"]) == "*#1013*0*1##" and queued["is_status_request"] is True


def test_manual_model_confirmed_by_who1013_is_kept(dev_reg, issues):
    """Manual F461, WHO=13 says 200, WHO=1013 says 134 (F461): nothing to fix, nothing to add to any table."""
    create, delete, corrected = issues
    h = _handler({"name": "F461"}, title="F461 Gateway")
    h.gateway.model_name = "F461"
    dev_reg.async_get.return_value = MagicMock(model="F461")
    _who13(h, "200")
    _who1013(h, "134")
    assert h.gateway.model_name == "F461"
    h.hass.config_entries.async_update_entry.assert_not_called()
    corrected.assert_not_called()
    create.assert_not_called()
    ident = h.identification()
    assert ident["who1013_code"] == "134" and ident["who1013_model"] == "F461"
    assert ident["conflict"] is None
    # answered: a repeat of the shared code does not ask again
    _who13(h, "200")
    assert h.send_buffer.qsize() == 1


def test_manual_model_contradicted_by_who1013_is_corrected(dev_reg, issues):
    """Manual F454 (the old flow default), WHO=13 says 200, WHO=1013 says 67: it is a MyHomeServer1 (#292/#297)."""
    create, delete, corrected = issues
    h = _handler({"name": "F454"}, title="F454 Gateway")
    h.gateway.model_name = "F454"
    dev_reg.async_get.return_value = MagicMock(model="F454")
    _who13(h, "200")
    assert h.gateway.model_name == "F454"
    _who1013(h, "67")
    assert h.gateway.model_name == "MyHomeServer1"
    kwargs = h.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"]["name"] == "MyHomeServer1" and kwargs["data"]["model_source"] == IDENTIFICATION_WHO13
    assert kwargs["title"] == "MyHomeServer1 Gateway"
    corrected.assert_called_once_with(h.hass, "entry_ident", "F454", "MyHomeServer1", "1013-1-67")
    create.assert_not_called()
    dev_reg.async_update_device.assert_called_once_with("dev_gw", model="MyHomeServer1")
    assert h.identification()["who1013_model"] == "MyHomeServer1"


def test_ssdp_model_with_unverified_observed_code_keeps_model_without_conflict(dev_reg, issues):
    """An observed code whose compatibility is unverified on an SSDP gateway keeps the model without conflict."""
    create, delete, corrected = issues
    h = _handler({"name": "MH202", "ssdp_location": "http://192.168.1.40:49153/desc.xml"})
    h.gateway.model_name = "MH202"
    dev_reg.async_get.return_value = MagicMock(model="MH202")

    _who13(h, "200")
    assert h.gateway.model_name == "MH202"
    assert h._identity_conflict is None
    create.assert_not_called()
    corrected.assert_not_called()
    ident = h.identification()
    assert ident["who13_model_observed"] == "F454 / MyHomeServer1 / MH202 / F461"
    assert ident["conflict"] is None
    assert str(h.send_buffer.get_nowait()["message"]) == "*#1013*0*1##"


def test_ssdp_model_cross_checked_by_who1013(dev_reg, issues):
    """SSDP MH202 answering 200: WHO=1013 confirms (5) or contradicts (67); the announcement is never overruled.

    The contradiction survives the periodic re-broadcast of the shared code that
    triggered the check, and is cleared only by a WHO=1013 reply that agrees.
    """
    create, delete, corrected = issues
    h = _handler({"name": "MH202", "ssdp_location": "http://192.0.2.40:49153/desc.xml"})
    h.gateway.model_name = "MH202"
    dev_reg.async_get.return_value = MagicMock(model="MH202")

    _who13(h, "200")
    _who1013(h, "5")  # MH202: agrees
    assert h._identity_conflict is None
    create.assert_not_called()
    assert h.gateway.model_name == "MH202"

    _who1013(h, "67")  # MyHomeServer1: the device announced MH202 - keep it, ask the owner
    assert h.gateway.model_name == "MH202"
    assert h._identity_conflict == (
        "configured as MH202 (ssdp) but WHO=1013 OBJECT_MODEL 67 identifies MyHomeServer1 per diagnostic catalogue"
    )
    create.assert_called_once()
    assert create.call_args.args[1:] == ("entry_ident", "MH202", "MyHomeServer1", "1013-1-67", "ssdp", True)
    corrected.assert_not_called()
    h.hass.config_entries.async_update_entry.assert_not_called()

    # the gateway broadcasts 200 again: no new request (answered), conflict untouched, no flapping issue
    delete.reset_mock()
    while not h.send_buffer.empty():
        h.send_buffer.get_nowait()
    _who13(h, "200")
    assert h.send_buffer.empty()
    assert h._identity_conflict is not None
    delete.assert_not_called()
    create.assert_called_once()

    # an agreeing WHO=1013 reply clears it
    _who1013(h, "5")
    assert h._identity_conflict is None
    delete.assert_called_once_with(h.hass, "entry_ident")

    # WHO=1013 outranks WHO=13: an official code arriving later does not reopen the question
    _who13(h, "4")
    assert h._identity_conflict is None


def test_serial_model_cross_checked_by_who1013(dev_reg, issues):
    """A serial-fixed identity is treated like SSDP: cross-checked, never relabelled."""
    create, delete, corrected = issues
    h = _handler({"transport_type": "serial", "name": "MH200"})
    h.gateway.model_name = "MH200"
    dev_reg.async_get.return_value = MagicMock(model="MH200")
    _who13(h, "200")  # no serial gateway is known to answer this; the path must still be sound
    assert str(h.send_buffer.get_nowait()["message"]) == "*#1013*0*1##"
    _who1013(h, "44")  # MH200N: same family
    assert h._identity_conflict is None
    _who1013(h, "51")  # F454
    assert h.gateway.model_name == "MH200"
    assert "configured as MH200 (serial)" in h._identity_conflict
    assert create.call_args.args[1:] == ("entry_ident", "MH200", "F454", "1013-1-51", "serial", True)
    corrected.assert_not_called()


def test_unknown_code_on_configured_gateway_is_recorded_not_applied(dev_reg, issues):
    create, _, corrected = issues
    h = _handler()
    _who13(h, "999")
    assert h.gateway.model_name == "MH200"
    assert h._who13["code"] == "999" and h._who13["model"] is None
    create.assert_not_called()
    corrected.assert_not_called()


def test_mislabelled_registry_is_repaired_from_the_configured_model(dev_reg, issues):
    """A device registry entry written as MH200N by an earlier release is corrected to the configured model."""
    dev_reg.async_get.return_value = MagicMock(model="MH200N")
    h = _handler()
    _who13(h, "4")
    dev_reg.async_update_device.assert_called_once_with("dev_gw", model="MH200")


# ── no model configured: WHO=13 may label, official codes first ──────────


def test_unknown_entry_is_labelled_from_official_code(dev_reg, issues):
    h = _handler({"name": "Generic"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"
    dev_reg.async_get.return_value = MagicMock(model="Generic")
    _who13(h, "6")
    assert h.gateway.model_name == "F452"
    kwargs = h.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"]["name"] == "F452"
    assert kwargs["data"]["model_source"] == IDENTIFICATION_WHO13
    assert kwargs["title"] == "F452 Gateway"
    dev_reg.async_update_device.assert_called_once_with("dev_gw", model="F452")


def test_unknown_entry_with_ambiguous_code_stays_generic(dev_reg, issues):
    """Code 200 is ambiguous between F454 and MyHomeServer1: cannot auto-label an unknown gateway."""
    _, _, corrected = issues
    h = _handler({"name": "Generic"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"
    dev_reg.async_get.return_value = MagicMock(model="Generic")
    _who13(h, "200")
    assert h.gateway.model_name == "Generic"
    h.hass.config_entries.async_update_entry.assert_not_called()
    dev_reg.async_update_device.assert_not_called()
    corrected.assert_not_called()
    assert h._identity_conflict is None
    # Verify the diagnostic request is queued to disambiguate the gateway.
    queued = h.send_buffer.get_nowait()
    assert str(queued["message"]) == "*#1013*0*1##"
    assert queued["is_status_request"] is True
    # unanswered: the request is pending, a re-broadcast does not repeat it
    _who13(h, "200")
    assert h.send_buffer.empty()
    # ...until the event session reconnects
    h._on_event_connection_state_change(True)
    _who13(h, "200")
    assert h.send_buffer.qsize() == 1
    h.send_buffer.get_nowait()
    # answered: labelled from the catalogue, and no further request
    _who1013(h, "51")
    assert h.gateway.model_name == "F454"
    kwargs = h.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"]["name"] == "F454" and kwargs["data"]["model_source"] == IDENTIFICATION_WHO13
    assert kwargs["title"] == "F454 Gateway"
    corrected.assert_not_called()  # nothing was corrected: there was no model
    _who13(h, "200")
    assert h.send_buffer.empty()

def test_mh200_unambiguous_who13_skips_who1013(dev_reg, issues):
    """Anonymous golden sample: a physical MH200 correctly returning WHO=13 DIM=15 value 4
    is correctly labelled as an MH200, and does not incorrectly trigger the WHO=1013 diagnostic frame
    (validating @anotherjulien's approach).
    """
    _, _, corrected = issues
    h = _handler({"name": "Generic"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"
    dev_reg.async_get.return_value = MagicMock(model="Generic")
    _who13(h, "4")
    assert h.gateway.model_name == "MH200"

    # Verify we did NOT query WHO=1013 DIM=1.
    assert h.send_buffer.empty()



def test_unknown_entry_with_unknown_code_stays_generic(dev_reg, issues):
    h = _handler({"name": "Generic"})
    h.gateway.model_name = "Generic"
    _who13(h, "999")
    assert h.gateway.model_name == "Generic"
    h.hass.config_entries.async_update_entry.assert_not_called()


def test_who13_label_is_not_repeated_when_already_applied(dev_reg, issues):
    h = _handler({"name": "F452", "model_source": "who13"})
    h.gateway.model_name = "F452"
    dev_reg.async_get.return_value = MagicMock(model="F452")
    _who13(h, "6")
    h.hass.config_entries.async_update_entry.assert_not_called()
    dev_reg.async_update_device.assert_not_called()


def test_manual_selection_outranks_an_earlier_who13_label(dev_reg, issues):
    """PR #345 review: an entry labelled MH200 by WHO=13, then switched to MH200N in the
    options flow, must not be flipped back by the next device-type 4 reply."""
    create, delete, corrected = issues
    # Before the options flow: the entry was labelled from WHO=13 and would be relabelled.
    h = _handler({"name": "MH200N", "model_source": "who13"})
    h.gateway.model_name = "MH200N"
    _who13(h, "4")
    assert h.gateway.model_name == "MH200"  # the bug the review reproduced
    # After the options flow: the selection is recorded as manual and stays intact.
    h = _handler({"name": "MH200N", "model_source": "manual"})
    h.gateway.model_name = "MH200N"
    dev_reg.async_get.return_value = MagicMock(model="MH200N")
    _who13(h, "4")
    assert h.gateway.model_name == "MH200N"
    assert h.config_entry.data["name"] == "MH200N"
    assert h._identity_conflict is None
    h.hass.config_entries.async_update_entry.assert_not_called()
    create.assert_not_called()
    corrected.assert_not_called()


def test_stale_identity_issue_is_cleared_by_a_fresh_handler(dev_reg, issues):
    """PR #345 review: a reload creates a handler with no conflict in memory, but the
    previous instance's warning is still in the issue registry; a matching reply must remove it."""
    create, delete, corrected = issues
    first = _handler({"name": "MH200", "ssdp_location": "http://192.168.1.40:49153/desc.xml"})
    first.gateway.model_name = "MH200"
    dev_reg.async_get.return_value = MagicMock(model="MH200")
    _who13(first, "6")  # official F452 code contradicts announced MH200: issue created
    assert first._identity_conflict is not None
    create.assert_called_once()
    delete.assert_not_called()

    second = _handler({"name": "MH200", "ssdp_location": "http://192.168.1.40:49153/desc.xml"})
    second.gateway.model_name = "MH200"
    dev_reg.async_get.return_value = MagicMock(model="MH200")
    assert second._identity_conflict is None
    _who13(second, "4")  # MH200 per the 2006 table: matches the configured model
    assert second._identity_conflict is None
    delete.assert_called_once_with(second.hass, "entry_ident")


# ── corroborating dimensions ─────────────────────────────────────────────


def test_firmware_kernel_distribution_are_recorded(dev_reg):
    h = _handler()
    h._handle_gateway_diagnostics(OWNEvent.parse("*#13**16*2*60*46##"))
    h._handle_gateway_diagnostics(OWNEvent.parse("*#13**23*2*6*32##"))
    h._handle_gateway_diagnostics(OWNEvent.parse("*#13**24*1*0*5##"))
    ident = h.identification()
    assert ident["who13_firmware"] == "2.60.46"
    assert ident["who13_kernel"] == "2.6.32"
    assert ident["who13_distribution"] == "1.0.5"
    assert ident["profile"] == "MH200NProfile"


# ── the evidence travels with diagnostics and the WebSocket / trace payload ──


def test_websocket_gateway_info_carries_identification_without_location():
    from custom_components.myhome.websocket import _extract_gateway_info

    h = _handler({"ssdp_location": "http://192.0.2.40:49153/desc.xml"})
    h._who13["code"] = "4"
    h._who1013["code"] = "44"
    h._who1013["model"] = "MH200N"
    info = _extract_gateway_info(h, "2.0.0b6")
    assert info["identification"]["source"] == IDENTIFICATION_SSDP
    assert info["identification"]["who13_code"] == "4"
    assert info["identification"]["who1013_code"] == "44"
    assert info["identification"]["who1013_model"] == "MH200N"
    assert "ssdp_location" not in info["identification"]


def test_websocket_gateway_info_tolerates_gateway_without_identification():
    from custom_components.myhome.websocket import _extract_gateway_info

    gw = MagicMock(spec=[])  # no identification attribute at all
    assert _extract_gateway_info(gw)["identification"] == {}


def test_apply_model_does_not_rewrite_an_entry_that_already_carries_it(dev_reg):
    h = _handler()
    h.config_entry.data["name"] = "F452"
    h._apply_model("F452")
    assert h.gateway.model_name == "F452" and h.profile is not None
    h.hass.config_entries.async_update_entry.assert_not_called()


def test_conflict_tracking_without_entry_id_and_registry_sync_without_device(dev_reg):
    """Defensive paths: no config entry id (no issue registry access) and no device registry id."""
    h = _handler()
    h.config_entry.entry_id = None
    with patch("custom_components.myhome.gateway.async_create_identity_issue") as create:
        h._set_conflict("some conflict", None)
        assert h._identity_conflict == "some conflict"
        create.assert_not_called()
    h.device_registry_id = None
    h._sync_device_registry_model("MH200")
    dev_reg.async_update_device.assert_not_called()


def _who1013(h, code):
    h._handle_gateway_identity_diagnostics(OWNEvent.parse(f"*#1013**1*{code}##"))

def test_who1013_unknown_code_is_reported_like_an_unknown_who13_code(dev_reg, issues):
    """A code outside the catalogue keeps the model and raises the same unknown-model repair as WHO=13 does."""
    h = _handler({"name": "Generic"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"
    with patch("custom_components.myhome.gateway.async_create_unknown_model_issue") as unknown, \
         patch("custom_components.myhome.gateway.async_delete_unknown_model_issue") as known:
        _who1013(h, "999")
        assert h.gateway.model_name == "Generic"
        unknown.assert_called_once_with(h.hass, "entry_ident", "1013-1-999")
        known.assert_not_called()
        ident = h.identification()
        assert ident["who1013_code"] == "999" and ident["who1013_model"] is None
        # the shared WHO=13 code that keeps being broadcast neither re-asks nor withdraws the request
        _who13(h, "200")
        assert h.send_buffer.empty()
        known.assert_not_called()
        unknown.assert_called_with(h.hass, "entry_ident", "1013-1-999")
        # a recognised reply afterwards clears the request for a trace
        _who1013(h, "5")
        known.assert_called_once_with(h.hass, "entry_ident")
        assert h.gateway.model_name == "MH202"

def test_who1013_updates_manual_model(dev_reg, issues):
    h = _handler({"name": "Generic", "model_source": "manual"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"
    _who1013(h, "5") # 5 is MH202
    assert h.gateway.model_name == "MH202"
    h.hass.config_entries.async_update_entry.assert_called_once()
    kwargs = h.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"]["name"] == "MH202"
    assert kwargs["title"] == "MH202 Gateway"
    dev_reg.async_update_device.assert_called_once_with("dev_gw", model="MH202")

def test_who1013_ssdp_conflict(dev_reg, issues):
    h = _handler({"name": "F454", "ssdp_location": "http://192.0.2.40:49153/desc.xml"}, title="F454 Gateway")
    h.gateway.model_name = "F454"
    _who1013(h, "4") # 4 is MH200
    assert h.gateway.model_name == "F454" # Does not update
    assert "identifies MH200 per diagnostic catalogue" in h._identity_conflict

def test_who1013_ssdp_compatible(dev_reg, issues):
    h = _handler({"name": "MH200", "ssdp_location": "http://192.0.2.40:49153/desc.xml"}, title="MH200 Gateway")
    h.gateway.model_name = "MH200"
    _who1013(h, "4") # 4 is MH200 (same family)
    assert h.gateway.model_name == "MH200"
    assert h._identity_conflict is None

async def test_who1013_is_dispatched(dev_reg, issues):
    """Cover the async _process_message dispatch for WHO=1013 DIM=1."""
    h = _handler({"name": "Generic"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"
    # Valid dimension 1
    await h._process_message(OWNEvent.parse("*#1013**1*5##"))
    assert h.gateway.model_name == "MH202"
    # Unhandled dimension
    await h._process_message(OWNEvent.parse("*#1013**2*5##"))
    # Unsupported who fallback (covered elsewhere typically, but good to ensure no crash)
    await h._process_message(OWNEvent.parse("*#9999**1*5##"))

def test_who13_ambiguous_handles_queue_full(dev_reg, issues):
    """Cover the QueueFull exception when dispatching the WHO=1013 diagnostic."""
    import asyncio
    h = _handler({"name": "Generic"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"

    # Fill the queue (maxsize is 0 by default, let us replace it with maxsize 1 and fill it)
    h.send_buffer = asyncio.Queue(maxsize=1)
    h.send_buffer.put_nowait({"message": "filler"})

    # This will attempt to queue *#1013*0*1## but fail with QueueFull
    _who13(h, "200")
    assert h._who1013["pending"] is False  # nothing left the handler: the next broadcast retries
    # and the parse guard: a request that cannot be built is skipped, not queued
    h.send_buffer = asyncio.Queue()
    with patch("custom_components.myhome.gateway.OWNCommand.parse", return_value=None):
        h._request_object_model()
    assert h.send_buffer.empty() and h._who1013["pending"] is False
    h.send_buffer = asyncio.Queue(maxsize=1)
    h.send_buffer.put_nowait({"message": "filler"})

    # It should still remain Generic and not crash
    assert h.gateway.model_name == "Generic"
    assert h.send_buffer.qsize() == 1

def test_who1013_invalid_dimension_value(dev_reg, issues):
    """Cover the early return when dimension value is missing."""
    h = _handler({"name": "Generic"}, title="Generic Gateway")
    h.gateway.model_name = "Generic"

    # Create an OWNEvent with no dimension values
    msg = OWNEvent.parse("*#1013**1##")
    h._handle_gateway_identity_diagnostics(msg)

    # Should safely return without changes
    assert h.gateway.model_name == "Generic"
