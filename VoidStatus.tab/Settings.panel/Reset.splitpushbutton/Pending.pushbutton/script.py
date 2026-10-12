# -*- coding: utf-8 -*-
__title__ = "Pending"
__author__ = "Byggstyrning AB"
__doc__ = (
    "Clear Pending by on the selection. "
    "Removes every discipline in that field, not only yours."
)

from void_status.commands import reset_status
from void_status.logutil import log_info

log_info("Ribbon: Reset Pending clicked")
reset_status("pending")
