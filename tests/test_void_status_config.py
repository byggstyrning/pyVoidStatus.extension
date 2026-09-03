# -*- coding: utf-8 -*-
"""Unit tests for Void Status XML and multi-value helpers (no Revit)."""

import os
import sys

LIB = os.path.join(os.path.dirname(__file__), "..", "lib")
sys.path.insert(0, os.path.abspath(LIB))

from void_status.config_xml import parse_config_xml, pretty_xml, validate_xml
from void_status.constants import DEFAULT_XML
from void_status.values import (
    add_value,
    remove_value,
    split_values,
    apply_synced_code,
    identity_values_from_keys,
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
    from void_status.constants import canonical_discipline_code
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
    from void_status.constants import MATCH_KEY, OBJECT_ID

    assert MATCH_KEY["guid"] == "2e9bc4c8-bf25-4700-b8ee-14294918ffa6"
    assert MATCH_KEY["name"] == "MatchKey"
    assert OBJECT_ID["guid"] == "b0b57893-462a-4872-93d9-741a29c5e4fc"
    assert OBJECT_ID["name"] == "ObjectId"


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
