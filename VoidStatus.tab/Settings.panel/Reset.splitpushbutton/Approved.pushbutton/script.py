# -*- coding: utf-8 -*-
__title__ = "Approved"
__author__ = "Byggstyrning AB"
__doc__ = (
    "Clear Approved by on the selection. "
    "Removes every discipline in that field, not only yours."
)

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

from void_status.actions import reset_status
from void_status.logutil import log_info

log_info("Ribbon: Reset Approved clicked")
reset_status("approved")
