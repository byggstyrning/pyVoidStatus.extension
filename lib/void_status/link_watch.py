# -*- coding: utf-8 -*-
"""Prompt to sync Void Status after the user reloads a Revit link.

DocumentChanged is used to detect a reloaded ``RevitLinkType``. The dialog
is shown on the next Idling tick so Revit is not inside the change event.
"""

from System import EventHandler
from Autodesk.Revit.DB import Events, RevitLinkType
from Autodesk.Revit.UI import Events as UIEvents

from pyrevit import HOST_APP

from void_status.logutil import log_debug, log_info, log_warning, log_exception
from void_status.sync import link_info_for_type

_OWN_TX_PREFIX = "Void Status"
_pending = []
_pending_keys = set()
_opening = False
_idling_armed = False
_prompting = False
_handlers = []
_doc_changed_handler = None
_idling_handler = None


def _type_id_value(element_id):
    try:
        if hasattr(element_id, "Value"):
            return int(element_id.Value)
        if hasattr(element_id, "IntegerValue"):
            return int(element_id.IntegerValue)
    except Exception:
        pass
    return str(element_id)


def _doc_key(doc):
    try:
        path = doc.PathName
        if path:
            return path
    except Exception:
        pass
    try:
        return doc.Title
    except Exception:
        return str(doc)


def _queue_key(doc, type_id):
    return (_doc_key(doc), _type_id_value(type_id))


def _is_our_transaction(args):
    try:
        names = args.GetTransactionNames()
    except Exception:
        return False
    for name in names or []:
        if name and _OWN_TX_PREFIX in name:
            return True
    return False


def _collect_link_type_ids(doc, args):
    ids = []
    seen = set()
    bags = []
    try:
        bags.append(args.GetModifiedElementIds())
    except Exception:
        pass
    try:
        bags.append(args.GetAddedElementIds())
    except Exception:
        pass
    for bag in bags:
        for eid in bag or []:
            key = _type_id_value(eid)
            if key in seen:
                continue
            try:
                element = doc.GetElement(eid)
            except Exception:
                continue
            if not isinstance(element, RevitLinkType):
                continue
            seen.add(key)
            ids.append(eid)
    return ids


def _on_document_changed(sender, args):
    if _opening or _prompting:
        return
    if _is_our_transaction(args):
        return
    try:
        doc = args.GetDocument()
    except Exception:
        return
    if doc is None:
        return
    try:
        if doc.IsFamilyDocument:
            return
    except Exception:
        pass
    type_ids = _collect_link_type_ids(doc, args)
    if not type_ids:
        return
    queued = 0
    for type_id in type_ids:
        key = _queue_key(doc, type_id)
        if key in _pending_keys:
            continue
        _pending_keys.add(key)
        _pending.append({"doc": doc, "type_id": type_id})
        queued += 1
    if queued:
        log_info("Link reload detected ({} type(s)); prompting on Idling".format(queued))
        _arm_idling()


def _arm_idling():
    global _idling_armed, _idling_handler
    if _idling_armed:
        return
    try:
        _idling_handler = EventHandler[UIEvents.IdlingEventArgs](_on_idling)
        HOST_APP.uiapp.Idling += _idling_handler
        _idling_armed = True
    except Exception as ex:
        log_exception("Could not arm Idling for link-reload prompt", ex)


def _disarm_idling():
    global _idling_armed, _idling_handler
    if not _idling_armed or _idling_handler is None:
        _idling_armed = False
        return
    try:
        HOST_APP.uiapp.Idling -= _idling_handler
    except Exception as ex:
        log_debug("Could not unsubscribe link-reload Idling: {}".format(ex))
    _idling_armed = False


def _on_idling(sender, args):
    global _prompting
    _disarm_idling()
    items = list(_pending)
    _pending[:] = []
    _pending_keys.clear()
    if not items:
        return
    _prompting = True
    try:
        from void_status.sync_ui import show_sync_window

        shown = set()
        for item in items:
            doc = item.get("doc")
            type_id = item.get("type_id")
            if doc is None or type_id is None:
                continue
            try:
                if not doc.IsValidObject:
                    continue
            except Exception:
                continue
            info = link_info_for_type(doc, type_id)
            if not info:
                log_debug("Reloaded link type is not loaded; skip prompt")
                continue
            show_key = (_doc_key(doc), info.get("name"))
            if show_key in shown:
                continue
            shown.add(show_key)
            log_info("Prompting Void Status sync after reload of '{}'".format(info.get("name")))
            show_sync_window(doc, fixed_link=info)
    except Exception as ex:
        log_exception("Link-reload sync prompt failed", ex)
    finally:
        _prompting = False


def mark_document_opening():
    global _opening
    _opening = True


def mark_document_opened():
    global _opening
    _opening = False
    _pending[:] = []
    _pending_keys.clear()


def subscribe():
    """Subscribe once from startup.py. Safe to call again."""
    global _doc_changed_handler
    if _doc_changed_handler is not None:
        return
    try:
        _doc_changed_handler = EventHandler[Events.DocumentChangedEventArgs](
            _on_document_changed
        )
        HOST_APP.app.DocumentChanged += _doc_changed_handler
        _handlers.append(_doc_changed_handler)
        log_info("Subscribed to DocumentChanged for Revit link reloads")
    except Exception as ex:
        log_exception("Could not subscribe to DocumentChanged", ex)
        _doc_changed_handler = None
