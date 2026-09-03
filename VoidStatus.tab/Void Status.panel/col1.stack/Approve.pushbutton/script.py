# -*- coding: utf-8 -*-
__title__ = "Approve"
__author__ = "Byggstyrning AB"
__doc__ = "Add your discipline to Approved by, and remove it from Pending by / Rejected by."
__persistentengine__ = True

import sys
import os.path as op


def _ensure_lib():
    folder = op.dirname(op.abspath(__file__))
    while folder:
        if folder.lower().endswith(".extension"):
            lib_path = op.join(folder, "lib")
            if lib_path not in sys.path:
                sys.path.insert(0, lib_path)
            return
        parent = op.dirname(folder)
        if parent == folder:
            break
        folder = parent


_ensure_lib()

from void_status.actions import apply_status
from void_status.logutil import log_info

log_info("Ribbon: Approve clicked")
apply_status("approve")
