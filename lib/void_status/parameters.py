# -*- coding: utf-8 -*-
"""Look up shared parameters on elements by GUID, then by name."""

import System
from Autodesk.Revit.DB import StorageType

from void_status.logutil import log_debug, log_warning, element_label

_GUID_CACHE = {}


def as_guid(guid_value):
    """Return a cached ``System.Guid``, or None."""
    if not guid_value:
        return None
    if isinstance(guid_value, System.Guid):
        return guid_value
    key = str(guid_value)
    cached = _GUID_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        guid_obj = System.Guid(key)
    except Exception:
        return None
    _GUID_CACHE[key] = guid_obj
    return guid_obj


def get_parameter(element, guid=None, name=None):
    """Find a parameter by shared-parameter GUID, then by name."""
    if element is None:
        return None

    guid_obj = as_guid(guid)
    if guid_obj is not None:
        try:
            param = element.get_Parameter(guid_obj)
            if param:
                return param
        except Exception as ex:
            log_debug("get_Parameter(guid={}) failed: {}".format(guid, ex))

    if name:
        try:
            param = element.LookupParameter(name)
            if param:
                log_debug(
                    "Parameter '{}' found by name (GUID miss) on {}".format(
                        name, element_label(element)
                    )
                )
                return param
        except Exception as ex:
            log_debug("LookupParameter({}) failed: {}".format(name, ex))
    return None


def param_as_string(param):
    """Read a parameter that was already resolved."""
    if not param:
        return ""
    try:
        if param.StorageType == StorageType.String:
            value = param.AsString()
            return value if value else ""
        return param.AsValueString() or ""
    except Exception:
        return ""


def get_string_value(element, guid=None, name=None):
    """Return the string value of a parameter, or an empty string."""
    return param_as_string(get_parameter(element, guid=guid, name=name))


def _param_name(param):
    try:
        return param.Definition.Name
    except Exception:
        return "?"


def set_string_value(param, value):
    """Set a string parameter. Returns True on success."""
    if param is None or param.IsReadOnly:
        if param is not None:
            log_warning("Cannot set read-only or missing parameter {}".format(_param_name(param)))
        return False
    if param.StorageType != StorageType.String:
        log_warning(
            "Cannot set {} — StorageType is {}, expected String".format(
                _param_name(param), param.StorageType
            )
        )
        return False
    try:
        new_value = value if value is not None else ""
        if param_as_string(param) == new_value:
            return True
        param.Set(new_value)
        return True
    except Exception as ex:
        log_warning("Failed to set parameter: {}".format(ex))
        return False
