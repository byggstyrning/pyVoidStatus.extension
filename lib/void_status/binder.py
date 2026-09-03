# -*- coding: utf-8 -*-
"""Bind bundled shared parameters as project parameters."""

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    SharedParameterElement,
    Transaction,
)
from pyrevit import script

from void_status.constants import STATUS_PARAMETERS
from void_status.paths import shared_parameter_file
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


def _existing_guids(doc):
    found = set()
    try:
        for sp in FilteredElementCollector(doc).OfClass(SharedParameterElement):
            try:
                found.add(str(sp.GuidValue).lower())
            except Exception:
                continue
    except Exception as ex:
        logger.debug("Could not list SharedParameterElements: {}".format(ex))
    return found


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


def ensure_shared_parameters(doc, category_names, start_path):
    """Add missing shared parameters as instance project parameters.

    Existing bindings are left untouched.
    Returns (added_count, already_present_count, error_message).
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

    log_info("Shared parameter file: {}".format(sp_path))

    app = doc.Application
    original = app.SharedParametersFilename
    existing = _existing_guids(doc)
    log_info("Project already has {} shared-parameter GUID(s)".format(len(existing)))
    wanted = dict((item["guid"].lower(), item) for item in STATUS_PARAMETERS)
    already = 0
    to_add_names = []
    for guid, item in wanted.items():
        if guid in existing:
            already += 1
            log_debug("Already present: {} ({})".format(item["name"], guid))
        else:
            to_add_names.append(item["name"])
            log_info("Will bind: {} ({})".format(item["name"], guid))

    if not to_add_names:
        log_info("Nothing to bind; {} status parameters already present".format(already))
        return 0, already, None

    group_id = _param_group()
    log_debug("Parameter group for binding: {}".format(group_id))
    added = 0
    try:
        app.SharedParametersFilename = sp_path
        def_file = app.OpenSharedParameterFile()
        if def_file is None:
            log_error("Revit could not open shared parameter file {}".format(sp_path))
            return 0, already, "Revit could not open the shared parameter file."

        definitions = []
        for group in def_file.Groups:
            for definition in group.Definitions:
                guid_str = str(definition.GUID).lower()
                if guid_str in wanted and guid_str not in existing:
                    definitions.append(definition)
                    log_debug(
                        "Definition from file: {} ({})".format(
                            definition.Name, guid_str
                        )
                    )

        if not definitions:
            log_error("No matching definitions in {}".format(sp_path))
            return 0, already, "No matching definitions found in the shared parameter file."

        cat_set = _category_set(doc, app, category_names)
        log_info("Category set size for binding: {}".format(cat_set.Size))
        if cat_set.Size == 0:
            log_error("No bindable categories from {}".format(list(category_names or [])))
            return 0, already, "None of the configured categories accept bound parameters."

        binding = app.Create.NewInstanceBinding(cat_set)
        t = Transaction(doc, "Bind Void Status shared parameters")
        t.Start()
        try:
            for definition in definitions:
                inserted = False
                if group_id is not None:
                    try:
                        inserted = doc.ParameterBindings.Insert(definition, binding, group_id)
                    except TypeError:
                        log_debug("Insert with group_id TypeError; retrying without group")
                        inserted = doc.ParameterBindings.Insert(definition, binding)
                else:
                    inserted = doc.ParameterBindings.Insert(definition, binding)
                if inserted:
                    added += 1
                    log_info("Bound {}".format(definition.Name))
                else:
                    log_warning("Binding.Insert returned False for {}".format(definition.Name))
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
