# -*- coding: utf-8 -*-
"""Split and join multi-discipline parameter values.

Approved by / Pending by / Rejected by are *value lists*.
Each token is a discipline code (ARC, STR, ELEC, ...). Combined profile
values such as ``HVAC & PLBG`` are a single token — ``&`` is not a separator.

Other disciplines already on the element are always preserved. We only add
or remove the current profile code.
"""

from void_status.constants import DEFAULT_VALUE_SEPARATOR


def split_values(raw, separator):
    """Split a stored multi-value string into trimmed tokens.

    List delimiters are comma and semicolon. Ampersand is kept inside a token
    so ``HVAC & PLBG`` stays one value.
    """
    if not raw:
        return []
    # Normalize only list delimiters; do not touch '&'.
    normalized = raw.replace(";", ",")
    configured = separator if separator is not None else DEFAULT_VALUE_SEPARATOR
    if configured and configured.strip() and configured.strip() not in (",", ";"):
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
    """Join tokens using the project separator, keeping original order."""
    sep = separator if separator is not None else DEFAULT_VALUE_SEPARATOR
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
    return sep.join(cleaned)


def add_value(raw, value, separator):
    """Append *value* if missing. Existing tokens from other disciplines stay."""
    values = split_values(raw, separator)
    needle = (value or "").strip()
    if not needle:
        return join_values(values, separator)
    if needle.lower() not in [v.lower() for v in values]:
        values.append(needle)
    return join_values(values, separator)


def remove_value(raw, value, separator):
    """Remove only an exact code match. Other disciplines stay."""
    values = split_values(raw, separator)
    needle = (value or "").strip().lower()
    kept = [v for v in values if v.lower() != needle]
    return join_values(kept, separator)


STATUS_FIELDS = ("approved", "rejected", "pending")


def code_in_fields(fields, code, separator):
    """True if *code* appears in any status field."""
    needle = (code or "").strip().lower()
    if not needle:
        return False
    for field in STATUS_FIELDS:
        tokens = [t.lower() for t in split_values(fields.get(field) or "", separator)]
        if needle in tokens:
            return True
    return False


def apply_synced_code(host_fields, link_fields, code, separator):
    """Move *code* on the host into the same status bucket as the linked opening.

    Other host disciplines are left untouched. Returns ``(new_fields, changed)``.
    If *code* is not present on the linked opening, host fields are unchanged.
    """
    needle = (code or "").strip()
    if not needle:
        return dict(host_fields), False

    target = None
    for field in STATUS_FIELDS:
        tokens = [t.lower() for t in split_values(link_fields.get(field) or "", separator)]
        if needle.lower() in tokens:
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
        before = split_values(host_fields.get(field) or "", separator)
        after = split_values(new_fields[field], separator)
        if [t.lower() for t in before] != [t.lower() for t in after]:
            changed = True
            break
    return new_fields, changed


def identity_values_from_keys(keys):
    """Identity strings that pair openings across models.

    **MatchKey** is the IfcGuid of the reference element. A host opening
    adopted from a linked opening therefore stores that opening's IFC GUID
    as MatchKey. Compare MatchKey / ObjectId / IfcGUID *values*
    regardless of which field they came from. UniqueId is file-local.
    """
    values = []
    seen = set()
    for kind, value in keys or []:
        if kind == "uniqueid" or not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values
