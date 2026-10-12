# -*- coding: utf-8 -*-
__title__ = "Reset"
__author__ = "Byggstyrning AB"
__doc__ = (
    "Clear Approved by, Rejected by, and Pending by on the selection. "
    "Removes every discipline in those fields, not only yours."
)

from void_status.commands import reset_status
from void_status.logutil import log_info

log_info("Ribbon: Reset all clicked")
reset_status("all")
