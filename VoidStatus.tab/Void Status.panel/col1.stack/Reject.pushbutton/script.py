# -*- coding: utf-8 -*-
__title__ = "Reject"
__author__ = "Byggstyrning AB"
__doc__ = "Add your discipline to Rejected by, and remove it from Approved by / Pending by."
__persistentengine__ = True

from void_status.commands import apply_status
from void_status.logutil import log_info

log_info("Ribbon: Reject clicked")
apply_status("reject")
