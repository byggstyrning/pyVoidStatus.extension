# -*- coding: utf-8 -*-
"""Synchronize approval statuses from a linked Revit/IFC model."""

from __future__ import print_function

__title__ = "Sync"
__author__ = "Byggstyrning AB"
__doc__ = (
    "Import Approved by / Rejected by / Pending by from a linked model and "
    "merge the selected discipline codes into matching openings in this project."
)

import sys
import os.path as op

from pyrevit import revit


def _drop_cached_lib():
    """lib/ stays in the IronPython engine until the extension is reloaded."""
    prefixes = ("void_status", "extensible_storage")
    for name in list(sys.modules):
        for prefix in prefixes:
            if name == prefix or name.startswith(prefix + "."):
                sys.modules.pop(name, None)
                break


def _ensure_lib():
    folder = op.dirname(op.abspath(__file__))
    while folder:
        if folder.lower().endswith(".extension"):
            lib_path = op.join(folder, "lib")
            if lib_path not in sys.path:
                sys.path.insert(0, lib_path)
            _drop_cached_lib()
            return
        parent = op.dirname(folder)
        if parent == folder:
            break
        folder = parent


_ensure_lib()

from void_status.sync_ui import show_sync_window

show_sync_window(revit.doc)
