# -*- coding: utf-8 -*-
"""Unit tests for Void Status XML and multi-value helpers (no Revit)."""

import os
import sys

LIB = os.path.join(os.path.dirname(__file__), "..", "lib")
sys.path.insert(0, os.path.abspath(LIB))

from void_status.config import (
    parse_config_xml,
    pretty_xml,
    validate_xml,
    assert_import_xml,
    MAX_IMPORT_XML_CHARS,
)
from void_status.contract import DEFAULT_XML
from void_status.values import (
    add_value,
    remove_value,
    split_values,
    apply_synced_code,
    identity_values_from_keys,
    index_match_keys,
    match_against_index,
)


def test_default_xml_uses_discipline_codes():
    config = parse_config_xml(DEFAULT_XML)
    codes = config.discipline_codes()
    assert "STR" in codes
    assert "ARC" in codes
    assert "ELEC" in codes
    assert "HVAC & PLBG" in codes
    assert "Architecture" not in codes
    assert config.parameter("approved_by")["guid"] == "719a943d-f1a3-4a18-9684-0f813b9d6e5a"
    assert config.parameter("approved_by")["name"] == "Approved by"


def test_xml_roundtrip_keeps_guid_and_combined_code():
    pretty = pretty_xml(DEFAULT_XML)
    again = parse_config_xml(pretty)
    assert again.parameter("pending_by")["guid"] == "962ca537-282e-42a1-b77c-c959957efb99"
    assert "HVAC & ELEC" in again.discipline_codes()


def test_invalid_xml():
    ok, err = validate_xml("<not-closed>")
    assert ok is False
    assert err


def test_multi_approve_keeps_other_disciplines():
    sep = ", "
    raw = add_value("STR", "ELEC", sep)
    assert split_values(raw, sep) == ["STR", "ELEC"]
    raw = add_value(raw, "STR", sep)
    assert split_values(raw, sep) == ["STR", "ELEC"]
    raw = remove_value(raw, "ELEC", sep)
    assert split_values(raw, sep) == ["STR"]


def test_legacy_full_names_migrate_to_discipline_codes():
    old_xml = """<?xml version="1.0" encoding="utf-8"?>
<VoidStatus version="1.0">
  <Disciplines>
    <Discipline>Architecture</Discipline>
    <Discipline>Structure</Discipline>
    <Discipline>HVAC</Discipline>
    <Discipline>Electrical</Discipline>
    <Discipline>Plumbing</Discipline>
    <Discipline>Fire Protection</Discipline>
    <Discipline>Sprinkler</Discipline>
    <Discipline>Coordination</Discipline>
  </Disciplines>
  <Parameters>
    <Parameter key="approved_by" guid="719a943d-f1a3-4a18-9684-0f813b9d6e5a" name="Approved by" />
  </Parameters>
</VoidStatus>
"""
    config = parse_config_xml(old_xml)
    codes = config.discipline_codes()
    assert codes == [
        "ARC",
        "STR",
        "HVAC",
        "ELEC",
        "PLBG",
        "COORD",
        "FP",
        "TP",
        "MEP",
        "HVAC & PLBG",
        "HVAC & ELEC",
        "PLGB & ELEC",
    ]
    pretty = pretty_xml(old_xml)
    assert "Architecture" not in pretty
    assert "HVAC &amp; PLBG" in pretty or "HVAC & PLBG" in pretty


def test_canonical_discipline_code():
    from void_status.contract import canonical_discipline_code
    assert canonical_discipline_code("Structure") == "STR"
    assert canonical_discipline_code("STR") == "STR"
    assert canonical_discipline_code("HVAC & PLBG") == "HVAC & PLBG"


def test_combined_discipline_code_is_one_token():
    sep = ", "
    raw = "STR, HVAC & PLBG, ELEC"
    assert split_values(raw, sep) == ["STR", "HVAC & PLBG", "ELEC"]
    raw = remove_value(raw, "STR", sep)
    assert split_values(raw, sep) == ["HVAC & PLBG", "ELEC"]
    raw = add_value(raw, "ARC", sep)
    assert split_values(raw, sep) == ["HVAC & PLBG", "ELEC", "ARC"]
    raw = remove_value("HVAC & PLBG, ELEC", "ELEC", sep)
    assert split_values(raw, sep) == ["HVAC & PLBG"]


def test_sync_merges_linked_code_without_dropping_host():
    sep = ", "
    host = {"approved": "STR", "rejected": "", "pending": ""}
    link = {"approved": "ARC", "rejected": "", "pending": ""}
    new_fields, changed = apply_synced_code(host, link, "ARC", sep)
    assert changed is True
    assert split_values(new_fields["approved"], sep) == ["STR", "ARC"]
    assert new_fields["rejected"] == ""
    assert new_fields["pending"] == ""


def test_sync_moves_code_when_linked_rejected():
    sep = ", "
    host = {"approved": "STR, ARC", "rejected": "", "pending": ""}
    link = {"approved": "", "rejected": "ARC", "pending": ""}
    new_fields, changed = apply_synced_code(host, link, "ARC", sep)
    assert changed is True
    assert split_values(new_fields["approved"], sep) == ["STR"]
    assert split_values(new_fields["rejected"], sep) == ["ARC"]


def test_match_guids_match_bundled_shared_params():
    from void_status.contract import MATCH_KEY, OBJECT_ID, PARAM_BY_KEY

    assert MATCH_KEY["guid"] == "2e9bc4c8-bf25-4700-b8ee-14294918ffa6"
    assert MATCH_KEY["name"] == "MatchKey"
    assert OBJECT_ID["guid"] == "b0b57893-462a-4872-93d9-741a29c5e4fc"
    assert OBJECT_ID["name"] == "ObjectId"
    assert PARAM_BY_KEY["chat_log"]["guid"] == "09b9ba26-7e8f-4a91-8ce2-80f22244f2b5"
    assert PARAM_BY_KEY["chat_log"]["name"] == "Chat Log"


def test_identity_values_cross_match_adopted_opening():
    """Host MatchKey can equal a linked opening's IfcGUID after adopt."""
    link_keys = [
        ("matchkey", "0lfklokoj3buyhdkfx6blf"),
        ("objectid", "3e0953a8-2b47-4322-bef7-bf74f6838af1"),
        ("ifcguid", "0_2leeaqt38hxtltjswuhn"),
        ("uniqueid", "3e0953a8-2b47-4322-bef7-bf74f6e8c073-006b4a82"),
    ]
    host_keys = [
        ("matchkey", "0_2leeaqt38hxtltjswuhn"),
        ("objectid", "039fa647-276c-4838-8cc1-f4e8f8c6e7fc"),
        ("ifcguid", "03dwp79sn8e8p1zezunkvy"),
    ]
    overlap = set(identity_values_from_keys(link_keys)) & set(
        identity_values_from_keys(host_keys)
    )
    assert overlap == set(["0_2leeaqt38hxtltjswuhn"])
    assert "3e0953a8-2b47-4322-bef7-bf74f6e8c073-006b4a82" not in identity_values_from_keys(
        link_keys
    )


def test_host_index_unique_identity_match():
    host = "host-a"
    index, ambiguous = index_match_keys([
        (host, [("matchkey", "abc"), ("uniqueid", "u1")]),
    ])
    assert ambiguous == 0
    item, method = match_against_index(
        [("ifcguid", "abc"), ("uniqueid", "other")],
        index,
    )
    assert item == host
    assert method == "identity"


def test_host_index_drops_ambiguous_key():
    index, ambiguous = index_match_keys([
        ("a", [("matchkey", "same")]),
        ("b", [("objectid", "same")]),
    ])
    assert ambiguous == 1
    item, method = match_against_index([("ifcguid", "same")], index)
    assert item is None
    assert method is None


def test_host_index_uniqueid_is_fallback_only():
    index, ambiguous = index_match_keys([
        ("host", [("matchkey", "host-key"), ("uniqueid", "shared-uid")]),
    ])
    assert ambiguous == 0
    item, method = match_against_index(
        [("matchkey", "other"), ("uniqueid", "shared-uid")],
        index,
    )
    assert item == "host"
    assert method == "uniqueid"

    index, _ambiguous = index_match_keys([
        ("by-id", [("matchkey", "wanted")]),
        ("by-uid", [("uniqueid", "uid-1")]),
    ])
    item, method = match_against_index(
        [("ifcguid", "wanted"), ("uniqueid", "uid-1")],
        index,
    )
    assert item == "by-id"
    assert method == "identity"


def test_storage_and_profile_contract():
    from void_status.contract import (
        PROJECT_SCHEMA_GUID,
        USER_SCHEMA_GUID,
        FIELD_SCHEMA_VERSION,
        FIELD_CONFIG_XML,
        FIELD_DISCIPLINE_BY_USER,
        SCHEMA_VERSION,
        PROFILE_SECTION,
        PROFILE_NAME_KEY,
        PROFILE_DISCIPLINE_KEY,
    )

    assert PROJECT_SCHEMA_GUID == "c8e4f2a1-7b39-4d6e-9a5c-1f8d2e4b6a70"
    assert USER_SCHEMA_GUID == "c8e4f2a1-7b39-4d6e-9a5c-1f8d2e4b6a71"
    assert FIELD_SCHEMA_VERSION == "schema_version"
    assert FIELD_CONFIG_XML == "config_xml"
    assert FIELD_DISCIPLINE_BY_USER == "discipline_by_user"
    assert SCHEMA_VERSION == "1.0"
    assert PROFILE_SECTION == "VoidStatus"
    assert PROFILE_NAME_KEY == "profile_name"
    assert PROFILE_DISCIPLINE_KEY == "profile_discipline"


def test_shared_parameter_contract():
    from void_status.contract import STATUS_PARAMETERS, DEFAULT_CATEGORIES, DEFAULT_VALUE_SEPARATOR

    expected = {
        "drawn_by": ("9651d3dd-e420-4a10-8de6-565fc0315f47", "Drawn by"),
        "drawn_date": ("240a0677-044f-4bb8-9410-486103fbe13b", "Drawn Date"),
        "drawn_status": ("8e164356-e013-4548-b21b-5128466c692c", "Drawn Status"),
        "approved_by": ("719a943d-f1a3-4a18-9684-0f813b9d6e5a", "Approved by"),
        "rejected_by": ("b01b41a7-973e-48fd-8816-163f7a33a7a7", "Rejected by"),
        "pending_by": ("962ca537-282e-42a1-b77c-c959957efb99", "Pending by"),
        "assigned_to": ("1035d1b3-baff-4446-94c5-312404c3d845", "Assigned to"),
        "chat_log": ("09b9ba26-7e8f-4a91-8ce2-80f22244f2b5", "Chat Log"),
    }
    actual = dict((item["key"], (item["guid"], item["name"])) for item in STATUS_PARAMETERS)
    assert actual == expected
    assert list(DEFAULT_CATEGORIES) == [
        "OST_GenericModel",
        "OST_Windows",
        "OST_Doors",
        "OST_ShaftOpening",
        "OST_Opening",
        "OST_SWallRectOpening",
        "OST_MechanicalEquipment",
    ]
    from void_status.contract import categories_for_ensure
    assert categories_for_ensure(["OST_Doors"]) == [
        "OST_Doors",
        "OST_MechanicalEquipment",
    ]
    assert categories_for_ensure(["OST_MechanicalEquipment", "OST_Doors"]) == [
        "OST_MechanicalEquipment",
        "OST_Doors",
    ]
    assert DEFAULT_VALUE_SEPARATOR == ", "


def test_action_rules_move_only_the_current_code():
    from void_status.contract import ACTIONS, RESET_TARGETS
    from void_status.values import edit_status_fields, split_values

    assert ACTIONS["approve"]["add_key"] == "approved_by"
    assert ACTIONS["approve"]["remove_keys"] == ("pending_by", "rejected_by")
    assert ACTIONS["pending"]["add_key"] == "pending_by"
    assert ACTIONS["pending"]["remove_keys"] == ("approved_by", "rejected_by")
    assert ACTIONS["reject"]["add_key"] == "rejected_by"
    assert ACTIONS["reject"]["remove_keys"] == ("approved_by", "pending_by")
    assert RESET_TARGETS["all"] == ("approved_by", "rejected_by", "pending_by")
    assert RESET_TARGETS["approved"] == ("approved_by",)
    assert RESET_TARGETS["rejected"] == ("rejected_by",)
    assert RESET_TARGETS["pending"] == ("pending_by",)

    sep = ", "
    fields = {
        "approved_by": "STR",
        "pending_by": "ARC",
        "rejected_by": "ARC, ELEC",
    }
    spec = ACTIONS["approve"]
    updated = edit_status_fields(
        fields, spec["add_key"], spec["remove_keys"], "ARC", sep
    )
    assert split_values(updated["approved_by"], sep) == ["STR", "ARC"]
    assert split_values(updated["pending_by"], sep) == []
    assert split_values(updated["rejected_by"], sep) == ["ELEC"]


def test_default_xml_shape():
    config = parse_config_xml(DEFAULT_XML)
    assert config.value_separator == ", "
    assert config.categories[0] == "OST_GenericModel"
    assert config.parameter("drawn_by")["name"] == "Drawn by"
    built = pretty_xml(DEFAULT_XML)
    assert built.startswith("<?xml")
    assert 'version="1.0"' in built
    assert "<VoidStatus" in built
    assert "<ValueSeparator>" in built


def test_import_xml_rejects_oversized_and_foreign_files():
    try:
        assert_import_xml("x" * (MAX_IMPORT_XML_CHARS + 1))
        raised = False
    except ValueError:
        raised = True
    assert raised is True

    try:
        assert_import_xml("<NotVoidStatus />")
        raised = False
    except ValueError:
        raised = True
    assert raised is True

    accepted = assert_import_xml(
        '<?xml version="1.0" encoding="utf-8"?><VoidStatus version="1.0"></VoidStatus>'
    )
    assert "<VoidStatus" in accepted

    try:
        assert_import_xml(
            '<!DOCTYPE VoidStatus [<!ENTITY x "boom">]><VoidStatus>&x;</VoidStatus>'
        )
        raised = False
    except ValueError:
        raised = True
    assert raised is True
