# -*- coding: utf-8 -*-
"""Bind bundled shared parameters as project parameters."""

import System
from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    SharedParameterElement,
    Transaction,
)
from pyrevit import script

from void_status.constants import STATUS_PARAMETERS
from void_status.paths import shared_parameter_file, local_bundle_file
from void_status.logutil import log_debug, log_info, log_warning, log_error, log_exception

logger = script.get_logger()


def _param_group():
    try:
        from Autodesk.Revit.DB import GroupTypeId
        return GroupTypeId.Data
    except Exception:
        try:
            from Autodesk.Revit.DB import BuiltInParameterGroup
            return BuiltInParameterGroup.PG_DATA
        except Exception:
            return None


def _guid_text(value):
    text = str(value or "").lower().strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    return text


def _category_set(doc, app, category_names):
    cats = app.Create.NewCategorySet()
    categories = doc.Settings.Categories
    for name in category_names:
        try:
            bic = getattr(BuiltInCategory, name)
            cat = categories.get_Item(bic)
            if cat and cat.AllowsBoundParameters:
                cats.Insert(cat)
        except Exception as ex:
            logger.debug("Skip category {}: {}".format(name, ex))
    return cats


def _category_ids(category_set):
    ids = set()
    if category_set is None:
        return ids
    try:
        for cat in category_set:
            try:
                ids.add(int(cat.Id.IntegerValue))
            except Exception:
                continue
    except Exception:
        pass
    return ids


def _shared_param_element(doc, guid_lower):
    """Return SharedParameterElement for GUID, or None."""
    try:
        spe = SharedParameterElement.Lookup(doc, System.Guid(guid_lower))
        if spe is not None:
            return spe
    except Exception:
        pass
    try:
        for spe in FilteredElementCollector(doc).OfClass(SharedParameterElement):
            try:
                if _guid_text(spe.GuidValue) == guid_lower:
                    return spe
            except Exception:
                continue
    except Exception as ex:
        log_debug("Could not list SharedParameterElements: {}".format(ex))
    return None


def _binding_for_guid(doc, guid_lower):
    """Return (definition, binding) for a shared-parameter GUID, or (None, None)."""
    spe = _shared_param_element(doc, guid_lower)
    if spe is not None:
        try:
            definition = spe.GetDefinition()
            if definition is not None and doc.ParameterBindings.Contains(definition):
                return definition, doc.ParameterBindings[definition]
        except Exception as ex:
            log_debug(
                "SharedParameterElement present but no binding for {}: {}".format(
                    guid_lower, ex
                )
            )

    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        definition = it.Key
        try:
            def_guid = _guid_text(definition.GUID)
        except Exception:
            continue
        if def_guid == guid_lower:
            return definition, it.Current
    return None, None


def _definition_from_file(def_file, guid_lower):
    for group in def_file.Groups:
        for definition in group.Definitions:
            try:
                if _guid_text(definition.GUID) == guid_lower:
                    return definition
            except Exception:
                continue
    return None


def _definition_count(def_file):
    count = 0
    try:
        for group in def_file.Groups:
            for _definition in group.Definitions:
                count += 1
    except Exception:
        pass
    return count


def _insert_or_reinsert(doc, definition, binding, group_id, reinsert):
    """Insert or ReInsert a project-parameter binding. Return True on success."""
    if group_id is not None:
        try:
            if reinsert:
                return doc.ParameterBindings.ReInsert(definition, binding, group_id)
            return doc.ParameterBindings.Insert(definition, binding, group_id)
        except TypeError:
            log_debug("Binding with group_id TypeError; retrying without group")
    if reinsert:
        return doc.ParameterBindings.ReInsert(definition, binding)
    return doc.ParameterBindings.Insert(definition, binding)


def _bind_definition(doc, definition, binding, group_id, item_name):
    """Insert, falling back to ReInsert when the param was bound before.

    Revit returns False from Insert if the parameter was ever bound in the
    project (even after delete). ReInsert is the documented recovery path.
    """
    inserted = _insert_or_reinsert(
        doc, definition, binding, group_id, reinsert=False
    )
    if inserted:
        log_info("Bound {}".format(item_name))
        return "added"

    log_debug(
        "Insert returned False for {}; trying ReInsert".format(item_name)
    )
    updated = _insert_or_reinsert(
        doc, definition, binding, group_id, reinsert=True
    )
    if updated:
        log_info("Rebound {}".format(item_name))
        return "added"

    bound_def, bound = _binding_for_guid(doc, _guid_text(definition.GUID))
    if bound_def is not None and bound is not None:
        log_info(
            "Already bound after Insert/ReInsert False: {}".format(item_name)
        )
        return "already"

    log_warning(
        "Could not bind {} (Insert and ReInsert both returned False)".format(
            item_name
        )
    )
    return "failed"


def ensure_shared_parameters(doc, category_names, start_path):
    """Add or repair missing shared parameters as instance project parameters.

    A GUID that only exists on loaded families (SharedParameterElement) is not
    enough — we require a project binding that covers the configured categories.
    Incomplete bindings are expanded with ReInsert. Insert False falls back to
    ReInsert (common for ConVoid params already used in the project).

    Returns (added_count, already_present_count, error_message).
    ``added_count`` includes new inserts and repaired bindings.
    """
    log_info(
        "Bind shared parameters start categories={} start_path={}".format(
            list(category_names or []), start_path
        )
    )
    sp_path = shared_parameter_file(start_path)
    if not sp_path:
        log_error("Bundled shared parameter file not located")
        return 0, 0, "Could not locate the bundled shared parameter file."

    import os.path as op
    if not op.isfile(sp_path):
        log_error("Shared parameter file missing: {}".format(sp_path))
        return 0, 0, "Shared parameter file not found:\n{}".format(sp_path)

    try:
        sp_path = local_bundle_file(sp_path)
    except Exception as ex:
        log_warning("Could not cache shared parameter file: {}".format(ex))

    log_info("Shared parameter file: {}".format(sp_path))

    app = doc.Application
    original = app.SharedParametersFilename
    wanted = dict((item["guid"].lower(), item) for item in STATUS_PARAMETERS)
    group_id = _param_group()
    log_debug("Parameter group for binding: {}".format(group_id))

    added = 0
    already = 0
    try:
        app.SharedParametersFilename = sp_path
        def_file = app.OpenSharedParameterFile()
        if def_file is None:
            log_error("Revit could not open shared parameter file {}".format(sp_path))
            return 0, 0, "Revit could not open the shared parameter file."

        found = _definition_count(def_file)
        log_info("Shared parameter file definitions: {}".format(found))
        if found == 0:
            log_error("Shared parameter file opened but has no definitions")
            return (
                0,
                0,
                "Shared parameter file opened with no definitions.\n"
                "Check that VoidStatus.txt is ANSI/UTF-8 (not UTF-16 without BOM).",
            )

        cat_set = _category_set(doc, app, category_names)
        log_info("Category set size for binding: {}".format(cat_set.Size))
        if cat_set.Size == 0:
            log_error("No bindable categories from {}".format(list(category_names or [])))
            return 0, 0, "None of the configured categories accept bound parameters."

        wanted_cat_ids = _category_ids(cat_set)
        to_insert = []
        to_reinsert = []

        for guid, item in wanted.items():
            bound_def, bound = _binding_for_guid(doc, guid)
            if bound_def is None or bound is None:
                definition = _definition_from_file(def_file, guid)
                if definition is None:
                    log_error(
                        "Definition missing from shared parameter file: {} ({})".format(
                            item["name"], guid
                        )
                    )
                    return (
                        added,
                        already,
                        "Shared parameter file is missing {}.".format(item["name"]),
                    )
                to_insert.append((definition, item))
                spe = _shared_param_element(doc, guid)
                if spe is not None:
                    log_info(
                        "Will bind (SharedParameterElement exists, no project "
                        "binding yet): {} ({})".format(item["name"], guid)
                    )
                else:
                    log_info("Will bind: {} ({})".format(item["name"], guid))
                continue

            try:
                existing_cats = bound.Categories
            except Exception:
                existing_cats = None
            existing_ids = _category_ids(existing_cats)
            missing = wanted_cat_ids - existing_ids
            if missing:
                merged = app.Create.NewCategorySet()
                if existing_cats is not None:
                    for cat in existing_cats:
                        try:
                            merged.Insert(cat)
                        except Exception:
                            continue
                for cat in cat_set:
                    try:
                        merged.Insert(cat)
                    except Exception:
                        continue
                to_reinsert.append((bound_def, merged, item))
                log_info(
                    "Will repair binding categories for {} (missing {})".format(
                        item["name"], len(missing)
                    )
                )
            else:
                already += 1
                log_debug("Already bound: {} ({})".format(item["name"], guid))

        if not to_insert and not to_reinsert:
            log_info(
                "Nothing to bind; {} status parameters already present".format(already)
            )
            return 0, already, None

        binding = app.Create.NewInstanceBinding(cat_set)
        t = Transaction(doc, "Bind Void Status shared parameters")
        t.Start()
        try:
            for definition, item in to_insert:
                result = _bind_definition(
                    doc, definition, binding, group_id, item["name"]
                )
                if result == "added":
                    added += 1
                elif result == "already":
                    already += 1

            for definition, merged_cats, item in to_reinsert:
                repaired = app.Create.NewInstanceBinding(merged_cats)
                updated = _insert_or_reinsert(
                    doc, definition, repaired, group_id, reinsert=True
                )
                if updated:
                    added += 1
                    log_info("Repaired binding for {}".format(item["name"]))
                else:
                    log_warning(
                        "Binding.ReInsert returned False for {}".format(item["name"])
                    )

            t.Commit()
            log_info("Bind transaction committed")
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
                log_warning("Bind transaction rolled back")
            log_exception("Bind shared parameters failed", ex)
            return added, already, str(ex)
    finally:
        try:
            app.SharedParametersFilename = original
        except Exception as ex:
            log_warning("Could not restore SharedParametersFilename: {}".format(ex))

    log_info("Bind done: added={} already={}".format(added, already))
    return added, already, None
