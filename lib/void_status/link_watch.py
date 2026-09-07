# -*- coding: utf-8 -*-
"""Prompt to sync Void Status after the user reloads a Revit link.

There is no dedicated Revit API event for ``RevitLinkType.Reload``.
``DocumentChanged`` with a modified ``RevitLinkType`` is the usual signal, but
Synchronize with Central / Reload Latest also touch link types. Those are
suppressed via worksharing events and transaction-name filters.
The dialog is shown on the next Idling tick so Revit is not inside the change
event.
"""

from System import EventHandler
from Autodesk.Revit.DB import Events, RevitLinkType
from Autodesk.Revit.UI import Events as UIEvents

from pyrevit import HOST_APP

from void_status.logutil import log_debug, log_info, log_warning, log_exception
from void_status.sync import link_info_for_type

_OWN_TX_PREFIX = "Void Status"

# Host worksharing operations that modify RevitLinkType without a manual reload.
_IGNORE_TX_FRAGMENTS = (
    "void status",
    "synchron",   # Synchronize / Synchronising / Synchroniser
    "synkron",    # Synkronisera (sv)
    "reload latest",
    "ladda senaste",
    "worksharing",
)

_pending = []
_pending_keys = set()
_opening = False
_worksharing = False
_idling_armed = False
_prompting = False
_handlers = []
_doc_changed_handler = None
_idling_handler = None
_syncing_handler = None
_synced_handler = None
_reloading_handler = None
_reloaded_handler = None


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


def _transaction_names(args):
    try:
        return list(args.GetTransactionNames() or [])
    except Exception:
        return []


def _names_match(names, fragments):
    for name in names:
        text = (name or "").lower()
        if not text:
            continue
        for fragment in fragments:
            if fragment in text:
                return True
    return False


def _is_ignored_transaction(args):
    """True for our own txs and host worksharing sync/reload-latest."""
    names = _transaction_names(args)
    if not names:
        return False
    if _names_match(names, _IGNORE_TX_FRAGMENTS):
        log_debug(
            "Ignore DocumentChanged for transactions: {}".format(
                ", ".join(names)
            )
        )
        return True
    return False


def _clear_pending(reason):
    if _pending or _pending_keys:
        log_debug(
            "Clear pending link-reload prompts ({}); had {}".format(
                reason, len(_pending)
            )
        )
    _pending[:] = []
    _pending_keys.clear()


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
    if _opening or _prompting or _worksharing:
        return
    if _is_ignored_transaction(args):
        _clear_pending("ignored transaction")
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
        log_info(
            "Link reload detected ({} type(s), txs={}); prompting on Idling".format(
                queued, ", ".join(_transaction_names(args)) or "?"
            )
        )
        _arm_idling()


def _set_worksharing(active, reason):
    global _worksharing
    _worksharing = bool(active)
    if active:
        _clear_pending(reason)
        _disarm_idling()
    log_debug("Worksharing suppress={}: {}".format(_worksharing, reason))


def _on_syncing_with_central(sender, args):
    _set_worksharing(True, "DocumentSynchronizingWithCentral")


def _on_synchronized_with_central(sender, args):
    _set_worksharing(False, "DocumentSynchronizedWithCentral")
    _clear_pending("after synchronize with central")


def _on_reloading_latest(sender, args):
    _set_worksharing(True, "DocumentReloadingLatest")


def _on_reloaded_latest(sender, args):
    _set_worksharing(False, "DocumentReloadedLatest")
    _clear_pending("after reload latest")


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
    if _worksharing or _opening:
        _clear_pending("idling during worksharing/opening")
        return
    items = list(_pending)
    _pending[:] = []
    _pending_keys.clear()
    if not items:
        return
    _prompting = True
    try:
        from void_status.storage import load_config_xml
        from void_status.config_xml import parse_config_xml
        from void_status.sync import collect_link_disciplines
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

            try:
                config = parse_config_xml(load_config_xml(doc))
                rows, opening_count = collect_link_disciplines(
                    info["document"], config, config.value_separator
                )
            except Exception as ex:
                log_warning(
                    "Could not scan reloaded link '{}': {}".format(
                        info.get("name"), ex
                    )
                )
                continue

            if not rows:
                log_info(
                    "Skip sync prompt for '{}': no status codes "
                    "({} openings with MatchKey/ObjectId)".format(
                        info.get("name"), opening_count
                    )
                )
                continue

            log_info(
                "Prompting Void Status sync after reload of '{}' "
                "({} status code(s))".format(info.get("name"), len(rows))
            )
            show_sync_window(doc, fixed_link=info)
    except Exception as ex:
        log_exception("Link-reload sync prompt failed", ex)
    finally:
        _prompting = False


def mark_document_opening():
    global _opening
    _opening = True
    _clear_pending("document opening")


def mark_document_opened():
    global _opening
    _opening = False
    _clear_pending("document opened")


def _subscribe_app_event(attr_name, handler_attr, callback, event_args_type):
    """Attach an Application event if this Revit build exposes it."""
    global_dict = globals()
    if global_dict.get(handler_attr) is not None:
        return
    app = HOST_APP.app
    if not hasattr(app, attr_name):
        log_debug("Application has no event {}".format(attr_name))
        return
    try:
        handler = EventHandler[event_args_type](callback)
        getattr(app, attr_name).__iadd__(handler)
        global_dict[handler_attr] = handler
        _handlers.append(handler)
        log_info("Subscribed to {}".format(attr_name))
    except Exception as ex:
        log_debug("Could not subscribe to {}: {}".format(attr_name, ex))
        global_dict[handler_attr] = None


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
        return

    # Suppress prompts during host Sync with Central / Reload Latest.
    try:
        _subscribe_app_event(
            "DocumentSynchronizingWithCentral",
            "_syncing_handler",
            _on_syncing_with_central,
            Events.DocumentSynchronizingWithCentralEventArgs,
        )
        _subscribe_app_event(
            "DocumentSynchronizedWithCentral",
            "_synced_handler",
            _on_synchronized_with_central,
            Events.DocumentSynchronizedWithCentralEventArgs,
        )
        _subscribe_app_event(
            "DocumentReloadingLatest",
            "_reloading_handler",
            _on_reloading_latest,
            Events.DocumentReloadingLatestEventArgs,
        )
        _subscribe_app_event(
            "DocumentReloadedLatest",
            "_reloaded_handler",
            _on_reloaded_latest,
            Events.DocumentReloadedLatestEventArgs,
        )
    except Exception as ex:
        log_warning("Worksharing suppress events unavailable: {}".format(ex))
