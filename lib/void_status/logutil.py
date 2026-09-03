# -*- coding: utf-8 -*-
"""Shared logging helpers for Void Status.

All messages are prefixed with ``[VoidStatus]`` so they are easy to grep
in ``%APPDATA%/pyRevit/<RevitVersion>/pyRevit_*_runtime.log``.

Enable pyRevit Settings → Reporting Levels → File Debug Logging, then
reload the extension after changing ``lib/`` or ``startup.py``.
"""

import traceback

try:
    from pyrevit import script
    _logger = script.get_logger()
except Exception:
    import logging
    _logger = logging.getLogger("VoidStatus")
    if not _logger.handlers:
        _logger.addHandler(logging.NullHandler())

PREFIX = "[VoidStatus] "

try:
    import logging as _logging
    _DEBUG_LEVEL = _logging.DEBUG
except Exception:
    _DEBUG_LEVEL = 10


def is_debug():
    """True when pyRevit debug logging will actually emit."""
    try:
        checker = getattr(_logger, "isEnabledFor", None) or getattr(
            _logger, "is_enabled_for", None
        )
        if checker:
            return bool(checker(_DEBUG_LEVEL))
    except Exception:
        pass
    return False


def log_debug(message):
    if not is_debug():
        return
    _logger.debug(PREFIX + message)


def log_info(message):
    _logger.info(PREFIX + message)


def log_warning(message):
    _logger.warning(PREFIX + message)


def log_error(message):
    _logger.error(PREFIX + message)


def log_exception(message, exc=None):
    """Log an error plus traceback."""
    log_error(message)
    if exc is not None:
        log_error("{}: {}".format(type(exc).__name__, exc))
    log_error(traceback.format_exc())


def element_id_str(element):
    """Revit 2024+ uses ElementId.Value; older builds use IntegerValue.

    Accepts an element or an ElementId.
    """
    if element is None:
        return "None"
    eid = element
    if hasattr(element, "Id"):
        try:
            eid = element.Id
        except Exception:
            eid = element
    try:
        if hasattr(eid, "Value"):
            return str(eid.Value)
        if hasattr(eid, "IntegerValue"):
            return str(eid.IntegerValue)
        return str(eid)
    except Exception:
        return "?"


def element_label(element):
    """Short 'Category Name [id]' string for log lines."""
    if element is None:
        return "None"
    cat = ""
    try:
        if element.Category:
            cat = element.Category.Name
    except Exception:
        cat = ""
    name = ""
    try:
        name = element.Name or ""
    except Exception:
        name = ""
    parts = [p for p in (cat, name) if p]
    label = " ".join(parts) if parts else "Element"
    return "{} [{}]".format(label, element_id_str(element))
