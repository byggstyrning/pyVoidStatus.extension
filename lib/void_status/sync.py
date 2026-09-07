# -*- coding: utf-8 -*-
"""Synchronize approval statuses from a linked model into host openings.

Pick a linked Revit/IFC model, choose which discipline codes to import, and
merge those codes into matching host openings. Other disciplines already on
the host stay in place. Only Approved by / Rejected by / Pending by are written.
"""

from Autodesk.Revit.DB import (
    BuiltInParameter,
    FilteredElementCollector,
    RevitLinkInstance,
)

from void_status.constants import (
    canonical_discipline_code,
    MATCH_KEY,
    OBJECT_ID,
)
from void_status.parameters import get_parameter, get_string_value, set_string_value
from void_status.values import (
    STATUS_FIELDS,
    apply_synced_code,
    code_in_fields,
    split_values,
    identity_values_from_keys,
)
from void_status.logutil import (
    log_debug,
    log_info,
    log_warning,
    element_label,
)


def list_loaded_links(doc):
    """Return unique loaded Revit/IFC links: ``[{name, document, instance}, ...]``."""
    links = []
    seen_docs = set()
    for inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = inst.GetLinkDocument()
        if link_doc is None:
            continue
        doc_id = link_doc.Title
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        links.append(
            {
                "name": link_doc.Title or inst.Name,
                "document": link_doc,
                "instance": inst,
            }
        )
    links.sort(key=lambda item: item["name"].lower())
    log_info(
        "Loaded links: {} ({})".format(
            len(links),
            ", ".join([item["name"] for item in links]) or "none",
        )
    )
    return links


def link_info_for_type(doc, link_type_id):
    """Return the loaded link dict for a ``RevitLinkType`` id, or None."""
    if doc is None or link_type_id is None:
        return None
    for inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            if inst.GetTypeId() != link_type_id:
                continue
        except Exception:
            continue
        link_doc = inst.GetLinkDocument()
        if link_doc is None:
            continue
        return {
            "name": link_doc.Title or inst.Name,
            "document": link_doc,
            "instance": inst,
        }
    return None


def iter_status_elements(doc, config):
    """Yield elements that have the Approved by parameter."""
    approved = config.parameter("approved_by")
    if not approved:
        log_warning("iter_status_elements: no approved_by mapping in project XML")
        return
    count = 0
    collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    for element in collector:
        if get_parameter(element, guid=approved["guid"], name=approved["name"]):
            count += 1
            yield element
    log_debug(
        "iter_status_elements in '{}': {} openings with Approved by".format(
            getattr(doc, "Title", "?"), count
        )
    )


def read_status_fields(element, config):
    fields = {}
    for key, field in (
        ("approved_by", "approved"),
        ("rejected_by", "rejected"),
        ("pending_by", "pending"),
    ):
        mapped = config.parameter(key)
        if not mapped:
            fields[field] = ""
            continue
        fields[field] = get_string_value(
            element, guid=mapped["guid"], name=mapped["name"]
        )
    return fields


def collect_link_disciplines(link_doc, config, separator):
    """Unique status codes in the linked model, with per-field counts."""
    stats = {}
    opening_count = 0
    for element in iter_status_elements(link_doc, config):
        if not _has_opening_identity(element):
            continue
        opening_count += 1
        fields = read_status_fields(element, config)
        for field in STATUS_FIELDS:
            for token in split_values(fields.get(field) or "", separator):
                code = canonical_discipline_code(token) or token
                if not code:
                    continue
                key = code.lower()
                if key not in stats:
                    stats[key] = {
                        "code": code,
                        "approved": 0,
                        "rejected": 0,
                        "pending": 0,
                    }
                stats[key][field] += 1
    rows = list(stats.values())
    rows.sort(key=lambda row: row["code"].lower())
    log_info(
        "Link '{}': {} openings, {} unique status codes: {}".format(
            getattr(link_doc, "Title", "?"),
            opening_count,
            len(rows),
            ", ".join(
                [
                    "{} (A{} R{} P{})".format(
                        row["code"], row["approved"], row["rejected"], row["pending"]
                    )
                    for row in rows
                ]
            )
            or "none",
        )
    )
    return rows, opening_count


def _identity_text(element, mapping):
    """Read an identity parameter by GUID, then name."""
    value = get_string_value(
        element, guid=mapping["guid"], name=mapping["name"]
    )
    if value:
        return value.strip()
    return ""


def _ifc_guid(element):
    """Revit built-in IFC GUID of *this* element (not the MatchKey parameter)."""
    try:
        param = element.get_Parameter(BuiltInParameter.IFC_GUID)
        if param:
            value = param.AsString()
            if value:
                return value.strip()
    except Exception:
        pass
    return ""


def element_match_keys(element):
    """Ordered identity keys used to pair host openings with linked openings.

    Priority is identity parameters, not Revit element identity:

    1. **MatchKey** — IfcGuid of the reference element. Two independently
       generated openings from the same duct/pipe share this value, and a host
       opening adopted from a linked opening stores that opening's IFC GUID here.
    2. **ObjectId** — per-opening identity.
    3. Built-in **IFC_GUID** — useful for IFC-linked models.
    4. **UniqueId** — almost never matches across two .rvt files; kept last.

    Mark is not used: it is not an identity field and collides easily.
    """
    keys = []
    match_key = _identity_text(element, MATCH_KEY)
    if match_key:
        keys.append(("matchkey", match_key.lower()))
    object_id = _identity_text(element, OBJECT_ID)
    if object_id:
        keys.append(("objectid", object_id.lower()))
    guid = _ifc_guid(element)
    if guid:
        keys.append(("ifcguid", guid.lower()))
    try:
        unique_id = element.UniqueId
        if unique_id:
            keys.append(("uniqueid", unique_id))
    except Exception:
        pass
    return keys


def _has_opening_identity(element):
    """True when the element has MatchKey or ObjectId."""
    if _identity_text(element, MATCH_KEY):
        return True
    if _identity_text(element, OBJECT_ID):
        return True
    return False


def build_host_index(host_elements):
    """Map identity values to host elements. Ambiguous values are dropped.

    MatchKey / ObjectId / IfcGUID are indexed by *value* so a host MatchKey
    can pair with a linked opening's IfcGUID.
    """
    buckets = {}
    for element in host_elements:
        keys = element_match_keys(element)
        for value in identity_values_from_keys(keys):
            buckets.setdefault(("id", value), []).append(element)
        for kind, value in keys:
            if kind == "uniqueid":
                buckets.setdefault(("uniqueid", value), []).append(element)
    index = {}
    ambiguous_keys = 0
    for key, elements in buckets.items():
        if len(elements) == 1:
            index[key] = elements[0]
        else:
            ambiguous_keys += 1
            log_debug(
                "Ambiguous host match key {}={} on {} elements; ignored".format(
                    key[0], key[1], len(elements)
                )
            )
    log_info(
        "Host index: {} openings, {} unique keys, {} ambiguous keys dropped".format(
            len(host_elements), len(index), ambiguous_keys
        )
    )
    return index


def find_host_match(link_element, host_index):
    """Return ``(host_element, method)`` or ``(None, None)``.

    Pairing is identity only: MatchKey / ObjectId / IfcGUID values, then UniqueId.
    """
    keys = element_match_keys(link_element)
    log_debug(
        "Link {} keys: {}".format(
            element_label(link_element),
            ", ".join(["{}={}".format(k, v) for k, v in keys]) or "none",
        )
    )
    for key in identity_values_from_keys(keys):
        host = host_index.get(("id", key))
        if host is not None:
            log_debug(
                "Matched {} -> {} via identity {}".format(
                    element_label(link_element), element_label(host), key
                )
            )
            return host, "identity"
    unique_id = None
    for kind, value in keys:
        if kind == "uniqueid":
            unique_id = value
            break
    if unique_id:
        host = host_index.get(("uniqueid", unique_id))
        if host is not None:
            return host, "uniqueid"
    log_debug("No identity match for {}".format(element_label(link_element)))
    return None, None


def write_status_fields(element, config, fields):
    """Write merged status strings. Returns True if any parameter was set."""
    wrote = False
    mapping = (
        ("approved_by", "approved"),
        ("rejected_by", "rejected"),
        ("pending_by", "pending"),
    )
    for key, field in mapping:
        mapped = config.parameter(key)
        if not mapped:
            continue
        param = get_parameter(element, guid=mapped["guid"], name=mapped["name"])
        if not param:
            continue
        if set_string_value(param, fields.get(field) or ""):
            wrote = True
            log_debug(
                "Wrote {}='{}' on {}".format(
                    mapped["name"], fields.get(field) or "", element_label(element)
                )
            )
    return wrote


def synchronize_from_link(host_doc, link_info, config, selected_codes, separator):
    """Merge selected discipline codes from a linked model into host openings.

    Returns a result dict with counts.
    """
    selected = []
    seen = set()
    for code in selected_codes or []:
        canon = canonical_discipline_code(code) or (code or "").strip()
        if not canon:
            continue
        key = canon.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(canon)

    result = {
        "updated": 0,
        "unchanged": 0,
        "unmatched": 0,
        "skipped": 0,
        "selected": selected,
        "unmatched_items": [],
    }
    if not selected:
        log_warning("Sync called with no selected discipline codes")
        return result

    log_info(
        "Sync start from '{}' codes={} separator={!r}".format(
            link_info.get("name"), selected, separator
        )
    )

    link_doc = link_info["document"]
    status_elements = list(iter_status_elements(host_doc, config))
    host_elements = [el for el in status_elements if _has_opening_identity(el)]
    log_info(
        "Host openings with status params: {} (with MatchKey/ObjectId: {})".format(
            len(status_elements), len(host_elements)
        )
    )
    host_index = build_host_index(host_elements)

    link_count = 0
    for link_element in iter_status_elements(link_doc, config):
        if not _has_opening_identity(link_element):
            continue
        link_count += 1
        link_fields = read_status_fields(link_element, config)
        log_debug(
            "Link {} statuses A={!r} R={!r} P={!r}".format(
                element_label(link_element),
                link_fields.get("approved"),
                link_fields.get("rejected"),
                link_fields.get("pending"),
            )
        )
        relevant = False
        for code in selected:
            if code_in_fields(link_fields, code, separator):
                relevant = True
                break
        if not relevant:
            result["skipped"] += 1
            log_debug("Skipped {} (no selected codes)".format(element_label(link_element)))
            continue

        host_element, method = find_host_match(link_element, host_index)
        if host_element is None:
            result["unmatched"] += 1
            log_debug(
                "Unmatched linked opening {}".format(element_label(link_element))
            )
            result["unmatched_items"].append(
                {
                    "label": element_label(link_element),
                    "keys": [
                        "{}={}".format(k, v)
                        for k, v in element_match_keys(link_element)
                        if k != "uniqueid"
                    ],
                }
            )
            continue

        host_fields = read_status_fields(host_element, config)
        log_info(
            "Pair via {}: {} -> {} | host A={!r} R={!r} P={!r}".format(
                method,
                element_label(link_element),
                element_label(host_element),
                host_fields.get("approved"),
                host_fields.get("rejected"),
                host_fields.get("pending"),
            )
        )
        new_fields = dict(host_fields)
        any_change = False
        for code in selected:
            new_fields, changed = apply_synced_code(
                new_fields, link_fields, code, separator
            )
            if changed:
                any_change = True
                log_debug("Applied code {} from link onto host".format(code))

        if not any_change:
            result["unchanged"] += 1
            log_info("Already in sync: {}".format(element_label(host_element)))
            continue

        log_info(
            "Merged {} A={!r} R={!r} P={!r}".format(
                element_label(host_element),
                new_fields.get("approved"),
                new_fields.get("rejected"),
                new_fields.get("pending"),
            )
        )
        if write_status_fields(host_element, config, new_fields):
            result["updated"] += 1
        else:
            result["unchanged"] += 1
            log_warning("Failed to write statuses on {}".format(element_label(host_element)))

    log_info(
        "Sync done: link_openings={} updated={} unchanged={} unmatched={} skipped={}".format(
            link_count,
            result["updated"],
            result["unchanged"],
            result["unmatched"],
            result["skipped"],
        )
    )
    return result
