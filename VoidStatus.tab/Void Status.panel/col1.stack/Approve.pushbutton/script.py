# -*- coding: utf-8 -*-
__title__ = "Approve"
__author__ = "Byggstyrning AB"
__doc__ = "Add your discipline to Approved by, and remove it from Pending by / Rejected by."
__persistentengine__ = True

from void_status.commands import apply_status
from void_status.logutil import log_info

log_info("Ribbon: Approve clicked")
apply_status("approve")
