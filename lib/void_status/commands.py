# -*- coding: utf-8 -*-
"""Approve, Pending, Reject, and Reset on the current selection."""

from Autodesk.Revit.DB import Transaction
from pyrevit import revit, forms, script

from void_status.contract import ACTIONS, RESET_TARGETS
from void_status.storage import load_config
from void_status.profile import load_profile
from void_status.values import edit_status_fields
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


def _alert(message):
    forms.alert(message, title="Void Status")


def _selection_ids():
    selection = revit.get_selection()
    if not selection or not selection.element_ids:
        return None
    return list(selection.element_ids)


def _load_project_config(doc, verb):
    try:
        return load_config(doc)
    except ValueError as ex:
        log_exception("{} aborted: invalid project XML".format(verb), ex)
        _alert(
            "Project Void Status XML is invalid.\nOpen Config and fix it.\n\n{}".format(ex)
        )
        return None


def _read_fields(element, config, keys):
    fields = {}
    params = {}
    for key in keys:
        mapped = config.parameter(key)
        if not mapped:
            fields[key] = ""
            params[key] = None
            continue
        param = get_parameter(element, guid=mapped["guid"], name=mapped["name"])
        params[key] = param
        fields[key] = param_as_string(param) if param else ""
    return fields, params


def _snapshot(element, config):
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


def _report_skips(success_count, failed_ids):
    if not failed_ids:
        return
    output = script.get_output()
    output.print_md(
        "**Void Status — {} updated, {} skipped** (missing status parameters?)".format(
            success_count, len(failed_ids)
        )
    )
    for element_id in failed_ids:
        output.print_md("- {}".format(output.linkify(element_id)))
    if success_count:
        _alert(
            "Updated {} element(s). Skipped {} (missing status parameters).\n\n"
            "The skipped elements are listed in the pyRevit output window.".format(
                success_count, len(failed_ids)
            )
        )


def _rollback(transaction, label):
    if transaction.HasStarted() and not transaction.HasEnded():
        transaction.RollBack()
        log_warning("{} rolled back".format(label))


def apply_status(action_name):
    """Apply an approval action to the current selection.

    Returns True if at least one element was updated.
    """
    spec = ACTIONS.get(action_name)
    if not spec:
        log_error("Unknown action: {}".format(action_name))
        _alert("Unknown Void Status action: {}".format(action_name))
        return False

    log_info("Action '{}' started".format(action_name))
    doc = revit.doc
    profile = load_profile(doc)
    discipline = (profile.get("discipline") or "").strip()
    if not discipline:
        log_warning("Action aborted: no discipline for this user in this model")
        _alert(
            "Set your discipline in Add-Ins → Void Status → Config before approving openings.\n\n"
            "Discipline is stored for you in this Revit file."
        )
        return False

    selection_ids = _selection_ids()
    if not selection_ids:
        log_warning("Action aborted: empty selection")
        _alert("Select one or more openings / voids first.")
        return False

    debug = is_debug()
    if debug:
        log_debug(
            "Profile name={!r} discipline={!r} selection={}".format(
                profile.get("name"), discipline, len(selection_ids)
            )
        )

    config = _load_project_config(doc, "Action")
    if config is None:
        return False

    separator = config.value_separator
    add_map = config.parameter(spec["add_key"])
    if not add_map:
        log_error("Missing parameter mapping for {}".format(spec["add_key"]))
        _alert(
            "Parameter mapping for '{}' is missing in the project XML.".format(spec["add_key"])
        )
        return False

    keys = (spec["add_key"],) + tuple(spec["remove_keys"])
    success_count = 0
    failed_ids = []
    transaction = Transaction(doc, "Void Status: {}".format(spec["title"]))
    transaction.Start()
    try:
        for element_id in selection_ids:
            element = doc.GetElement(element_id)
            if not element:
                log_warning("Skip missing element id={}".format(element_id_str(element_id)))
                failed_ids.append(element_id)
                continue
            if debug:
                log_debug("Before {} {}".format(element_label(element), _snapshot(element, config)))

            fields, params = _read_fields(element, config, keys)
            add_param = params.get(spec["add_key"])
            if not add_param:
                log_warning(
                    "Skip {}: missing parameter {} (guid={})".format(
                        element_label(element), add_map["name"], add_map["guid"]
                    )
                )
                failed_ids.append(element_id)
                continue

            updated = edit_status_fields(
                fields, spec["add_key"], spec["remove_keys"], discipline, separator
            )
            if not set_string_value(add_param, updated.get(spec["add_key"]) or ""):
                log_warning(
                    "Skip {}: could not write {}".format(element_label(element), add_map["name"])
                )
                failed_ids.append(element_id)
                continue

            for remove_key in spec["remove_keys"]:
                remove_param = params.get(remove_key)
                if not remove_param:
                    continue
                mapped = config.parameter(remove_key)
                if not set_string_value(remove_param, updated.get(remove_key) or ""):
                    log_warning(
                        "Could not update {} on {}".format(
                            mapped["name"] if mapped else remove_key,
                            element_label(element),
                        )
                    )

            if debug:
                log_debug("After  {} {}".format(element_label(element), _snapshot(element, config)))
            success_count += 1
        transaction.Commit()
    except Exception as ex:
        _rollback(transaction, "Transaction")
        log_exception("Void Status action failed", ex)
        logger.error("Void Status action failed: {}".format(ex))
        _alert("Error: {}".format(ex))
        return False

    log_info(
        "Action '{}' done: updated={} skipped={}".format(
            action_name, success_count, len(failed_ids)
        )
    )
    _report_skips(success_count, failed_ids)
    if success_count == 0:
        log_warning("Action '{}' wrote nothing".format(action_name))
        _alert(
            "Could not write '{}' on the selection.\n\n"
            "Bind the status parameters from Add-Ins → Void Status → Config, "
            "or pick openings that already have them.".format(add_map["name"])
        )
        return False
    return True


def reset_status(which):
    """Empty the chosen approval fields on the selection.

    This clears every discipline in that field, not only the current profile.
    """
    keys = RESET_TARGETS.get(which)
    if not keys:
        log_error("Unknown reset target: {}".format(which))
        _alert("Unknown Void Status reset: {}".format(which))
        return False

    log_info("Reset '{}' started".format(which))
    selection_ids = _selection_ids()
    if not selection_ids:
        log_warning("Reset aborted: empty selection")
        _alert("Select one or more openings / voids first.")
        return False

    doc = revit.doc
    config = _load_project_config(doc, "Reset")
    if config is None:
        return False

    param_maps = []
    for key in keys:
        mapped = config.parameter(key)
        if not mapped:
            log_error("Missing parameter mapping for {}".format(key))
            _alert("Parameter mapping for '{}' is missing in the project XML.".format(key))
            return False
        param_maps.append(mapped)

    field_names = ", ".join([item["name"] for item in param_maps])
    log_info("Reset confirm prompt for {} on {} elements".format(field_names, len(selection_ids)))
    if not forms.alert(
        "Clear {} on {} selected element(s)?\n\n"
        "This empties the field for every discipline, not only yours.".format(
            field_names, len(selection_ids)
        ),
        yes=True,
        no=True,
        title="Void Status",
    ):
        log_info("Reset cancelled by user")
        return False

    success_count = 0
    failed_ids = []
    transaction = Transaction(doc, "Void Status: Reset {}".format(field_names))
    transaction.Start()
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
                        "Could not clear {} on {}".format(mapped["name"], element_label(element))
                    )
            if missing_all or not wrote_any:
                log_warning("Reset skipped {}".format(element_label(element)))
                failed_ids.append(element_id)
            else:
                success_count += 1
        transaction.Commit()
        log_info("Reset transaction committed")
    except Exception as ex:
        _rollback(transaction, "Reset transaction")
        log_exception("Void Status reset failed", ex)
        logger.error("Void Status reset failed: {}".format(ex))
        _alert("Error: {}".format(ex))
        return False

    log_info(
        "Reset '{}' done: updated={} skipped={}".format(which, success_count, len(failed_ids))
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
        if success_count:
            _alert(
                "Cleared {} element(s). Skipped {} (missing status parameters).\n\n"
                "The skipped elements are listed in the pyRevit output window.".format(
                    success_count, len(failed_ids)
                )
            )
    if success_count == 0:
        log_warning("Reset '{}' wrote nothing".format(which))
        _alert(
            "Could not clear {} on the selection.\n\n"
            "Bind the status parameters from Add-Ins → Void Status → Config, "
            "or pick openings that already have them.".format(field_names)
        )
        return False
    return True
