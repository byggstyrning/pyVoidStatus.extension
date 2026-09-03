# -*- coding: utf-8 -*-
__title__ = "Pending"
__author__ = "Byggstyrning AB"
__doc__ = "Add your discipline to Pending by, and remove it from Approved by / Rejected by."
__persistentengine__ = True

import sys
import os.path as op


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

from void_status.actions import apply_status
from void_status.logutil import log_info

log_info("Ribbon: Pending clicked")
apply_status("pending")
