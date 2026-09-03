# -*- coding: utf-8 -*-
"""
Startup script for the Void Status extension.

pyRevit still builds a Void Status tab (needed as the clone source for
Approve / Pending / Reject). At runtime we:

- Copy Config / Reset / Sync onto Revit's Add-Ins tab
- Copy Approve / Pending / Reject onto the Modify tab (MMI pattern)
- Hide the extra Void Status tab so it does not use a ribbon slot
"""

import clr
clr.AddReference("AdWindows")
import Autodesk.Windows as AdWindows

from pyrevit import HOST_APP
from System import EventHandler
from Autodesk.Revit.DB import Events
from Autodesk.Revit.UI import Events as UIEvents
from pyrevit.coreutils import logger
from void_status.logutil import log_debug, log_info, log_warning, log_exception

script_logger = logger.get_logger("pyVoidStatus_startup")

SOURCE_TAB_TITLE = "Void Status"
SETTINGS_PANEL_TITLE = "Settings"
STATUS_PANEL_TITLE = "Void Status"
ADDINS_PANEL_TITLE = "Void Status"

_ADDINS_TITLES = ("add-ins", "addins", "add-in", "tillägg")
_MODIFY_TITLES = ("modify", "ändra")


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


def _is_source_tab(tab):
    return _norm(tab.Title) == _norm(SOURCE_TAB_TITLE) and not _is_addins_tab(tab)


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
    """Find a panel on the pyRevit source tab, including when that tab is hidden."""
    for tab in ribbon.Tabs:
        if not _is_source_tab(tab):
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


def _hide_source_tab(ribbon):
    source_tab = _find_tab(ribbon, _is_source_tab, visible_only=False)
    if not source_tab:
        return False
    if not source_tab.IsVisible:
        return True
    source_tab.IsVisible = False
    log_info("Hid extra ribbon tab '{}'".format(SOURCE_TAB_TITLE))
    return True


def place_void_status_panels():
    """Copy panels onto Add-Ins / Modify and hide the extra tab.

    Returns True when Add-Ins settings are in place. Modify clone is best-effort
    until Revit shows the contextual Modify tab.
    """
    ribbon = AdWindows.ComponentManager.Ribbon
    if not ribbon:
        log_debug("Ribbon not ready yet")
        return False

    addins_ok = False
    try:
        addins_tab = _find_tab(ribbon, _is_addins_tab, visible_only=False)
        settings_panel, _settings_tab = _find_source_panel(ribbon, SETTINGS_PANEL_TITLE)
        if addins_tab and _tab_has_panel(addins_tab, ADDINS_PANEL_TITLE):
            addins_ok = True
        elif addins_tab and settings_panel:
            _clone_panel(settings_panel, addins_tab, ADDINS_PANEL_TITLE)
            addins_ok = True
            log_info(
                "Cloned '{}' onto Add-Ins as '{}'".format(
                    SETTINGS_PANEL_TITLE, ADDINS_PANEL_TITLE
                )
            )
    except Exception as ex:
        log_exception("Failed to place Void Status on Add-Ins", ex)

    try:
        modify_tab = _find_tab(ribbon, _is_modify_tab, visible_only=True)
        status_panel, _status_tab = _find_source_panel(ribbon, STATUS_PANEL_TITLE)
        if modify_tab and status_panel and not _tab_has_panel(modify_tab, STATUS_PANEL_TITLE):
            _clone_panel(status_panel, modify_tab, STATUS_PANEL_TITLE)
            log_info("Cloned '{}' onto Modify".format(STATUS_PANEL_TITLE))
    except Exception as ex:
        log_exception("Failed to clone '{}' onto Modify".format(STATUS_PANEL_TITLE), ex)

    if addins_ok:
        try:
            _hide_source_tab(ribbon)
        except Exception as ex:
            log_debug("Could not hide source tab: {}".format(ex))

    return addins_ok


log_info("startup.py loading — placing ribbon panels")
place_void_status_panels()

_idling_attempts = [0]
_MAX_IDLING_ATTEMPTS = 50


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
            HOST_APP.uiapp.Idling -= EventHandler[UIEvents.IdlingEventArgs](_idling_handler)
        return

    placed = place_void_status_panels()
    modify_tab = _find_tab(ribbon, _is_modify_tab, visible_only=True)
    modify_ok = _tab_has_panel(modify_tab, STATUS_PANEL_TITLE) if modify_tab else False

    if placed and modify_ok:
        log_info("Idling panel placement finished")
        try:
            HOST_APP.uiapp.Idling -= EventHandler[UIEvents.IdlingEventArgs](_idling_handler)
        except Exception as ex:
            log_debug("Could not unsubscribe Idling handler: {}".format(ex))
        return

    if _idling_attempts[0] >= _MAX_IDLING_ATTEMPTS:
        if placed:
            log_info("Idling finished: Add-Ins ready, Modify clone deferred until selection")
        else:
            log_warning(
                "Gave up placing panels after {} idles".format(_MAX_IDLING_ATTEMPTS)
            )
        try:
            HOST_APP.uiapp.Idling -= EventHandler[UIEvents.IdlingEventArgs](_idling_handler)
        except Exception as ex:
            log_debug("Could not unsubscribe Idling handler: {}".format(ex))


try:
    HOST_APP.uiapp.Idling += EventHandler[UIEvents.IdlingEventArgs](_idling_handler)
    log_debug("Subscribed to Idling for panel placement")
except Exception as ex:
    log_exception("Could not subscribe to Idling", ex)


def doc_opening_handler(sender, args):
    log_debug("DocumentOpening — place panels")
    try:
        from void_status.link_watch import mark_document_opening
        mark_document_opening()
    except Exception as ex:
        log_debug("link_watch opening hook skipped: {}".format(ex))
    place_void_status_panels()


HOST_APP.app.DocumentOpening += EventHandler[Events.DocumentOpeningEventArgs](
    doc_opening_handler
)


def doc_opened_handler(sender, args):
    log_debug("DocumentOpened — place panels")
    try:
        from void_status.link_watch import mark_document_opened
        mark_document_opened()
    except Exception as ex:
        log_debug("link_watch opened hook skipped: {}".format(ex))
    place_void_status_panels()


try:
    HOST_APP.app.DocumentOpened += EventHandler[Events.DocumentOpenedEventArgs](
        doc_opened_handler
    )
    log_debug("Subscribed to DocumentOpened")
except Exception as ex:
    log_debug("DocumentOpened subscribe skipped: {}".format(ex))
    script_logger.debug("DocumentOpened subscribe skipped: {}".format(ex))


def view_activated_handler(sender, args):
    place_void_status_panels()


try:
    HOST_APP.uiapp.ViewActivated += EventHandler[UIEvents.ViewActivatedEventArgs](
        view_activated_handler
    )
    log_debug("Subscribed to ViewActivated")
except Exception as ex:
    log_debug("ViewActivated subscribe skipped: {}".format(ex))


def selection_changed_handler(sender, args):
    place_void_status_panels()


try:
    HOST_APP.uiapp.SelectionChanged += EventHandler[UIEvents.SelectionChangedEventArgs](
        selection_changed_handler
    )
    log_debug("Subscribed to SelectionChanged")
except Exception as ex:
    log_debug("SelectionChanged subscribe skipped: {}".format(ex))


try:
    from void_status.link_watch import subscribe as subscribe_link_watch
    subscribe_link_watch()
except Exception as ex:
    log_exception("Could not subscribe link-reload watch", ex)
