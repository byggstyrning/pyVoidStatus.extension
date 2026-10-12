# -*- coding: utf-8 -*-
"""Parse and write the project Void Status XML. No Revit imports."""

from xml.etree import ElementTree as ET

try:
    unicode
except NameError:
    unicode = str

from void_status.contract import (
    STATUS_PARAMETERS,
    DEFAULT_DISCIPLINES,
    DEFAULT_CATEGORIES,
    DEFAULT_VALUE_SEPARATOR,
    DEFAULT_XML,
    PARAM_BY_KEY,
    DISCIPLINE_CODES,
    LEGACY_DISCIPLINE_MARKERS,
    canonical_discipline_code,
)
from void_status.logutil import log_debug, log_info, log_warning

# Project settings are a short document. Reject larger imports before parsing.
MAX_IMPORT_XML_CHARS = 262144


def _as_unicode(value):
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    try:
        return value.decode("utf-8", "replace")
    except Exception:
        return unicode(value)


class VoidStatusConfig(object):
    """In-memory project settings."""

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
        existing = [item.lower() for item in self.discipline_codes()]
        if code.lower() in existing:
            return
        self.disciplines.append({"code": code, "label": label or ""})


def _reject_xml_declarations(xml_text):
    """Refuse DTD and entity declarations before ElementTree sees the text."""
    lowered = _as_unicode(xml_text).lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("XML entity declarations are not allowed.")


def _child_text(node):
    return (node.text or "").strip()


def _read_disciplines(root):
    rows = []
    for node in root.findall("./Disciplines/Discipline"):
        code = (node.get("code") or "").strip()
        label = _child_text(node)
        if not code:
            code = label
            label = ""
        if code:
            rows.append({"code": code, "label": label})
    return rows


def _read_categories(root):
    names = []
    for node in root.findall("./Categories/Category"):
        text = _child_text(node)
        if text:
            names.append(text)
    return names


def _read_parameters(root, config):
    count = 0
    for node in root.findall("./Parameters/Parameter"):
        key = (node.get("key") or "").strip()
        guid = (node.get("guid") or "").strip()
        name = (node.get("name") or "").strip()
        if key and guid and name:
            config.parameters[key] = {"guid": guid, "name": name}
            count += 1
    return count


def _default_disciplines():
    return [{"code": code, "label": label} for code, label in DEFAULT_DISCIPLINES]


def _label_for(code, current_label, raw):
    if current_label and current_label != raw:
        return current_label
    return dict(DEFAULT_DISCIPLINES).get(code, "")


def _migrate_legacy_disciplines(config):
    """Replace the first-version full-name list, or canonicalize each code."""
    codes = config.discipline_codes()
    if not codes:
        log_info("XML had no disciplines; applying default discipline list")
        config.disciplines = _default_disciplines()
        return

    markers = set(LEGACY_DISCIPLINE_MARKERS)
    has_legacy_name = any(code in markers for code in codes)
    has_known_code = any(
        code in DISCIPLINE_CODES and code not in ("HVAC",) for code in codes
    )
    if has_legacy_name and not has_known_code:
        log_info(
            "Replacing legacy full-name discipline list {} with default codes".format(
                codes
            )
        )
        config.disciplines = _default_disciplines()
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
        migrated.append({"code": code, "label": _label_for(code, label, raw)})
    if migrated:
        config.disciplines = migrated


def parse_config_xml(xml_text):
    """Parse XML text into a VoidStatusConfig. Raises ValueError on bad XML."""
    if not xml_text or not _as_unicode(xml_text).strip():
        xml_text = DEFAULT_XML

    _reject_xml_declarations(xml_text)
    text = _as_unicode(xml_text)
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except Exception:
        try:
            root = ET.fromstring(text)
        except Exception as ex:
            log_warning("Invalid XML: {}".format(ex))
            raise ValueError("Invalid XML: {}".format(ex))

    config = VoidStatusConfig()
    disciplines = _read_disciplines(root)
    if disciplines:
        config.disciplines = disciplines
    categories = _read_categories(root)
    if categories:
        config.categories = categories

    separator = root.find("./Options/ValueSeparator")
    if separator is not None and separator.text is not None:
        config.value_separator = separator.text

    param_count = _read_parameters(root, config)
    before_codes = list(config.discipline_codes())
    _migrate_legacy_disciplines(config)
    after_codes = list(config.discipline_codes())
    if before_codes != after_codes:
        log_info("Migrated disciplines {} -> {}".format(before_codes, after_codes))
    log_debug(
        "Parsed XML: disciplines={} categories={} separator={!r} parameters={}".format(
            after_codes, config.categories, config.value_separator, param_count
        )
    )
    return config


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
    for category in config.categories:
        node = ET.SubElement(cats_el, "Category")
        node.text = category

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
    """Re-indent XML. Raises ValueError if parsing fails."""
    return build_config_xml(parse_config_xml(xml_text))


def validate_xml(xml_text):
    """Return (ok, error_message)."""
    try:
        parse_config_xml(xml_text)
        return True, None
    except ValueError as ex:
        return False, str(ex)


def assert_import_xml(xml_text):
    """Reject oversized or non-settings XML before it is parsed.

    Raises ValueError. Returns the text with a leading BOM removed.
    """
    if xml_text is None:
        raise ValueError("The file is empty.")
    if not isinstance(xml_text, unicode):
        try:
            if isinstance(xml_text, str):
                xml_text = xml_text.decode("utf-8")
            else:
                xml_text = unicode(xml_text)
        except Exception:
            raise ValueError("The file is not text.")
    if xml_text.startswith(u"\ufeff"):
        xml_text = xml_text.lstrip(u"\ufeff")
    if len(xml_text) > MAX_IMPORT_XML_CHARS:
        raise ValueError(
            "The file is too large ({} characters, limit {}).".format(
                len(xml_text), MAX_IMPORT_XML_CHARS
            )
        )
    stripped = xml_text.strip()
    if not stripped.startswith("<"):
        raise ValueError("The file is not XML.")
    _reject_xml_declarations(stripped)
    head = stripped[:8000].lower()
    if "<voidstatus" not in head:
        raise ValueError("The file is not a Void Status settings file.")
    return xml_text
