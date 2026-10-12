# -*- coding: utf-8 -*-
"""Place Void Status on Revit's Add-Ins tab, and the status buttons on Modify.

pyRevit creates the buttons on its own tab. This module copies them onto
Add-Ins and Modify, then removes the pyRevit copies so the tools are not
left on the pyRevit tab.
"""

import clr
clr.AddReference("AdWindows")
import Autodesk.Windows as AdWindows

from pyrevit import HOST_APP
from System import EventHandler
from Autodesk.Revit.DB import Events
from Autodesk.Revit.UI import Events as UIEvents
from pyrevit.coreutils import envvars

from void_status.logutil import log_debug, log_info, log_warning, log_exception

SETTINGS_PANEL_TITLE = "Void Status Settings"
STATUS_PANEL_TITLE = "Void Status"
ADDINS_PANEL_TITLE = "Void Status"
_LEGACY_TAB_TITLE = "Void Status"

_ADDINS_TITLES = ("add-ins", "addins", "add-in", "tillägg")
_MODIFY_TITLES = ("modify", "ändra")

_HANDLER_ENV = "pyvoidstatus.startup_handlers"
_idling_attempts = [0]
_MAX_IDLING_ATTEMPTS = 50


def _norm(title):
    return (title or "").strip().lower()


def _is_addins_tab(tab):
    if _norm(tab.Title) in _ADDINS_TITLES:
        return True
    try:
        if _norm(str(tab.Id or "")) in _ADDINS_TITLES:
            return True
    except Exception:
        pass
    return False


def _is_modify_tab(tab):
    return _norm(tab.Title) in _MODIFY_TITLES


def _is_legacy_tab(tab):
    return _norm(tab.Title) == _norm(_LEGACY_TAB_TITLE) and not _is_addins_tab(tab)


def _panel_title(panel):
    try:
        if panel.Source:
            return panel.Source.Title
    except Exception:
        pass
    return None


def _tab_has_panel(tab, title):
    if not tab:
        return False
    for panel in tab.Panels:
        if _panel_title(panel) == title:
            return True
    return False


def _placement_state(ribbon):
    if not ribbon:
        return False, False
    addins_tab = _find_tab(ribbon, _is_addins_tab, visible_only=False)
    addins_ok = bool(addins_tab and _tab_has_panel(addins_tab, ADDINS_PANEL_TITLE))
    modify_tab = _find_tab(ribbon, _is_modify_tab, visible_only=True)
    modify_ok = bool(modify_tab and _tab_has_panel(modify_tab, STATUS_PANEL_TITLE))
    return addins_ok, modify_ok


def _find_tab(ribbon, predicate, visible_only=False):
    for tab in ribbon.Tabs:
        try:
            if visible_only and not tab.IsVisible:
                continue
            if predicate(tab):
                return tab
        except Exception:
            continue
    return None


def _find_source_panel(ribbon, panel_title):
    """Find a panel pyRevit created, not one already on Add-Ins or Modify."""
    for tab in ribbon.Tabs:
        if _is_addins_tab(tab) or _is_modify_tab(tab):
            continue
        for panel in tab.Panels:
            if _panel_title(panel) == panel_title:
                return panel, tab
    return None, None


def _clone_panel(source_panel, dest_tab, dest_title):
    if _tab_has_panel(dest_tab, dest_title):
        return True
    dest_tab.Panels.Add(AdWindows.RibbonPanel())
    new_panel = dest_tab.Panels[dest_tab.Panels.Count - 1]
    cloned = source_panel.Source.Clone()
    cloned.Title = dest_title
    new_panel.Source = cloned
    new_panel.IsEnabled = True
    return True


def _remove_panel(tab, panel):
    """Take a panel off its tab so it does not stay on pyRevit."""
    if not tab or not panel:
        return False
    try:
        tab.Panels.Remove(panel)
        log_info(
            "Removed '{}' from '{}'".format(_panel_title(panel), _norm(tab.Title) or tab.Title)
        )
        return True
    except Exception as ex:
        log_debug(
            "Could not remove panel '{}' from '{}': {}".format(
                _panel_title(panel), tab.Title, ex
            )
        )
        try:
            panel.IsVisible = False
            return True
        except Exception:
            return False


def _remove_legacy_tab(ribbon):
    legacy = _find_tab(ribbon, _is_legacy_tab, visible_only=False)
    if not legacy:
        return
    try:
        ribbon.Tabs.Remove(legacy)
        log_info("Removed leftover '{}' ribbon tab".format(_LEGACY_TAB_TITLE))
    except Exception as ex:
        log_debug("Could not remove leftover tab: {}".format(ex))


def place_void_status_panels():
    """Copy settings onto Add-Ins and status buttons onto Modify.

    The pyRevit copies are removed once the destination panel exists.
    Modify is contextual, so that copy waits until Revit shows the tab.

    Returns True when Add-Ins settings are in place.
    """
    ribbon = AdWindows.ComponentManager.Ribbon
    if not ribbon:
        log_debug("Ribbon not ready yet")
        return False

    addins_ok = False
    settings_panel = None
    settings_tab = None
    try:
        addins_tab = _find_tab(ribbon, _is_addins_tab, visible_only=False)
        settings_panel, settings_tab = _find_source_panel(ribbon, SETTINGS_PANEL_TITLE)
        if addins_tab and _tab_has_panel(addins_tab, ADDINS_PANEL_TITLE):
            addins_ok = True
        elif addins_tab and settings_panel:
            _clone_panel(settings_panel, addins_tab, ADDINS_PANEL_TITLE)
            addins_ok = True
            log_info(
                "Added '{}' to Add-Ins as '{}'".format(
                    SETTINGS_PANEL_TITLE, ADDINS_PANEL_TITLE
                )
            )
    except Exception as ex:
        log_exception("Failed to place Void Status on Add-Ins", ex)

    status_panel = None
    status_tab = None
    modify_ok = False
    try:
        modify_tab = _find_tab(ribbon, _is_modify_tab, visible_only=True)
        status_panel, status_tab = _find_source_panel(ribbon, STATUS_PANEL_TITLE)
        if modify_tab and _tab_has_panel(modify_tab, STATUS_PANEL_TITLE):
            modify_ok = True
        elif modify_tab and status_panel:
            _clone_panel(status_panel, modify_tab, STATUS_PANEL_TITLE)
            modify_ok = True
            log_info("Added '{}' to Modify".format(STATUS_PANEL_TITLE))
    except Exception as ex:
        log_exception("Failed to add '{}' to Modify".format(STATUS_PANEL_TITLE), ex)

    if addins_ok and settings_panel:
        _remove_panel(settings_tab, settings_panel)
    if modify_ok and status_panel:
        _remove_panel(status_tab, status_panel)
    if addins_ok:
        _remove_legacy_tab(ribbon)
    return addins_ok


def _handler_store():
    stored = envvars.get_pyrevit_env_var(_HANDLER_ENV)
    if not isinstance(stored, dict):
        stored = {}
        envvars.set_pyrevit_env_var(_HANDLER_ENV, stored)
    return stored


def _detach(event_name, handler):
    if handler is None:
        return
    try:
        if event_name == "Idling":
            HOST_APP.uiapp.Idling -= handler
        elif event_name == "ViewActivated":
            HOST_APP.uiapp.ViewActivated -= handler
        elif event_name == "SelectionChanged":
            HOST_APP.uiapp.SelectionChanged -= handler
        elif event_name == "DocumentOpening":
            HOST_APP.app.DocumentOpening -= handler
        elif event_name == "DocumentOpened":
            HOST_APP.app.DocumentOpened -= handler
    except Exception as ex:
        log_debug("Could not unsubscribe {}: {}".format(event_name, ex))


def _unsubscribe(event_name):
    stored = _handler_store()
    handler = stored.get(event_name)
    if handler is None:
        return False
    _detach(event_name, handler)
    stored[event_name] = None
    log_debug("Unsubscribed {}".format(event_name))
    return True


def _subscribe(event_name, callback, event_args_type):
    stored = _handler_store()
    previous = stored.get(event_name)
    if previous is not None:
        _detach(event_name, previous)
        stored[event_name] = None
    handler = EventHandler[event_args_type](callback)
    if event_name == "Idling":
        HOST_APP.uiapp.Idling += handler
    elif event_name == "ViewActivated":
        HOST_APP.uiapp.ViewActivated += handler
    elif event_name == "SelectionChanged":
        HOST_APP.uiapp.SelectionChanged += handler
    elif event_name == "DocumentOpening":
        HOST_APP.app.DocumentOpening += handler
    elif event_name == "DocumentOpened":
        HOST_APP.app.DocumentOpened += handler
    else:
        log_warning("Unknown startup event {}".format(event_name))
        return None
    stored[event_name] = handler
    log_debug("Subscribed to {}".format(event_name))
    return handler


def _stop_finished_watchers():
    """Drop ribbon scans once the cloned panels exist.

    Add-Ins placement ends Idling and ViewActivated. SelectionChanged stays
    only until the contextual Modify clone succeeds.
    """
    ribbon = AdWindows.ComponentManager.Ribbon
    addins_ok, modify_ok = _placement_state(ribbon)
    if addins_ok:
        _unsubscribe("ViewActivated")
        _unsubscribe("Idling")
    if modify_ok:
        if _unsubscribe("SelectionChanged"):
            log_info("Modify panel is in place; selection watch stopped")
        _unsubscribe("Idling")
    return addins_ok, modify_ok


def _idling_handler(sender, args):
    _idling_attempts[0] += 1
    log_debug("Idling panel placement attempt {}".format(_idling_attempts[0]))
    ribbon = AdWindows.ComponentManager.Ribbon
    if not ribbon:
        if _idling_attempts[0] >= _MAX_IDLING_ATTEMPTS:
            log_warning(
                "Gave up placing panels: ribbon never ready after {} idles".format(
                    _MAX_IDLING_ATTEMPTS
                )
            )
            _unsubscribe("Idling")
            _unsubscribe("ViewActivated")
        return

    place_void_status_panels()
    addins_ok, modify_ok = _stop_finished_watchers()
    if addins_ok and modify_ok:
        log_info("Idling panel placement finished")
        return
    if addins_ok:
        log_info("Idling finished: Add-Ins ready, Modify clone deferred until selection")
        return
    if _idling_attempts[0] >= _MAX_IDLING_ATTEMPTS:
        log_warning("Gave up placing panels after {} idles".format(_MAX_IDLING_ATTEMPTS))
        _unsubscribe("Idling")
        _unsubscribe("ViewActivated")


def install(on_document_opening=None, on_document_opened=None):
    """Clone the ribbon panels and keep trying until Add-Ins and Modify are ready."""
    _idling_attempts[0] = 0

    def doc_opening_handler(sender, args):
        log_debug("DocumentOpening — place panels")
        if on_document_opening:
            try:
                on_document_opening()
            except Exception as ex:
                log_debug("document opening hook skipped: {}".format(ex))
        place_void_status_panels()
        _stop_finished_watchers()

    def doc_opened_handler(sender, args):
        log_debug("DocumentOpened — place panels")
        if on_document_opened:
            try:
                on_document_opened()
            except Exception as ex:
                log_debug("document opened hook skipped: {}".format(ex))
        place_void_status_panels()
        _stop_finished_watchers()

    def view_activated_handler(sender, args):
        place_void_status_panels()
        _stop_finished_watchers()

    def selection_changed_handler(sender, args):
        place_void_status_panels()
        _stop_finished_watchers()

    log_info("startup.py loading — placing ribbon panels")
    place_void_status_panels()
    addins_ok, modify_ok = _stop_finished_watchers()

    try:
        if not (addins_ok and modify_ok):
            _subscribe("Idling", _idling_handler, UIEvents.IdlingEventArgs)
    except Exception as ex:
        log_exception("Could not subscribe to Idling", ex)

    try:
        _subscribe("DocumentOpening", doc_opening_handler, Events.DocumentOpeningEventArgs)
    except Exception as ex:
        log_debug("DocumentOpening subscribe skipped: {}".format(ex))

    try:
        _subscribe("DocumentOpened", doc_opened_handler, Events.DocumentOpenedEventArgs)
    except Exception as ex:
        log_debug("DocumentOpened subscribe skipped: {}".format(ex))

    if not addins_ok:
        try:
            _subscribe("ViewActivated", view_activated_handler, UIEvents.ViewActivatedEventArgs)
        except Exception as ex:
            log_debug("ViewActivated subscribe skipped: {}".format(ex))

    if not modify_ok:
        try:
            _subscribe(
                "SelectionChanged",
                selection_changed_handler,
                UIEvents.SelectionChangedEventArgs,
            )
        except Exception as ex:
            log_debug("SelectionChanged subscribe skipped: {}".format(ex))
