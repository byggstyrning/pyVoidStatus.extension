# -*- coding: utf-8 -*-
"""Shared-parameter GUIDs and default project XML."""

SCHEMA_VERSION = "1.0"

# Coordination parameters used for void approval. GUIDs must stay identical
# so existing models that already have these parameters keep working.
STATUS_PARAMETERS = (
    {
        "key": "drawn_by",
        "guid": "9651d3dd-e420-4a10-8de6-565fc0315f47",
        "name": "Drawn by",
        "user_modifiable": True,
        "description": "Displays the name of the Drawer.",
    },
    {
        "key": "drawn_date",
        "guid": "240a0677-044f-4bb8-9410-486103fbe13b",
        "name": "Drawn Date",
        "user_modifiable": False,
        "description": "Displays the creation or update date of the element.",
    },
    {
        "key": "drawn_status",
        "guid": "8e164356-e013-4548-b21b-5128466c692c",
        "name": "Drawn Status",
        "user_modifiable": False,
        "description": "Drawing status: Created, Changed or Up to Date.",
    },
    {
        "key": "approved_by",
        "guid": "719a943d-f1a3-4a18-9684-0f813b9d6e5a",
        "name": "Approved by",
        "user_modifiable": False,
        "description": "Disciplines that have approved the element.",
    },
    {
        "key": "rejected_by",
        "guid": "b01b41a7-973e-48fd-8816-163f7a33a7a7",
        "name": "Rejected by",
        "user_modifiable": False,
        "description": "Disciplines that have rejected the element.",
    },
    {
        "key": "pending_by",
        "guid": "962ca537-282e-42a1-b77c-c959957efb99",
        "name": "Pending by",
        "user_modifiable": False,
        "description": "Disciplines that have placed the element on hold.",
    },
    {
        "key": "assigned_to",
        "guid": "1035d1b3-baff-4446-94c5-312404c3d845",
        "name": "Assigned to",
        "user_modifiable": False,
        "description": "User or team responsible for reviewing the element.",
    },
    {
        "key": "chat_log",
        "guid": "09b9ba26-7e8f-4a91-8ce2-80f22244f2b5",
        "name": "Chat Log",
        "user_modifiable": True,
        "description": "Saves the chat into a readable format.",
    },
)

PARAM_BY_KEY = dict((item["key"], item) for item in STATUS_PARAMETERS)

# Identity parameters used to pair openings across linked models.
# MatchKey is the IfcGuid of the reference element (the duct/pipe/opening
# the void was created or adopted from).
MATCH_KEY = {
    "guid": "2e9bc4c8-bf25-4700-b8ee-14294918ffa6",
    "name": "MatchKey",
}
OBJECT_ID = {
    "guid": "b0b57893-462a-4872-93d9-741a29c5e4fc",
    "name": "ObjectId",
}

# Profile value list. The *code* is what gets written into
# Approved by / Pending by / Rejected by. Combined entries (with &) are a
# single list value, not two disciplines glued together.
DEFAULT_DISCIPLINES = (
    ("ARC", "Architectural"),
    ("STR", "Structural"),
    ("HVAC", "HVAC"),
    ("ELEC", "Electrical"),
    ("PLBG", "Plumbing"),
    ("COORD", "Coordination"),
    ("FP", "Fire Protection"),
    ("TP", "Telecommunications"),
    ("MEP", "MEP"),
    ("HVAC & PLBG", "HVAC and Plumbing"),
    ("HVAC & ELEC", "HVAC and Electrical"),
    ("PLGB & ELEC", "Plumbing and Electrical"),
)

# Full names from the first Config default → value-list codes.
LEGACY_DISCIPLINE_MAP = {
    "Architecture": "ARC",
    "Architectural": "ARC",
    "Structure": "STR",
    "Structural": "STR",
    "Electrical": "ELEC",
    "Plumbing": "PLBG",
    "Fire Protection": "FP",
    "Sprinkler": "FP",
    "Coordination": "COORD",
    "Telecommunications": "TP",
    "Tele": "TP",
}

DISCIPLINE_CODES = tuple(code for code, _label in DEFAULT_DISCIPLINES)


def canonical_discipline_code(value):
    """Return the discipline code for a stored profile/XML discipline string."""
    text = (value or "").strip()
    if not text:
        return ""
    for code in DISCIPLINE_CODES:
        if text.lower() == code.lower():
            return code
    lower_map = dict((key.lower(), mapped) for key, mapped in LEGACY_DISCIPLINE_MAP.items())
    return lower_map.get(text.lower(), text)

DEFAULT_CATEGORIES = (
    "OST_GenericModel",
    "OST_Windows",
    "OST_Doors",
    "OST_ShaftOpening",
    "OST_Opening",
    "OST_SWallRectOpening",
)

CATEGORY_CHOICES = (
    ("OST_GenericModel", "Generic Models"),
    ("OST_Windows", "Windows"),
    ("OST_Doors", "Doors"),
    ("OST_ShaftOpening", "Shaft Openings"),
    ("OST_Opening", "Openings"),
    ("OST_SWallRectOpening", "Rectangular wall openings"),
)

DEFAULT_VALUE_SEPARATOR = ", "

DEFAULT_XML = """<?xml version="1.0" encoding="utf-8"?>
<VoidStatus version="1.0">
  <Disciplines>
    <Discipline code="ARC">Architectural</Discipline>
    <Discipline code="STR">Structural</Discipline>
    <Discipline code="HVAC">HVAC</Discipline>
    <Discipline code="ELEC">Electrical</Discipline>
    <Discipline code="PLBG">Plumbing</Discipline>
    <Discipline code="COORD">Coordination</Discipline>
    <Discipline code="FP">Fire Protection</Discipline>
    <Discipline code="TP">Telecommunications</Discipline>
    <Discipline code="MEP">MEP</Discipline>
    <Discipline code="HVAC &amp; PLBG">HVAC and Plumbing</Discipline>
    <Discipline code="HVAC &amp; ELEC">HVAC and Electrical</Discipline>
    <Discipline code="PLGB &amp; ELEC">Plumbing and Electrical</Discipline>
  </Disciplines>
  <Parameters>
    <Parameter key="drawn_by" guid="9651d3dd-e420-4a10-8de6-565fc0315f47" name="Drawn by" />
    <Parameter key="drawn_date" guid="240a0677-044f-4bb8-9410-486103fbe13b" name="Drawn Date" />
    <Parameter key="drawn_status" guid="8e164356-e013-4548-b21b-5128466c692c" name="Drawn Status" />
    <Parameter key="approved_by" guid="719a943d-f1a3-4a18-9684-0f813b9d6e5a" name="Approved by" />
    <Parameter key="rejected_by" guid="b01b41a7-973e-48fd-8816-163f7a33a7a7" name="Rejected by" />
    <Parameter key="pending_by" guid="962ca537-282e-42a1-b77c-c959957efb99" name="Pending by" />
    <Parameter key="assigned_to" guid="1035d1b3-baff-4446-94c5-312404c3d845" name="Assigned to" />
    <Parameter key="chat_log" guid="09b9ba26-7e8f-4a91-8ce2-80f22244f2b5" name="Chat Log" />
  </Parameters>
  <Categories>
    <Category>OST_GenericModel</Category>
    <Category>OST_Windows</Category>
    <Category>OST_Doors</Category>
    <Category>OST_ShaftOpening</Category>
    <Category>OST_Opening</Category>
    <Category>OST_SWallRectOpening</Category>
  </Categories>
  <Options>
    <ValueSeparator>, </ValueSeparator>
  </Options>
</VoidStatus>
"""
