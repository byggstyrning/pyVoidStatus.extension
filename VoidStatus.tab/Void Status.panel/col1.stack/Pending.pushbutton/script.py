# -*- coding: utf-8 -*-
__title__ = "Pending"
__author__ = "Byggstyrning AB"
__doc__ = "Add your discipline to Pending by, and remove it from Approved by / Rejected by."
__persistentengine__ = True

from void_status.commands import apply_status
from void_status.logutil import log_info

log_info("Ribbon: Pending clicked")
apply_status("pending")
