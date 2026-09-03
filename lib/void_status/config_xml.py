# -*- coding: utf-8 -*-
"""Parse and build the project-level Void Status XML."""

from xml.etree import ElementTree as ET

try:
    unicode
except NameError:
    unicode = str

from void_status.constants import (
    STATUS_PARAMETERS,
    DEFAULT_DISCIPLINES,
    DEFAULT_CATEGORIES,
    DEFAULT_VALUE_SEPARATOR,
    DEFAULT_XML,
    PARAM_BY_KEY,
    DISCIPLINE_CODES,
    canonical_discipline_code,
)
from void_status.logutil import log_debug, log_info, log_warning


class VoidStatusConfig(object):
    """In-memory view of the project XML."""

    def __init__(self):
        self.disciplines = [
            {"code": code, "label": label} for code, label in DEFAULT_DISCIPLINES
        ]
        self.categories = list(DEFAULT_CATEGORIES)
        self.value_separator = DEFAULT_VALUE_SEPARATOR
        self.parameters = dict(
            (item["key"], {"guid": item["guid"], "name": item["name"]})
            for item in STATUS_PARAMETERS
        )

    def parameter(self, key):
        """Return ``{guid, name}`` for a logical parameter key."""
        mapped = self.parameters.get(key)
        if mapped:
            return mapped
        fallback = PARAM_BY_KEY.get(key)
        if fallback:
            return {"guid": fallback["guid"], "name": fallback["name"]}
        return None

    def discipline_codes(self):
        """Codes written into Approved by / Pending by / Rejected by."""
        codes = []
        for item in self.disciplines:
            if isinstance(item, dict):
                code = (item.get("code") or "").strip()
            else:
                code = (item or "").strip()
            if code:
                codes.append(code)
        return codes

    def add_discipline(self, code, label=""):
        code = (code or "").strip()
        if not code:
            return
        existing = [c.lower() for c in self.discipline_codes()]
        if code.lower() in existing:
            return
        self.disciplines.append({"code": code, "label": label or ""})


def parse_config_xml(xml_text):
    """Parse XML text into a VoidStatusConfig. Raises ValueError on bad XML."""
    if not xml_text or not xml_text.strip():
        xml_text = DEFAULT_XML

    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, unicode) else xml_text)
    except Exception:
        try:
            root = ET.fromstring(xml_text)
        except Exception as ex:
            log_warning("Invalid XML: {}".format(ex))
            raise ValueError("Invalid XML: {}".format(ex))

    config = VoidStatusConfig()

    disciplines = []
    for node in root.findall("./Disciplines/Discipline"):
        code = (node.get("code") or "").strip()
        label = (node.text or "").strip()
        if not code:
            code = label
            label = ""
        if code:
            disciplines.append({"code": code, "label": label})
    if disciplines:
        config.disciplines = disciplines

    categories = []
    for node in root.findall("./Categories/Category"):
        text = (node.text or "").strip()
        if text:
            categories.append(text)
    if categories:
        config.categories = categories

    sep_node = root.find("./Options/ValueSeparator")
    if sep_node is not None and sep_node.text is not None:
        config.value_separator = sep_node.text

    param_count = 0
    for node in root.findall("./Parameters/Parameter"):
        key = (node.get("key") or "").strip()
        guid = (node.get("guid") or "").strip()
        name = (node.get("name") or "").strip()
        if key and guid and name:
            config.parameters[key] = {"guid": guid, "name": name}
            param_count += 1

    before_codes = list(config.discipline_codes())
    _migrate_legacy_disciplines(config)
    after_codes = list(config.discipline_codes())
    if before_codes != after_codes:
        log_info(
            "Migrated disciplines {} -> {}".format(before_codes, after_codes)
        )
    log_debug(
        "Parsed XML: disciplines={} categories={} separator={!r} parameters={}".format(
            after_codes,
            config.categories,
            config.value_separator,
            param_count,
        )
    )
    return config


def _legacy_markers():
    return set(
        [
            "Architecture",
            "Architectural",
            "Structure",
            "Structural",
            "Electrical",
            "Plumbing",
            "Fire Protection",
            "Sprinkler",
            "Coordination",
        ]
    )


def _migrate_legacy_disciplines(config):
    """Replace the first-version full-name list with discipline codes + combos."""
    codes = config.discipline_codes()
    if not codes:
        log_info("XML had no disciplines; applying default discipline list")
        config.disciplines = [
            {"code": code, "label": label} for code, label in DEFAULT_DISCIPLINES
        ]
        return

    markers = _legacy_markers()
    has_legacy_name = any(code in markers for code in codes)
    has_known_code = any(
        code in DISCIPLINE_CODES and code not in ("HVAC",)
        for code in codes
    )
    if has_legacy_name and not has_known_code:
        log_info(
            "Replacing legacy full-name discipline list {} with default codes".format(
                codes
            )
        )
        config.disciplines = [
            {"code": code, "label": label} for code, label in DEFAULT_DISCIPLINES
        ]
        return

    migrated = []
    seen = set()
    for item in config.disciplines:
        if isinstance(item, dict):
            raw = item.get("code") or ""
            label = item.get("label") or ""
        else:
            raw = item or ""
            label = ""
        code = canonical_discipline_code(raw)
        if not code:
            continue
        key = code.lower()
        if key in seen:
            continue
        seen.add(key)
        if not label or label == raw:
            label = dict(DEFAULT_DISCIPLINES).get(code, "")
        migrated.append({"code": code, "label": label})
    if migrated:
        config.disciplines = migrated


def _indent_element(elem, level=0):
    """In-place pretty indent for ElementTree (IronPython-safe)."""
    indent = "\n" + ("  " * level)
    child_indent = "\n" + ("  " * (level + 1))
    children = list(elem)
    if children:
        if not elem.text or not elem.text.strip():
            elem.text = child_indent
        for child in children:
            _indent_element(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = indent
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = indent


def build_config_xml(config):
    """Serialize a VoidStatusConfig to pretty-printed XML text."""
    root = ET.Element("VoidStatus")
    root.set("version", "1.0")

    disciplines_el = ET.SubElement(root, "Disciplines")
    for item in config.disciplines:
        if isinstance(item, dict):
            code = (item.get("code") or "").strip()
            label = (item.get("label") or "").strip()
        else:
            code = (item or "").strip()
            label = ""
        if not code:
            continue
        node = ET.SubElement(disciplines_el, "Discipline")
        node.set("code", code)
        if label and label != code:
            node.text = label

    params_el = ET.SubElement(root, "Parameters")
    for item in STATUS_PARAMETERS:
        mapped = config.parameters.get(item["key"], item)
        node = ET.SubElement(params_el, "Parameter")
        node.set("key", item["key"])
        node.set("guid", mapped.get("guid", item["guid"]))
        node.set("name", mapped.get("name", item["name"]))

    cats_el = ET.SubElement(root, "Categories")
    for cat in config.categories:
        node = ET.SubElement(cats_el, "Category")
        node.text = cat

    options_el = ET.SubElement(root, "Options")
    sep_node = ET.SubElement(options_el, "ValueSeparator")
    sep_node.text = config.value_separator

    _indent_element(root)
    xml_body = ET.tostring(root, encoding="utf-8")
    if not isinstance(xml_body, str):
        xml_body = xml_body.decode("utf-8")
    if xml_body.startswith("<?xml"):
        return xml_body
    return '<?xml version="1.0" encoding="utf-8"?>\n' + xml_body


def pretty_xml(xml_text):
    """Re-indent XML; raises ValueError if parsing fails."""
    config = parse_config_xml(xml_text)
    return build_config_xml(config)


def validate_xml(xml_text):
    """Return (ok, error_message)."""
    try:
        parse_config_xml(xml_text)
        return True, None
    except ValueError as ex:
        return False, str(ex)
