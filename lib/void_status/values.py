# -*- coding: utf-8 -*-
"""Multi-discipline value lists and opening match indexes. No Revit imports.

Approved by / Pending by / Rejected by store discipline codes separated by
comma or semicolon. ``HVAC & PLBG`` is one token: ampersand is not a separator.
"""

from void_status.contract import DEFAULT_VALUE_SEPARATOR

STATUS_FIELDS = ("approved", "rejected", "pending")


def _separator(separator):
    if separator is None:
        return DEFAULT_VALUE_SEPARATOR
    return separator


def split_values(raw, separator):
    """Split a stored multi-value string into trimmed, unique tokens."""
    if not raw:
        return []
    normalized = raw.replace(";", ",")
    configured = _separator(separator)
    stripped = configured.strip() if configured else ""
    if stripped and stripped not in (",", ";"):
        normalized = normalized.replace(configured, ",")
    parts = []
    seen = set()
    for token in normalized.split(","):
        item = token.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(item)
    return parts


def join_values(values, separator):
    """Join tokens with the project separator, keeping the first occurrence."""
    cleaned = []
    seen = set()
    for item in values:
        text = (item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return _separator(separator).join(cleaned)


def add_value(raw, value, separator):
    """Append *value* when it is missing. Other disciplines stay."""
    values = split_values(raw, separator)
    needle = (value or "").strip()
    if needle and needle.lower() not in [item.lower() for item in values]:
        values.append(needle)
    return join_values(values, separator)


def remove_value(raw, value, separator):
    """Remove one exact code. Other disciplines stay."""
    needle = (value or "").strip().lower()
    kept = [
        item for item in split_values(raw, separator) if item.lower() != needle
    ]
    return join_values(kept, separator)


def edit_status_fields(fields, add_key, remove_keys, code, separator):
    """Add *code* to one status parameter and remove only that code from the others.

    *fields* is keyed by parameter key (``approved_by``, ``pending_by``,
    ``rejected_by``).
    """
    updated = {}
    for key in fields:
        updated[key] = fields.get(key) or ""
    updated[add_key] = add_value(fields.get(add_key) or "", code, separator)
    for key in remove_keys:
        source = updated.get(key, fields.get(key) or "")
        updated[key] = remove_value(source, code, separator)
    return updated


def code_in_fields(fields, code, separator):
    """True when *code* appears in any status bucket."""
    needle = (code or "").strip().lower()
    if not needle:
        return False
    for field in STATUS_FIELDS:
        tokens = [
            token.lower()
            for token in split_values(fields.get(field) or "", separator)
        ]
        if needle in tokens:
            return True
    return False


def apply_synced_code(host_fields, link_fields, code, separator):
    """Move *code* on the host into the same bucket as the linked opening.

    Other host disciplines stay. Returns ``(new_fields, changed)``.
    When *code* is absent from the link, the host fields are unchanged.
    """
    needle = (code or "").strip()
    if not needle:
        return dict(host_fields), False

    target = None
    lowered = needle.lower()
    for field in STATUS_FIELDS:
        tokens = [
            token.lower()
            for token in split_values(link_fields.get(field) or "", separator)
        ]
        if lowered in tokens:
            target = field
            break
    if target is None:
        return dict(host_fields), False

    new_fields = {}
    for field in STATUS_FIELDS:
        raw = host_fields.get(field) or ""
        if field == target:
            new_fields[field] = add_value(raw, needle, separator)
        else:
            new_fields[field] = remove_value(raw, needle, separator)

    changed = False
    for field in STATUS_FIELDS:
        before = [token.lower() for token in split_values(host_fields.get(field) or "", separator)]
        after = [token.lower() for token in split_values(new_fields[field], separator)]
        if before != after:
            changed = True
            break
    return new_fields, changed


def identity_values_from_keys(keys):
    """MatchKey / ObjectId / IfcGUID values. UniqueId is file-local and skipped."""
    values = []
    seen = set()
    for kind, value in keys or []:
        if kind == "uniqueid" or not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def index_match_keys(entries):
    """Index ``[(item, keys), ...]``.

    Ambiguous values are dropped. Keys are ``("id", value)`` or
    ``("uniqueid", value)``. Returns ``(index, ambiguous_count)``.
    """
    buckets = {}
    for item, keys in entries:
        for value in identity_values_from_keys(keys):
            buckets.setdefault(("id", value), []).append(item)
        for kind, value in keys or []:
            if kind == "uniqueid" and value:
                buckets.setdefault(("uniqueid", value), []).append(item)

    index = {}
    ambiguous = 0
    for key, items in buckets.items():
        if len(items) == 1:
            index[key] = items[0]
        else:
            ambiguous += 1
    return index, ambiguous


def match_against_index(keys, index):
    """Return ``(item, method)`` or ``(None, None)``.

    Identity values are tried before UniqueId.
    """
    for value in identity_values_from_keys(keys):
        item = index.get(("id", value))
        if item is not None:
            return item, "identity"
    unique_id = None
    for kind, value in keys or []:
        if kind == "uniqueid":
            unique_id = value
            break
    if unique_id:
        item = index.get(("uniqueid", unique_id))
        if item is not None:
            return item, "uniqueid"
    return None, None
