# -*- coding: utf-8 -*-
"""Startup script for the Void Status extension.

pyRevit builds the buttons, then they are moved onto Add-Ins and Modify.
A dedicated tab would count against Revit's custom-tab limit.
"""

from void_status.logutil import log_exception
from void_status.ribbon import install


def _opening():
    from void_status.link_watch import mark_document_opening
    mark_document_opening()


def _opened():
    from void_status.link_watch import mark_document_opened
    mark_document_opened()


install(on_document_opening=_opening, on_document_opened=_opened)

try:
    from void_status.link_watch import subscribe as subscribe_link_watch
    subscribe_link_watch()
except Exception as ex:
    log_exception("Could not subscribe link-reload watch", ex)
