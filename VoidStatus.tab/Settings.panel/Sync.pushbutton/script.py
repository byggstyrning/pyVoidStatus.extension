# -*- coding: utf-8 -*-
"""Synchronize approval statuses from a linked Revit or IFC model."""

from __future__ import print_function

__title__ = "Sync"
__author__ = "Byggstyrning AB"
__doc__ = (
    "Import Approved by / Rejected by / Pending by from a linked model and "
    "merge the selected discipline codes into matching openings in this project."
)

from pyrevit import revit
from void_status.sync_ui import show_sync_window

show_sync_window(revit.doc)
