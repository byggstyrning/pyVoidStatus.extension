# -*- coding: utf-8 -*-
"""Approve / pending / reject actions on the current selection."""

from Autodesk.Revit.DB import Transaction
from pyrevit import revit, forms, script

from void_status.storage import load_config
from void_status.profile import load_profile
from void_status.values import add_value, remove_value
from void_status.parameters import get_parameter, param_as_string, set_string_value
from void_status.logutil import (
    log_debug,
    log_info,
    log_warning,
    log_error,
    log_exception,
    is_debug,
    element_id_str,
    element_label,
)

logger = script.get_logger()

ACTIONS = {
    "approve": {
        "title": "Approve",
        "add_key": "approved_by",
        "remove_keys": ("pending_by", "rejected_by"),
    },
    "pending": {
        "title": "Pending",
        "add_key": "pending_by",
        "remove_keys": ("approved_by", "rejected_by"),
    },
    "reject": {
        "title": "Reject",
        "add_key": "rejected_by",
        "remove_keys": ("approved_by", "pending_by"),
    },
}


def _snapshot(element, config):
    """Current Approved / Rejected / Pending strings for debug logging."""
    parts = []
    for key, label in (
        ("approved_by", "A"),
        ("rejected_by", "R"),
        ("pending_by", "P"),
    ):
        mapped = config.parameter(key)
        if not mapped:
            parts.append("{}=?".format(label))
            continue
        param = get_parameter(element, guid=mapped["guid"], name=mapped["name"])
        parts.append("{}={!r}".format(label, param_as_string(param)))
    return " ".join(parts)


def apply_status(action_name):
    """Apply an approval action to the current selection.

    Returns True if at least one element was updated.
    """
    spec = ACTIONS.get(action_name)
    if not spec:
        log_error("Unknown action: {}".format(action_name))
        forms.alert("Unknown Void Status action: {}".format(action_name), title="Void Status")
        return False

    log_info("Action '{}' started".format(action_name))

    doc = revit.doc
    profile = load_profile(doc)
    discipline = (profile.get("discipline") or "").strip()
    if not discipline:
        log_warning("Action aborted: no discipline for this user in this model")
        forms.alert(
            "Set your discipline in Add-Ins → Void Status → Config before approving openings.\n\n"
            "Discipline is stored for you in this Revit file.",
            title="Void Status",
        )
        return False

    selection = revit.get_selection()
    if not selection or not selection.element_ids:
        log_warning("Action aborted: empty selection")
        forms.alert("Select one or more openings / voids first.", title="Void Status")
        return False

    selection_ids = list(selection.element_ids)
    debug = is_debug()
    if debug:
        log_debug(
            "Profile name={!r} discipline={!r} selection={}".format(
                profile.get("name"), discipline, len(selection_ids)
            )
        )

    try:
        config = load_config(doc)
    except ValueError as ex:
        log_exception("Action aborted: invalid project XML", ex)
        forms.alert(
            "Project Void Status XML is invalid.\nOpen Config and fix it.\n\n{}".format(ex),
            title="Void Status",
        )
        return False

    separator = config.value_separator
    add_map = config.parameter(spec["add_key"])
    remove_maps = [config.parameter(key) for key in spec["remove_keys"]]

    if not add_map:
        log_error("Missing parameter mapping for {}".format(spec["add_key"]))
        forms.alert(
            "Parameter mapping for '{}' is missing in the project XML.".format(spec["add_key"]),
            title="Void Status",
        )
        return False

    success_count = 0
    failed_ids = []

    t = Transaction(doc, "Void Status: {}".format(spec["title"]))
    t.Start()
    try:
        for element_id in selection_ids:
            element = doc.GetElement(element_id)
            if not element:
                log_warning("Skip missing element id={}".format(element_id_str(element_id)))
                failed_ids.append(element_id)
                continue

            if debug:
                log_debug(
                    "Before {} {}".format(element_label(element), _snapshot(element, config))
                )

            add_param = get_parameter(element, guid=add_map["guid"], name=add_map["name"])
            if not add_param:
                log_warning(
                    "Skip {}: missing parameter {} (guid={})".format(
                        element_label(element), add_map["name"], add_map["guid"]
                    )
                )
                failed_ids.append(element_id)
                continue

            current = param_as_string(add_param)
            updated = add_value(current, discipline, separator)
            if not set_string_value(add_param, updated):
                log_warning(
                    "Skip {}: could not write {}".format(
                        element_label(element), add_map["name"]
                    )
                )
                failed_ids.append(element_id)
                continue

            for remove_key, remove_map in zip(spec["remove_keys"], remove_maps):
                if not remove_map:
                    continue
                rem_param = get_parameter(
                    element, guid=remove_map["guid"], name=remove_map["name"]
                )
                if not rem_param:
                    continue
                rem_updated = remove_value(
                    param_as_string(rem_param), discipline, separator
                )
                if not set_string_value(rem_param, rem_updated):
                    log_warning(
                        "Could not update {} on {}".format(
                            remove_map["name"], element_label(element)
                        )
                    )

            if debug:
                log_debug(
                    "After  {} {}".format(element_label(element), _snapshot(element, config))
                )
            success_count += 1
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
            log_warning("Transaction rolled back for '{}'".format(action_name))
        log_exception("Void Status action failed", ex)
        logger.error("Void Status action failed: {}".format(ex))
        forms.alert("Error: {}".format(ex), title="Void Status")
        return False

    log_info(
        "Action '{}' done: updated={} skipped={}".format(
            action_name, success_count, len(failed_ids)
        )
    )

    if failed_ids:
        output = script.get_output()
        output.print_md(
            "**Void Status — {} updated, {} skipped** (missing status parameters?)".format(
                success_count, len(failed_ids)
            )
        )
        for element_id in failed_ids:
            output.print_md("- {}".format(output.linkify(element_id)))

    if success_count == 0:
        log_warning("Action '{}' wrote nothing".format(action_name))
        forms.alert(
            "Could not write '{}' on the selection.\n\n"
            "Bind the status parameters from Add-Ins → Void Status → Config, "
            "or pick openings that already have them.".format(
                add_map["name"]
            ),
            title="Void Status",
        )
        return False

    return True


RESET_TARGETS = {
    "all": ("approved_by", "rejected_by", "pending_by"),
    "approved": ("approved_by",),
    "rejected": ("rejected_by",),
    "pending": ("pending_by",),
}


def reset_status(which):
    """Empty the chosen approval value-list field(s) on the selection.

    This clears every discipline in that field, not only the current profile.
    """
    keys = RESET_TARGETS.get(which)
    if not keys:
        log_error("Unknown reset target: {}".format(which))
        forms.alert("Unknown Void Status reset: {}".format(which), title="Void Status")
        return False

    log_info("Reset '{}' started".format(which))

    selection = revit.get_selection()
    if not selection or not selection.element_ids:
        log_warning("Reset aborted: empty selection")
        forms.alert("Select one or more openings / voids first.", title="Void Status")
        return False

    selection_ids = list(selection.element_ids)

    doc = revit.doc
    try:
        config = load_config(doc)
    except ValueError as ex:
        log_exception("Reset aborted: invalid project XML", ex)
        forms.alert(
            "Project Void Status XML is invalid.\nOpen Config and fix it.\n\n{}".format(ex),
            title="Void Status",
        )
        return False

    param_maps = []
    for key in keys:
        mapped = config.parameter(key)
        if not mapped:
            log_error("Missing parameter mapping for {}".format(key))
            forms.alert(
                "Parameter mapping for '{}' is missing in the project XML.".format(key),
                title="Void Status",
            )
            return False
        param_maps.append(mapped)

    field_names = ", ".join([item["name"] for item in param_maps])
    count = len(selection_ids)
    log_info("Reset confirm prompt for {} on {} elements".format(field_names, count))
    if not forms.alert(
        "Clear {} on {} selected element(s)?\n\n"
        "This empties the field for every discipline, not only yours.".format(
            field_names, count
        ),
        yes=True,
        no=True,
        title="Void Status",
    ):
        log_info("Reset cancelled by user")
        return False

    success_count = 0
    failed_ids = []

    t = Transaction(doc, "Void Status: Reset {}".format(field_names))
    t.Start()
    try:
        for element_id in selection_ids:
            element = doc.GetElement(element_id)
            if not element:
                log_warning("Reset skip missing element id={}".format(element_id_str(element_id)))
                failed_ids.append(element_id)
                continue
            wrote_any = False
            missing_all = True
            for mapped in param_maps:
                param = get_parameter(element, guid=mapped["guid"], name=mapped["name"])
                if not param:
                    continue
                missing_all = False
                if set_string_value(param, ""):
                    wrote_any = True
                else:
                    log_warning(
                        "Could not clear {} on {}".format(
                            mapped["name"], element_label(element)
                        )
                    )
            if missing_all or not wrote_any:
                log_warning("Reset skipped {}".format(element_label(element)))
                failed_ids.append(element_id)
            else:
                success_count += 1
        t.Commit()
        log_info("Reset transaction committed")
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
            log_warning("Reset transaction rolled back")
        log_exception("Void Status reset failed", ex)
        logger.error("Void Status reset failed: {}".format(ex))
        forms.alert("Error: {}".format(ex), title="Void Status")
        return False

    log_info(
        "Reset '{}' done: updated={} skipped={}".format(
            which, success_count, len(failed_ids)
        )
    )

    if failed_ids:
        output = script.get_output()
        output.print_md(
            "**Void Status reset — {} updated, {} skipped**".format(
                success_count, len(failed_ids)
            )
        )
        for element_id in failed_ids:
            output.print_md("- {}".format(output.linkify(element_id)))

    if success_count == 0:
        log_warning("Reset '{}' wrote nothing".format(which))
        forms.alert(
            "Could not clear {} on the selection.\n\n"
            "Bind the status parameters from Add-Ins → Void Status → Config, "
            "or pick openings that already have them.".format(field_names),
            title="Void Status",
        )
        return False

    return True
